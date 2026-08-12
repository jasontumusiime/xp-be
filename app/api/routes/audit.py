from typing import Any
from fastapi import APIRouter
from sqlmodel import select, func, col

from app.api.deps import CurrentUser, SessionDep, require_roles
from app.models import AuditLog, AuditLogPublic, AuditLogsPublic, UserRole

router = APIRouter(prefix="/audit", tags=["audit"])

AUDIT_ROLES = (UserRole.HQ_ADMIN, UserRole.DG, UserRole.RISO)


@router.get("/", response_model=AuditLogsPublic, dependencies=[require_roles(*AUDIT_ROLES)])
def list_audit_logs(
    session: SessionDep,
    skip: int = 0,
    limit: int = 200,
    entity_type: str | None = None,
) -> Any:
    q = select(AuditLog)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    count = session.exec(select(func.count()).select_from(q.subquery())).one()
    logs = session.exec(q.order_by(col(AuditLog.created_at).desc()).offset(skip).limit(limit)).all()
    return AuditLogsPublic(data=[AuditLogPublic.model_validate(l) for l in logs], count=count)
