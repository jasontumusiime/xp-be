import uuid
from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from sqlmodel import select, func, col

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.models import (
    Task, TaskCreate, TaskUpdate, TaskPublic, TasksPublic,
    TaskStatus, UserRole, AuditLog, get_datetime_utc,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])

ALLOWED_TYPES: dict[str, set[str]] = {
    "photo": {"jpg", "jpeg", "png", "webp"},
    "video": {"mp4", "mov", "avi"},
    "voice": {"m4a", "mp3", "wav", "aac"},
    "document": {"pdf", "doc", "docx"},
}

@router.post("/upload")
async def upload_task_attachment(
    current_user: CurrentUser,
    media_type: str,
    file: UploadFile = File(...),
) -> JSONResponse:
    if media_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"media_type must be one of: {', '.join(ALLOWED_TYPES)}")
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_TYPES[media_type]:
        raise HTTPException(status_code=400, detail=f"Invalid file type for {media_type}")
    dest_dir = Path(settings.MEDIA_PATH) / media_type
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}.{ext}"
    dest = dest_dir / filename
    content = await file.read()
    dest.write_bytes(content)
    return JSONResponse({"url": f"/media/{media_type}/{filename}"})

@router.get("/", response_model=TasksPublic)
def list_tasks(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
    status: TaskStatus | None = None,
    pdm_only: bool = False,
    pdm_beneficiary_id: uuid.UUID | None = None,
    pdm_disbursement_id: uuid.UUID | None = None,
) -> Any:
    from app.jurisdiction import get_agent_ids_in_jurisdiction
    q = select(Task)

    agent_ids = get_agent_ids_in_jurisdiction(session, current_user)
    if agent_ids is not None:
        q = q.where(Task.assigned_to.in_(agent_ids))

    if status:
        q = q.where(Task.status == status)
    if pdm_only:
        from sqlmodel import or_
        q = q.where(or_(Task.pdm_beneficiary_id.is_not(None), Task.pdm_disbursement_id.is_not(None)))
    if pdm_beneficiary_id:
        q = q.where(Task.pdm_beneficiary_id == pdm_beneficiary_id)
    if pdm_disbursement_id:
        q = q.where(Task.pdm_disbursement_id == pdm_disbursement_id)

    count = session.exec(select(func.count()).select_from(q.subquery())).one()
    tasks = session.exec(q.order_by(col(Task.created_at).desc()).offset(skip).limit(limit)).all()
    return TasksPublic(data=[TaskPublic.model_validate(t) for t in tasks], count=count)


@router.post("/", response_model=TaskPublic)
async def create_task(*, session: SessionDep, current_user: CurrentUser, body: TaskCreate) -> Any:
    if current_user.role == UserRole.AGENT:
        raise HTTPException(status_code=403, detail="Agents cannot create tasks.")
    task = Task(**body.model_dump(), created_by=current_user.id)
    session.add(task)
    session.commit()
    session.refresh(task)
    # Notify assigned agent
    from app.models import PushToken
    from app.api.routes.websocket import send_push_notifications
    from app.api.routes.notifications import create_notification
    from app.models import NotificationType
    if task.assigned_to:
        create_notification(session, task.assigned_to, NotificationType.TASK, "New Task Assigned", task.title)
        session.commit()
        tokens = session.exec(select(PushToken.token).where(PushToken.user_id == task.assigned_to)).all()
        await send_push_notifications(list(tokens), title="New Task Assigned", body=task.title)
    return task


@router.get("/{task_id}", response_model=TaskPublic)
def get_task(*, session: SessionDep, current_user: CurrentUser, task_id: uuid.UUID) -> Any:
    from app.jurisdiction import get_agent_ids_in_jurisdiction
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    agent_ids = get_agent_ids_in_jurisdiction(session, current_user)
    if agent_ids is not None and task.assigned_to not in agent_ids:
        raise HTTPException(status_code=403, detail="Access denied.")
    return task


@router.patch("/{task_id}", response_model=TaskPublic)
async def update_task(
    *, session: SessionDep, current_user: CurrentUser,
    task_id: uuid.UUID, body: TaskUpdate,
) -> Any:
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    # Agents can only update status on their own tasks
    if current_user.role == UserRole.AGENT:
        if task.assigned_to != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied.")
        allowed = {"status"}
        data = {k: v for k, v in body.model_dump(exclude_unset=True).items() if k in allowed}
    else:
        data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(task, field, value)
    task.updated_at = get_datetime_utc()
    session.add(task)
    if "status" in data:
        session.add(AuditLog(
            actor_id=current_user.id,
            action="task.status_changed",
            entity_type="task",
            entity_id=task.id,
            detail=f"status → {task.status}",
        ))
    session.commit()
    session.refresh(task)

    from app.models import PushToken, NotificationType
    from app.api.routes.websocket import send_push_notifications
    from app.api.routes.notifications import create_notification

    # Supervisor updates task → notify assigned agent
    if current_user.role != UserRole.AGENT and task.assigned_to:
        notif_body = f"Status updated to {task.status.replace('_', ' ').title()}" if "status" in data else "Your task has been updated"
        create_notification(session, task.assigned_to, NotificationType.TASK, task.title, notif_body)
        session.commit()
        tokens = session.exec(select(PushToken.token).where(PushToken.user_id == task.assigned_to)).all()
        if tokens:
            await send_push_notifications(list(tokens), title=task.title, body=notif_body)

    # Agent updates status → notify task creator
    if current_user.role == UserRole.AGENT and "status" in data and task.created_by:
        notif_body = f"{current_user.full_name or current_user.email} marked task as {task.status.replace('_', ' ').title()}"
        create_notification(session, task.created_by, NotificationType.TASK, task.title, notif_body)
        session.commit()

    return task
