import uuid
from typing import Any
from fastapi import APIRouter, HTTPException
from sqlmodel import select, col

from app.api.deps import CurrentUser, SessionDep
from app.models import Notification, NotificationPublic, NotificationType

router = APIRouter(prefix="/notifications", tags=["notifications"])


def create_notification(
    session: Any,
    user_id: uuid.UUID,
    type: NotificationType,
    title: str,
    message: str,
) -> None:
    """Internal helper — call from other routes to persist a notification."""
    session.add(Notification(user_id=user_id, type=type, title=title, message=message))
    # Caller is responsible for session.commit()


@router.get("/", response_model=list[NotificationPublic])
def list_notifications(*, session: SessionDep, current_user: CurrentUser) -> Any:
    return session.exec(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(col(Notification.created_at).desc())
        .limit(100)
    ).all()


@router.post("/{notification_id}/read", response_model=NotificationPublic)
def mark_read(*, session: SessionDep, current_user: CurrentUser, notification_id: uuid.UUID) -> Any:
    n = session.get(Notification, notification_id)
    if not n or n.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found.")
    n.read = True
    session.add(n)
    session.commit()
    session.refresh(n)
    return n


@router.post("/read-all")
def mark_all_read(*, session: SessionDep, current_user: CurrentUser) -> Any:
    notifications = session.exec(
        select(Notification)
        .where(Notification.user_id == current_user.id, Notification.read == False)  # noqa: E712
    ).all()
    for n in notifications:
        n.read = True
        session.add(n)
    session.commit()
    return {"message": f"Marked {len(notifications)} notifications as read"}
