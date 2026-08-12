import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.models import CheckIn, CheckInPublic

router = APIRouter(prefix="/checkin", tags=["checkin"])


@router.get("/", response_model=CheckInPublic | None)
def get_current_checkin(*, session: SessionDep, current_user: CurrentUser) -> Any:
    """Return the agent's active (not checked-out) check-in, or null."""
    row = session.exec(
        select(CheckIn)
        .where(CheckIn.user_id == current_user.id, CheckIn.checked_out_at == None)  # noqa: E711
        .order_by(CheckIn.checked_in_at.desc())
    ).first()
    return row


@router.post("/", response_model=CheckInPublic)
def check_in(
    *, session: SessionDep, current_user: CurrentUser,
    latitude: float | None = None, longitude: float | None = None,
) -> Any:
    """Check in. Closes any existing open check-in first."""
    # close any open check-in
    open_row = session.exec(
        select(CheckIn).where(CheckIn.user_id == current_user.id, CheckIn.checked_out_at == None)  # noqa: E711
    ).first()
    if open_row:
        open_row.checked_out_at = datetime.now(timezone.utc)
        session.add(open_row)

    row = CheckIn(user_id=current_user.id, latitude=latitude, longitude=longitude)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.post("/checkout", response_model=CheckInPublic)
def check_out(*, session: SessionDep, current_user: CurrentUser) -> Any:
    """Check out of the current active check-in."""
    row = session.exec(
        select(CheckIn).where(CheckIn.user_id == current_user.id, CheckIn.checked_out_at == None)  # noqa: E711
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="No active check-in found.")
    row.checked_out_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
