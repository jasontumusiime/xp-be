"""
WebSocket endpoint for real-time updates.

Clients connect to /ws?token=<jwt>
Server broadcasts JSON messages of the form:
  { "type": "gps", "agent_id": "...", "lat": 0.0, "lng": 0.0, "recorded_at": "..." }
  { "type": "notification", "message": "...", "level": "info|warning|danger" }
  { "type": "panic", "agent_id": "...", "lat": 0.0, "lng": 0.0, "agent_name": "..." }

The GPS route calls ws_manager.broadcast_gps() after each log insert.
"""
import json
from typing import Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status, Request
import jwt
from jwt.exceptions import InvalidTokenError
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core import security
from app.api.deps import CurrentUser, SessionDep
from app.models import AuditLog

router = APIRouter(tags=["websocket"])
limiter = Limiter(key_func=get_remote_address)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections = [c for c in self._connections if c is not ws]

    async def broadcast(self, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(json.dumps(payload))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_gps(self, agent_id: str, lat: float, lng: float, recorded_at: str) -> None:
        await self.broadcast({"type": "gps", "agent_id": agent_id, "lat": lat, "lng": lng, "recorded_at": recorded_at})

    async def broadcast_notification(self, message: str, level: str = "info") -> None:
        await self.broadcast({"type": "notification", "message": message, "level": level})


ws_manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(...)) -> None:
    try:
        jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
    except InvalidTokenError:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


from pydantic import BaseModel

class PanicPayload(BaseModel):
    latitude: float
    longitude: float


class PushTokenPayload(BaseModel):
    token: str


@router.post("/push-token")
def register_push_token(*, session: SessionDep, current_user: CurrentUser, body: PushTokenPayload) -> Any:
    """Register or update the Expo push token for the current user."""
    from app.models import PushToken
    from sqlmodel import select
    existing = session.exec(select(PushToken).where(PushToken.token == body.token)).first()
    if not existing:
        session.add(PushToken(user_id=current_user.id, token=body.token))
        session.commit()
    return {"message": "Push token registered"}


async def send_push_notifications(tokens: list[str], title: str, body: str) -> None:
    """Send FCM push notifications to a list of device tokens."""
    from app.firebase import send_fcm_notification
    from app.models import PushToken
    from sqlmodel import Session
    from app.core.db import engine
    invalid = await send_fcm_notification(tokens, title, body)
    if invalid:
        with Session(engine) as session:
            for token in invalid:
                row = session.exec(select(PushToken).where(PushToken.token == token)).first()
                if row:
                    session.delete(row)
            session.commit()


@router.post("/panic")
@limiter.limit("5/minute")
async def panic_alert(request: Request, *, session: SessionDep, current_user: CurrentUser, body: PanicPayload) -> Any:
    """Agent triggers a panic alert — broadcasts to all connected web clients."""
    from sqlmodel import select
    from app.models import PushToken, User, UserRole
    session.add(AuditLog(
        actor_id=current_user.id,
        action="agent.panic",
        entity_type="user",
        entity_id=current_user.id,
        detail=f"Panic alert at {body.latitude:.5f},{body.longitude:.5f}",
    ))
    session.commit()
    await ws_manager.broadcast({
        "type": "panic",
        "agent_id": str(current_user.id),
        "agent_name": current_user.full_name or current_user.email,
        "lat": body.latitude,
        "lng": body.longitude,
    })
    await ws_manager.broadcast_notification(
        message=f"🚨 PANIC ALERT from {current_user.full_name or current_user.email}",
        level="danger",
    )
    # Push to all admin users who have registered a push token
    admin_roles = [UserRole.HQ_ADMIN, UserRole.DG, UserRole.RISO, UserRole.SISO, UserRole.DISO, UserRole.GISO]
    admin_ids = session.exec(select(User.id).where(User.role.in_(admin_roles))).all()
    tokens = session.exec(select(PushToken.token).where(PushToken.user_id.in_(admin_ids))).all()
    await send_push_notifications(
        list(tokens),
        title="🚨 PANIC ALERT",
        body=f"{current_user.full_name or current_user.email} needs help at {body.latitude:.4f},{body.longitude:.4f}",
    )
    # SMS broadcast to all admins with phone numbers
    admin_phones = session.exec(
        select(User.phone_number).where(User.role.in_(admin_roles), User.phone_number != None)  # noqa: E711
    ).all()
    if admin_phones:
        sms_message = (
            f"XPURSE PANIC ALERT: {current_user.full_name or current_user.email} "
            f"needs help at {body.latitude:.4f},{body.longitude:.4f}. Respond immediately."
        )
        try:
            from app.africastalking import send_sms
            await __import__("asyncio").get_event_loop().run_in_executor(
                None, lambda: send_sms(list(admin_phones), sms_message)
            )
        except Exception:
            pass  # SMS failure must not block the panic response
    return {"message": "Panic alert sent"}
