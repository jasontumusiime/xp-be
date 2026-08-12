from typing import Any
from fastapi import APIRouter, Request
from sqlmodel import select, col, func
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.deps import CurrentUser, SessionDep
from app.models import Device, DeviceStatus, GpsLog, GpsLogCreate, GpsLogPublic, UserRole
from app.api.routes.websocket import ws_manager

router = APIRouter(prefix="/gps", tags=["gps"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/", response_model=GpsLogPublic)
@limiter.limit("10/minute")
async def log_location(request: Request, *, session: SessionDep, current_user: CurrentUser, body: GpsLogCreate) -> Any:
    log = GpsLog(agent_id=current_user.id, latitude=body.latitude, longitude=body.longitude)
    session.add(log)

    # Mark the agent's assigned device as ONLINE and update last_seen
    device = session.exec(select(Device).where(Device.assigned_to == current_user.id)).first()
    if device:
        device.status = DeviceStatus.ONLINE
        device.last_seen = log.recorded_at
        session.add(device)

    session.commit()
    session.refresh(log)
    # Broadcast to all connected web clients
    await ws_manager.broadcast_gps(
        agent_id=str(log.agent_id),
        lat=log.latitude,
        lng=log.longitude,
        recorded_at=log.recorded_at.isoformat(),
    )
    return log


@router.get("/latest", response_model=list[GpsLogPublic])
def get_latest_positions(*, session: SessionDep, current_user: CurrentUser) -> Any:
    """Most recent GPS ping per agent, scoped to the current user's jurisdiction."""
    from app.jurisdiction import get_agent_ids_in_jurisdiction
    agent_ids = get_agent_ids_in_jurisdiction(session, current_user)

    latest_times = (
        select(GpsLog.agent_id, func.max(GpsLog.recorded_at).label("max_ts"))
        .group_by(GpsLog.agent_id)
        .subquery()
    )
    q = (
        select(GpsLog)
        .join(latest_times, (GpsLog.agent_id == latest_times.c.agent_id) & (GpsLog.recorded_at == latest_times.c.max_ts))
    )
    if agent_ids is not None:
        q = q.where(GpsLog.agent_id.in_(agent_ids))

    rows = session.exec(q.order_by(col(GpsLog.recorded_at).desc()).limit(200)).all()
    return [GpsLogPublic.model_validate(r) for r in rows]


@router.get("/agents/{agent_id}", response_model=list[GpsLogPublic])
def get_agent_track(
    *, session: SessionDep, current_user: CurrentUser,
    agent_id: str, limit: int = 200,
) -> Any:
    import uuid as _uuid
    from fastapi import HTTPException
    if current_user.role == UserRole.AGENT and str(current_user.id) != agent_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    logs = session.exec(
        select(GpsLog)
        .where(GpsLog.agent_id == _uuid.UUID(agent_id))
        .order_by(col(GpsLog.recorded_at).desc())
        .limit(limit)
    ).all()
    return [GpsLogPublic.model_validate(l) for l in logs]
