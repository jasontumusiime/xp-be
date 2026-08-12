import uuid
from typing import Any, Literal
from fastapi import APIRouter, HTTPException
from sqlmodel import select, col
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep, require_roles
from app.models import (
    Device, DeviceCreate, DeviceUpdate, DevicePublic, DevicesPublic, UserRole,
    DeviceCommandRecord, DeviceCommandType, DeviceCommandStatus, DeviceCommandPublic,
    PushToken, User,
)
from app.api.routes.websocket import ws_manager

router = APIRouter(prefix="/devices", tags=["devices"])

DEVICE_ROLES = (UserRole.HQ_ADMIN, UserRole.DG, UserRole.RISO, UserRole.SISO, UserRole.DISO, UserRole.GISO)


async def _send_fcm_data(tokens: list[str], data: dict[str, str]) -> list[str]:
    """Send a silent FCM data message (no notification). Returns invalid tokens."""
    if not tokens:
        return []
    try:
        from firebase_admin import messaging
        from app.firebase import _init
        if not _init():
            return []
        response = messaging.send_each_for_multicast(
            messaging.MulticastMessage(
                data=data,
                android=messaging.AndroidConfig(priority="high"),
                tokens=tokens,
            )
        )
        invalid: list[str] = []
        for idx, result in enumerate(response.responses):
            if not result.success:
                code = getattr(result.exception, "code", None)
                if code in ("registration-token-not-registered", "invalid-registration-token"):
                    invalid.append(tokens[idx])
        return invalid
    except Exception:
        return []


@router.get("/", response_model=DevicesPublic, dependencies=[require_roles(*DEVICE_ROLES)])
def list_devices(session: SessionDep, current_user: CurrentUser) -> Any:
    from app.jurisdiction import get_agent_ids_in_jurisdiction
    q = select(Device)
    agent_ids = get_agent_ids_in_jurisdiction(session, current_user)
    if agent_ids is not None:
        q = q.where(Device.assigned_to.in_(agent_ids))
    devices = session.exec(q.order_by(col(Device.created_at).desc())).all()
    return DevicesPublic(data=[DevicePublic.model_validate(d) for d in devices], count=len(devices))


@router.post("/", response_model=DevicePublic, dependencies=[require_roles(UserRole.HQ_ADMIN)])
def create_device(*, session: SessionDep, body: DeviceCreate) -> Any:
    if session.exec(select(Device).where(Device.serial_number == body.serial_number)).first():
        raise HTTPException(status_code=409, detail="Device with this serial number already exists.")
    device = Device(**body.model_dump())
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


@router.patch("/{device_id}", response_model=DevicePublic, dependencies=[require_roles(UserRole.HQ_ADMIN)])
def update_device(*, session: SessionDep, device_id: uuid.UUID, body: DeviceUpdate) -> Any:
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(device, field, value)
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


@router.delete("/{device_id}", dependencies=[require_roles(UserRole.HQ_ADMIN)])
def delete_device(*, session: SessionDep, device_id: uuid.UUID) -> Any:
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found.")
    session.delete(device)
    session.commit()
    return {"message": "Device deleted"}


class DeviceCommand(BaseModel):
    type: Literal["ALERT", "VIBRATE"]


@router.post("/{device_id}/command", dependencies=[require_roles(*DEVICE_ROLES)])
async def send_device_command(
    *, session: SessionDep, device_id: uuid.UUID, body: DeviceCommand,
) -> Any:
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found.")
    await ws_manager.broadcast({
        "type": "device_command",
        "device_id": str(device_id),
        "agent_id": str(device.assigned_to) if device.assigned_to else None,
        "command": body.type,
    })
    return {"message": f"Command '{body.type}' sent to device {device_id}"}


# ── Remote Agent Control ──────────────────────────────────

class AgentCommandBody(BaseModel):
    command: DeviceCommandType


@router.post("/agent/{user_id}/command", response_model=DeviceCommandPublic, dependencies=[require_roles(*DEVICE_ROLES)])
async def issue_agent_command(
    *, session: SessionDep, current_user: CurrentUser, user_id: uuid.UUID, body: AgentCommandBody,
) -> Any:
    target = session.get(User, user_id)
    if not target or target.role != UserRole.AGENT:
        raise HTTPException(status_code=404, detail="Agent not found.")

    # WIPE deactivates the account so the agent cannot log in again
    if body.command == DeviceCommandType.WIPE:
        target.is_active = False
        session.add(target)

    # ENABLE reactivates the account
    if body.command == DeviceCommandType.ENABLE:
        target.is_active = True
        session.add(target)

    record = DeviceCommandRecord(user_id=user_id, issued_by=current_user.id, command=body.command)
    session.add(record)
    session.commit()
    session.refresh(record)

    tokens = session.exec(select(PushToken.token).where(PushToken.user_id == user_id)).all()
    if tokens:
        invalid = await _send_fcm_data(
            list(tokens),
            {"command": body.command.value, "command_id": str(record.id)},
        )
        if invalid:
            for t in invalid:
                row = session.exec(select(PushToken).where(PushToken.token == t)).first()
                if row:
                    session.delete(row)
        record.status = DeviceCommandStatus.DELIVERED
        session.add(record)
        session.commit()
        session.refresh(record)

    return record


@router.get("/agent/{user_id}/commands", response_model=list[DeviceCommandPublic], dependencies=[require_roles(*DEVICE_ROLES)])
def list_agent_commands(*, session: SessionDep, user_id: uuid.UUID) -> Any:
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    commands = session.exec(
        select(DeviceCommandRecord)
        .where(DeviceCommandRecord.user_id == user_id)
        .order_by(col(DeviceCommandRecord.created_at).desc())
    ).all()
    return commands


@router.post("/commands/{command_id}/ack")
def ack_command(*, session: SessionDep, current_user: CurrentUser, command_id: uuid.UUID) -> Any:
    record = session.get(DeviceCommandRecord, command_id)
    if not record or record.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Command not found.")
    record.status = DeviceCommandStatus.ACKNOWLEDGED
    session.add(record)
    session.commit()
    return {"message": "Acknowledged"}

