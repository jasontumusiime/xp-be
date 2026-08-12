import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import select, col

from app.api.deps import CurrentUser, SessionDep, require_roles
from app.models import Alert, AlertCategory, AlertPublic, AlertsPublic, UserRole, User, SubCounty, Parish

router = APIRouter(prefix="/alerts", tags=["alerts"])

ADMIN_ROLES = (UserRole.HQ_ADMIN, UserRole.DG)

# Roles that see everything (no jurisdiction filter)
UNRESTRICTED_ROLES = {UserRole.HQ_ADMIN, UserRole.DG, UserRole.RISO}


def _get_jurisdiction_subcounty_ids(session: SessionDep, user: User) -> list[uuid.UUID] | None:
    """
    Returns list of subcounty UUIDs the user can see, or None (unrestricted).
    - HQ_ADMIN / DG / RISO → None (all)
    - SISO (geographical_id = district_id) → all subcounties in that district via county
    - DISO (geographical_id = subcounty_id) → just that subcounty
    - GISO / AGENT (geographical_id = subcounty_id) → just that subcounty
    """
    if not user.geographical_id or user.role in UNRESTRICTED_ROLES:
        return None

    if user.role in (UserRole.DISO, UserRole.GISO, UserRole.AGENT):
        return [user.geographical_id]

    if user.role == UserRole.SISO:
        # geographical_id is a district id — get all subcounties via county
        from app.models import County
        counties = session.exec(select(County).where(County.district_id == user.geographical_id)).all()
        county_ids = [c.id for c in counties]
        if not county_ids:
            return []
        subcounties = session.exec(select(SubCounty).where(SubCounty.county_id.in_(county_ids))).all()
        return [s.id for s in subcounties]

    return None


@router.get("/", response_model=AlertsPublic)
def list_alerts(
    session: SessionDep,
    current_user: CurrentUser,
    subcounty_id: uuid.UUID | None = None,
    parish_id: uuid.UUID | None = None,
    category: AlertCategory | None = None,
    is_active: bool | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 20,
    offset: int = 0,
) -> Any:
    q = select(Alert)

    # Jurisdiction scoping
    allowed_subcounties = _get_jurisdiction_subcounty_ids(session, current_user)
    if allowed_subcounties is not None:
        if subcounty_id and subcounty_id in allowed_subcounties:
            q = q.where(Alert.subcounty_id == subcounty_id)
        elif allowed_subcounties:
            q = q.where(Alert.subcounty_id.in_(allowed_subcounties))
        else:
            return AlertsPublic(data=[], count=0)
    elif subcounty_id:
        q = q.where(Alert.subcounty_id == subcounty_id)

    if parish_id:
        q = q.where(Alert.parish_id == parish_id)
    if category:
        q = q.where(Alert.category == category)
    if is_active is not None:
        q = q.where(Alert.is_active == is_active)
    if date_from:
        q = q.where(Alert.created_at >= date_from)
    if date_to:
        q = q.where(Alert.created_at <= date_to)

    # Efficient count using SELECT COUNT(*)
    count_q = select(func.count()).select_from(q.subquery())
    total = session.exec(count_q).one()

    alerts = session.exec(q.order_by(col(Alert.created_at).desc()).offset(offset).limit(limit)).all()
    return AlertsPublic(data=alerts, count=total)


@router.get("/{alert_id}", response_model=AlertPublic)
def get_alert(*, session: SessionDep, current_user: CurrentUser, alert_id: uuid.UUID) -> Any:
    from fastapi import HTTPException
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return alert


@router.post("/run-engine", dependencies=[require_roles(*ADMIN_ROLES)])
async def run_engine(session: SessionDep) -> Any:
    from app.alert_engine import run_alert_engine
    result = await run_alert_engine(session)
    return result
