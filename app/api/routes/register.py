"""
Agent self-registration with OTP (Feature 2) and Device PIN verification (Feature 3).
"""
from __future__ import annotations

import hashlib
import random
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.core import security
from app.core.config import settings
from app.models import (
    DevicePin,
    OtpRecord,
    PushToken,
    Token,
    User,
    UserRole,
    UserStatus,
    get_datetime_utc,
)

router = APIRouter(tags=["register"])

UG_PHONE_RE = re.compile(r"^\+256[0-9]{9}$")

# Simple in-memory rate limit: phone → list of request timestamps
_otp_attempts: dict[str, list[datetime]] = {}
_OTP_WINDOW_HOURS = 1
_OTP_MAX_ATTEMPTS = 3


def _check_rate_limit(phone: str) -> None:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=_OTP_WINDOW_HOURS)
    attempts = [t for t in _otp_attempts.get(phone, []) if t > cutoff]
    if len(attempts) >= _OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many OTP requests. Try again later.")
    attempts.append(now)
    _otp_attempts[phone] = attempts


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def _hash_pin(pin: str) -> str:
    return security.get_password_hash(pin)


def _verify_pin(pin: str, pin_hash: str) -> bool:
    ok, _ = security.verify_password(pin, pin_hash)
    return ok


# ── OTP Request ───────────────────────────────────────────

class OtpRequestBody(BaseModel):
    phone_number: str


@router.post("/register/request-otp")
def request_otp(*, session: SessionDep, body: OtpRequestBody) -> Any:
    if not UG_PHONE_RE.match(body.phone_number):
        raise HTTPException(status_code=422, detail="Phone number must be a valid Ugandan number (+256XXXXXXXXX).")
    _check_rate_limit(body.phone_number)

    otp = str(random.randint(100000, 999999))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    # Invalidate any existing unused OTPs for this phone
    existing = session.exec(
        select(OtpRecord).where(OtpRecord.phone_number == body.phone_number, OtpRecord.used == False)  # noqa: E712
    ).all()
    for rec in existing:
        rec.used = True
        session.add(rec)

    record = OtpRecord(
        phone_number=body.phone_number,
        otp_hash=_hash_otp(otp),
        expires_at=expires_at,
    )
    session.add(record)
    session.commit()

    # Send SMS via Africa's Talking
    try:
        from app.africastalking import send_sms
        hash_suffix = f" {settings.SMS_APP_HASH}" if settings.SMS_APP_HASH and settings.SMS_APP_HASH != "changethis" else ""
        send_sms([body.phone_number], f"Your Xpurse verification code is: {otp}. Valid for 10 minutes.{hash_suffix}")
    except Exception:
        pass  # Don't fail if SMS is unavailable in dev

    return {"message": "OTP sent"}


# ── OTP Verify + Register ─────────────────────────────────

class RegisterBody(BaseModel):
    full_name: str
    phone_number: str
    otp: str
    pin: str
    device_id: str


@router.post("/register/verify", response_model=Token)
def verify_and_register(*, session: SessionDep, body: RegisterBody) -> Any:
    if not UG_PHONE_RE.match(body.phone_number):
        raise HTTPException(status_code=422, detail="Invalid phone number.")
    if len(body.pin) != 5 or not body.pin.isdigit():
        raise HTTPException(status_code=422, detail="PIN must be exactly 5 digits.")

    now = datetime.now(timezone.utc)
    record = session.exec(
        select(OtpRecord).where(
            OtpRecord.phone_number == body.phone_number,
            OtpRecord.used == False,  # noqa: E712
            OtpRecord.expires_at > now,
        )
    ).first()
    if not record or record.otp_hash != _hash_otp(body.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

    # Check phone not already registered
    if session.exec(select(User).where(User.phone_number == body.phone_number)).first():
        raise HTTPException(status_code=409, detail="Phone number already registered.")

    email = f"{body.phone_number.replace('+', '')}@xpurse.local"
    user = User(
        email=email,
        full_name=body.full_name,
        phone_number=body.phone_number,
        hashed_password=security.get_password_hash(str(uuid.uuid4())),
        role=UserRole.AGENT,
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    session.add(user)
    session.flush()  # get user.id

    # Create device PIN
    device_pin = DevicePin(
        user_id=user.id,
        device_id=body.device_id,
        pin_hash=_hash_pin(body.pin),
    )
    session.add(device_pin)

    record.used = True
    session.add(record)
    session.commit()

    access_token = security.create_access_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        role=user.role.value,
    )
    return Token(access_token=access_token, role=user.role)


# ── PIN Verification ──────────────────────────────────────

class PinVerifyBody(BaseModel):
    device_id: str
    pin: str


@router.post("/auth/verify-pin")
def verify_pin(*, session: SessionDep, current_user: CurrentUser, body: PinVerifyBody) -> Any:
    record = session.exec(
        select(DevicePin).where(
            DevicePin.user_id == current_user.id,
            DevicePin.device_id == body.device_id,
        )
    ).first()
    if not record or not _verify_pin(body.pin, record.pin_hash):
        raise HTTPException(status_code=401, detail="Invalid PIN.")
    return {"valid": True}


# ── PIN Update ────────────────────────────────────────────

class PinUpdateBody(BaseModel):
    device_id: str
    current_pin: str
    new_pin: str


@router.patch("/auth/update-pin")
def update_pin(*, session: SessionDep, current_user: CurrentUser, body: PinUpdateBody) -> Any:
    if len(body.new_pin) != 5 or not body.new_pin.isdigit():
        raise HTTPException(status_code=422, detail="PIN must be exactly 5 digits.")
    record = session.exec(
        select(DevicePin).where(
            DevicePin.user_id == current_user.id,
            DevicePin.device_id == body.device_id,
        )
    ).first()
    if not record or not _verify_pin(body.current_pin, record.pin_hash):
        raise HTTPException(status_code=401, detail="Current PIN is incorrect.")
    record.pin_hash = _hash_pin(body.new_pin)
    record.updated_at = get_datetime_utc()
    session.add(record)
    session.commit()
    return {"message": "PIN updated"}
