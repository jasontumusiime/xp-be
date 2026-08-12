"""
Communications routes — SMS alerts and click-to-call via Africa's Talking.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep, require_roles
from app.core.config import settings
from app.models import User, UserRole
from sqlmodel import select

router = APIRouter(prefix="/comms", tags=["comms"])


class SmsPayload(BaseModel):
    recipients: list[str]  # list of +256… numbers
    message: str


class CallPayload(BaseModel):
    destination: str  # +256… number to call
    caller_id: str    # +256… number to call from (must be registered AT number)


@router.post("/sms", dependencies=[require_roles(UserRole.GISO)])
def send_sms(*, body: SmsPayload, current_user: CurrentUser) -> Any:
    """Send an SMS to one or more recipients. Requires GISO role or above."""
    if not body.recipients:
        raise HTTPException(status_code=400, detail="No recipients provided.")
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    try:
        from app.africastalking import send_sms as _send
        result = _send(body.recipients, body.message)
        return {"status": "sent", "result": result}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SMS delivery failed: {exc}") from exc


@router.post("/call", dependencies=[require_roles(UserRole.GISO)])
def click_to_call(*, body: CallPayload, current_user: CurrentUser) -> Any:
    """Initiate a click-to-call. Requires GISO role or above."""
    try:
        from app.africastalking import initiate_call
        result = initiate_call(caller_id=body.caller_id, destination=body.destination)
        return {"status": "initiated", "result": result}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Call initiation failed: {exc}") from exc


@router.post("/call-agent/{user_id}", dependencies=[require_roles(UserRole.GISO)])
def call_agent(*, session: SessionDep, current_user: CurrentUser, user_id: str) -> Any:
    """Initiate a call to an agent by user ID. Uses AT_CALLER_ID from settings."""
    from app.models import User as UserModel
    import uuid as _uuid
    agent = session.get(UserModel, _uuid.UUID(user_id))
    if not agent or not agent.phone_number:
        raise HTTPException(status_code=404, detail="Agent not found or has no phone number.")
    caller_id = settings.AT_CALLER_ID
    if not caller_id:
        raise HTTPException(status_code=503, detail="AT_CALLER_ID not configured.")
    try:
        from app.africastalking import initiate_call
        result = initiate_call(caller_id=caller_id, destination=agent.phone_number)
        return {"status": "initiated", "destination": agent.phone_number, "result": result}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Call initiation failed: {exc}") from exc


@router.post("/sms/panic-broadcast")
async def sms_panic_broadcast(*, session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Send an SMS panic alert to all admin users who have a phone number.
    Called automatically by the panic endpoint, or manually by an admin.
    """
    admin_roles = [UserRole.HQ_ADMIN, UserRole.DG, UserRole.RISO, UserRole.SISO, UserRole.DISO, UserRole.GISO]
    admins = session.exec(
        select(User).where(User.role.in_(admin_roles), User.phone_number != None)  # noqa: E711
    ).all()
    recipients = [a.phone_number for a in admins if a.phone_number]
    if not recipients:
        return {"status": "no_recipients"}
    message = (
        f"XPURSE PANIC ALERT: {current_user.full_name or current_user.email} "
        "has triggered a panic alert. Please respond immediately."
    )
    try:
        from app.africastalking import send_sms as _send
        result = _send(recipients, message)
        return {"status": "sent", "recipients": len(recipients), "result": result}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SMS delivery failed: {exc}") from exc
