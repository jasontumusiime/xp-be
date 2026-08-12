import uuid
from typing import Any
from fastapi import APIRouter, HTTPException
from sqlmodel import select, func, col, or_

from app.api.deps import CurrentUser, SessionDep, require_roles
from app.models import (
    Beneficiary, BeneficiaryCreate, BeneficiaryUpdate,
    BeneficiaryPublic, BeneficiariesPublic, BeneficiaryStatus,
    Disbursement, DisbursementCreate, DisbursementUpdate,
    DisbursementPublic, DisbursementsPublic, DisbursementStatus,
    UserRole, get_datetime_utc,
)

router = APIRouter(prefix="/pdm", tags=["pdm"])

PDM_ROLES = (UserRole.HQ_ADMIN, UserRole.DG, UserRole.RISO, UserRole.SISO, UserRole.DISO, UserRole.GISO)


# ── Beneficiaries ─────────────────────────────────────────

@router.get("/beneficiaries", response_model=BeneficiariesPublic, dependencies=[require_roles(*PDM_ROLES)])
def list_beneficiaries(
    session: SessionDep,
    skip: int = 0,
    limit: int = 100,
    search: str | None = None,
    status: BeneficiaryStatus | None = None,
    parish_id: uuid.UUID | None = None,
) -> Any:
    q = select(Beneficiary)
    if search:
        q = q.where(or_(
            Beneficiary.full_name.ilike(f"%{search}%"),
            Beneficiary.national_id.ilike(f"%{search}%"),
        ))
    if status:
        q = q.where(Beneficiary.status == status)
    if parish_id:
        q = q.where(Beneficiary.parish_id == parish_id)
    count = session.exec(select(func.count()).select_from(q.subquery())).one()
    items = session.exec(q.order_by(col(Beneficiary.created_at).desc()).offset(skip).limit(limit)).all()
    return BeneficiariesPublic(data=[BeneficiaryPublic.model_validate(b) for b in items], count=count)


@router.post("/beneficiaries", response_model=BeneficiaryPublic, dependencies=[require_roles(*PDM_ROLES)])
def create_beneficiary(*, session: SessionDep, body: BeneficiaryCreate) -> Any:
    if session.exec(select(Beneficiary).where(Beneficiary.national_id == body.national_id)).first():
        raise HTTPException(status_code=409, detail="Beneficiary with this national ID already exists.")
    b = Beneficiary(**body.model_dump())
    session.add(b)
    session.commit()
    session.refresh(b)
    return b


@router.patch("/beneficiaries/{beneficiary_id}", response_model=BeneficiaryPublic, dependencies=[require_roles(*PDM_ROLES)])
def update_beneficiary(*, session: SessionDep, current_user: CurrentUser, beneficiary_id: uuid.UUID, body: BeneficiaryUpdate) -> Any:
    b = session.get(Beneficiary, beneficiary_id)
    if not b:
        raise HTTPException(status_code=404, detail="Beneficiary not found.")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] == BeneficiaryStatus.VERIFIED:
        data["verified_by"] = current_user.id
    for field, value in data.items():
        setattr(b, field, value)
    session.add(b)
    session.commit()
    session.refresh(b)
    return b


@router.get("/beneficiaries/{beneficiary_id}", response_model=BeneficiaryPublic, dependencies=[require_roles(*PDM_ROLES)])
def get_beneficiary(*, session: SessionDep, beneficiary_id: uuid.UUID) -> Any:
    b = session.get(Beneficiary, beneficiary_id)
    if not b:
        raise HTTPException(status_code=404, detail="Beneficiary not found.")
    return b


# ── Disbursements ─────────────────────────────────────────

@router.get("/disbursements", response_model=DisbursementsPublic, dependencies=[require_roles(*PDM_ROLES)])
def list_disbursements(
    session: SessionDep,
    skip: int = 0,
    limit: int = 100,
    beneficiary_id: uuid.UUID | None = None,
    status: DisbursementStatus | None = None,
) -> Any:
    q = select(Disbursement)
    if beneficiary_id:
        q = q.where(Disbursement.beneficiary_id == beneficiary_id)
    if status:
        q = q.where(Disbursement.status == status)
    count = session.exec(select(func.count()).select_from(q.subquery())).one()
    items = session.exec(q.order_by(col(Disbursement.created_at).desc()).offset(skip).limit(limit)).all()
    return DisbursementsPublic(data=[DisbursementPublic.model_validate(d) for d in items], count=count)


@router.post("/disbursements", response_model=DisbursementPublic, dependencies=[require_roles(*PDM_ROLES)])
def create_disbursement(*, session: SessionDep, body: DisbursementCreate) -> Any:
    if not session.get(Beneficiary, body.beneficiary_id):
        raise HTTPException(status_code=404, detail="Beneficiary not found.")
    d = Disbursement(**body.model_dump())
    session.add(d)
    session.commit()
    session.refresh(d)
    return d


@router.patch("/disbursements/{disbursement_id}", response_model=DisbursementPublic, dependencies=[require_roles(*PDM_ROLES)])
def update_disbursement(*, session: SessionDep, current_user: CurrentUser, disbursement_id: uuid.UUID, body: DisbursementUpdate) -> Any:
    d = session.get(Disbursement, disbursement_id)
    if not d:
        raise HTTPException(status_code=404, detail="Disbursement not found.")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] == DisbursementStatus.DISBURSED:
        data["disbursed_by"] = current_user.id
        data["disbursed_at"] = get_datetime_utc()
    for field, value in data.items():
        setattr(d, field, value)
    session.add(d)
    session.commit()
    session.refresh(d)
    return d


# ── Verifications ─────────────────────────────────────────

@router.get("/verifications", dependencies=[require_roles(*PDM_ROLES)])
def list_verifications(
    session: SessionDep,
    skip: int = 0,
    limit: int = 100,
    search: str | None = None,
    status: BeneficiaryStatus | None = None,
) -> Any:
    from app.models import User
    q = select(Beneficiary)
    if search:
        q = q.where(or_(
            Beneficiary.full_name.ilike(f"%{search}%"),
            Beneficiary.national_id.ilike(f"%{search}%"),
        ))
    if status:
        q = q.where(Beneficiary.status == status)
    count = session.exec(select(func.count()).select_from(q.subquery())).one()
    items = session.exec(q.order_by(col(Beneficiary.created_at).desc()).offset(skip).limit(limit)).all()

    result = []
    for b in items:
        disbs = session.exec(select(Disbursement).where(Disbursement.beneficiary_id == b.id)).all()
        total_disbursed = sum(d.amount for d in disbs if d.status == DisbursementStatus.DISBURSED)
        verified_by_name = None
        if b.verified_by:
            verifier = session.get(User, b.verified_by)
            verified_by_name = verifier.full_name or verifier.email if verifier else None
        result.append({
            **BeneficiaryPublic.model_validate(b).model_dump(),
            "disbursement_count": len(disbs),
            "total_disbursed": total_disbursed,
            "verified_by_name": verified_by_name,
        })
    return {"data": result, "count": count}


@router.post("/beneficiaries/{beneficiary_id}/flag", dependencies=[require_roles(*PDM_ROLES)])
def flag_beneficiary(*, session: SessionDep, current_user: CurrentUser, beneficiary_id: uuid.UUID, body: dict) -> Any:
    b = session.get(Beneficiary, beneficiary_id)
    if not b:
        raise HTTPException(status_code=404, detail="Beneficiary not found.")
    b.status = BeneficiaryStatus.FLAGGED
    b.notes = body.get("reason", "")
    session.add(b)
    session.commit()
    session.refresh(b)
    return BeneficiaryPublic.model_validate(b)
