import uuid
from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from sqlmodel import select, func, col

from app.api.deps import CurrentUser, SessionDep, require_roles
from app.core.config import settings
from app.models import (
    Report, ReportCreate, ReportUpdate, ReportPublic, ReportsPublic,
    ReportStatus, UserRole, AuditLog,
)

router = APIRouter(prefix="/reports", tags=["reports"])

ALLOWED_TYPES: dict[str, set[str]] = {
    "photo": {"jpg", "jpeg", "png", "webp"},
    "video": {"mp4", "mov", "avi"},
    "voice": {"m4a", "mp3", "wav", "aac"},
    "document": {"pdf", "doc", "docx"},
}

ADMIN_ROLES = (
    UserRole.HQ_ADMIN, UserRole.DG, UserRole.RISO,
    UserRole.SISO, UserRole.DISO, UserRole.GISO,
)


@router.get("/", response_model=ReportsPublic)
def list_reports(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
    status: ReportStatus | None = None,
    program_type: str | None = None,
    pdm_beneficiary_id: uuid.UUID | None = None,
    pdm_disbursement_id: uuid.UUID | None = None,
) -> Any:
    from app.jurisdiction import get_agent_ids_in_jurisdiction
    q = select(Report)

    agent_ids = get_agent_ids_in_jurisdiction(session, current_user)
    if agent_ids is not None:
        q = q.where(Report.submitted_by.in_(agent_ids))

    if status:
        q = q.where(Report.status == status)
    if program_type:
        q = q.where(Report.program_type == program_type.upper())
    if pdm_beneficiary_id:
        q = q.where(Report.pdm_beneficiary_id == pdm_beneficiary_id)
    if pdm_disbursement_id:
        q = q.where(Report.pdm_disbursement_id == pdm_disbursement_id)

    count = session.exec(select(func.count()).select_from(q.subquery())).one()
    reports = session.exec(q.order_by(col(Report.created_at).desc()).offset(skip).limit(limit)).all()
    return ReportsPublic(data=[ReportPublic.model_validate(r) for r in reports], count=count)


@router.post("/", response_model=ReportPublic)
def create_report(*, session: SessionDep, current_user: CurrentUser, body: ReportCreate) -> Any:
    report = Report(
        **body.model_dump(),
        submitted_by=current_user.id,
        status=ReportStatus.SUBMITTED,
    )
    session.add(report)
    session.commit()
    session.refresh(report)

    from app.api.routes.notifications import create_notification
    from app.models import NotificationType, User

    # Notify direct supervisor (GISO in same parish)
    if current_user.geographical_id:
        supervisor = session.exec(
            select(User).where(
                User.geographical_id == current_user.geographical_id,
                User.role == UserRole.GISO,
            )
        ).first()
        if supervisor:
            create_notification(
                session, supervisor.id, NotificationType.REPORT,
                "New Report Submitted",
                f"{current_user.full_name or current_user.email} submitted: {report.title}",
            )

    # For PDM reports, also notify all PDM-role users
    if report.program_type == "PDM":
        pdm_roles = (UserRole.HQ_ADMIN, UserRole.DG, UserRole.RISO, UserRole.SISO, UserRole.DISO, UserRole.GISO)
        admins = session.exec(select(User).where(User.role.in_(pdm_roles))).all()
        for admin in admins:
            if admin.id != current_user.id and (not supervisor or admin.id != supervisor.id):
                create_notification(
                    session, admin.id, NotificationType.REPORT,
                    "PDM Report Submitted",
                    f"{current_user.full_name or current_user.email} submitted PDM report: {report.title}",
                )

    session.commit()
    return report


@router.get("/{report_id}", response_model=ReportPublic)
def get_report(*, session: SessionDep, current_user: CurrentUser, report_id: uuid.UUID) -> Any:
    from app.jurisdiction import get_agent_ids_in_jurisdiction
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    agent_ids = get_agent_ids_in_jurisdiction(session, current_user)
    if agent_ids is not None and report.submitted_by not in agent_ids:
        raise HTTPException(status_code=403, detail="Access denied.")
    return report


@router.patch("/{report_id}", response_model=ReportPublic)
def update_report(
    *, session: SessionDep, current_user: CurrentUser,
    report_id: uuid.UUID, body: ReportUpdate,
) -> Any:
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    # Agents can only update their own draft reports
    if current_user.role == UserRole.AGENT:
        if report.submitted_by != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied.")
        if report.status != ReportStatus.DRAFT:
            raise HTTPException(status_code=400, detail="Submitted reports cannot be edited.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(report, field, value)
    from app.models import get_datetime_utc
    report.updated_at = get_datetime_utc()
    session.add(report)
    # Audit log
    if "status" in body.model_dump(exclude_unset=True):
        session.add(AuditLog(
            actor_id=current_user.id,
            action="report.status_changed",
            entity_type="report",
            entity_id=report.id,
            detail=f"status → {report.status}",
        ))

    # When a PDM report is closed, update the linked disbursement's verification_status
    if (
        report.status == ReportStatus.CLOSED
        and report.program_type == "PDM"
        and report.pdm_disbursement_id
        and report.outcome in ("CONFIRMED", "DISPUTED")
    ):
        from sqlalchemy import text
        session.execute(
            text("UPDATE pdm_disbursements SET verification_status = :vs WHERE id = :id"),
            {"vs": report.outcome, "id": str(report.pdm_disbursement_id)},
        )

    session.commit()
    session.refresh(report)

    # Notify submitting agent when supervisor changes status
    if current_user.role != UserRole.AGENT and "status" in body.model_dump(exclude_unset=True):
        from app.api.routes.notifications import create_notification
        from app.models import NotificationType
        create_notification(
            session, report.submitted_by, NotificationType.REPORT,
            f"Report {report.title}",
            f"Status updated to {report.status.replace('_', ' ').title()}",
        )
        session.commit()

    return report


@router.post("/upload")
async def upload_evidence(
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
