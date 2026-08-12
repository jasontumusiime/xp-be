from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID
from fastapi import APIRouter, Query
from sqlmodel import select, func

from app.api.deps import CurrentUser, SessionDep
from app.models import GpsLog, Report, ReportStatus, Task, TaskStatus, User, UserRole, UserStatus

router = APIRouter(prefix="/analytics", tags=["analytics"])

_AGENT_ONLINE_THRESHOLD_SECONDS = 90


def _pct_change(current: int, previous: int) -> float | None:
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


@router.get("/dashboard")
def dashboard_stats(
    session: SessionDep,
    current_user: CurrentUser,
    region_id: UUID | None = Query(default=None),
    sector_id: UUID | None = Query(default=None),
    district_id: UUID | None = Query(default=None),
    parish_id: UUID | None = Query(default=None),
    category_id: UUID | None = Query(default=None),
    date_from: str | None = Query(default=None, description="ISO date YYYY-MM-DD"),
    date_to: str | None = Query(default=None, description="ISO date YYYY-MM-DD"),
) -> Any:
    from app.models import SubCategory, District, County, SubCounty, Parish, Category, Sector

    # Determine current window
    now = datetime.now(timezone.utc)
    if date_from and date_to:
        window_start = datetime.fromisoformat(date_from)
        window_end = datetime.fromisoformat(date_to) + timedelta(days=1)
    else:
        window_end = now
        window_start = now - timedelta(days=7)

    window_len = window_end - window_start
    prev_start = window_start - window_len
    prev_end = window_start

    # Resolve any geo filter down to parish IDs (most specific wins)
    _filtered_parish_ids: list[UUID] | None = None
    if parish_id:
        _filtered_parish_ids = [parish_id]
    elif district_id:
        county_ids = session.exec(select(County.id).where(County.district_id == district_id)).all()
        subcounty_ids = session.exec(select(SubCounty.id).where(SubCounty.county_id.in_(county_ids))).all()
        _filtered_parish_ids = session.exec(select(Parish.id).where(Parish.subcounty_id.in_(subcounty_ids))).all()
    elif sector_id:
        district_ids = session.exec(select(District.id).where(District.sector_id == sector_id)).all()
        county_ids = session.exec(select(County.id).where(County.district_id.in_(district_ids))).all()
        subcounty_ids = session.exec(select(SubCounty.id).where(SubCounty.county_id.in_(county_ids))).all()
        _filtered_parish_ids = session.exec(select(Parish.id).where(Parish.subcounty_id.in_(subcounty_ids))).all()
    elif region_id:
        sector_ids = session.exec(select(Sector.id).where(Sector.region_id == region_id)).all()
        district_ids = session.exec(select(District.id).where(District.sector_id.in_(sector_ids))).all()
        county_ids = session.exec(select(County.id).where(County.district_id.in_(district_ids))).all()
        subcounty_ids = session.exec(select(SubCounty.id).where(SubCounty.county_id.in_(county_ids))).all()
        _filtered_parish_ids = session.exec(select(Parish.id).where(Parish.subcounty_id.in_(subcounty_ids))).all()

    def _report_filters(q, start=None, end=None):
        s = start or window_start
        e = end or window_end
        if _filtered_parish_ids is not None:
            q = q.where(Report.parish_id.in_(_filtered_parish_ids))
        if category_id:
            sub_ids = session.exec(select(SubCategory.id).where(SubCategory.category_id == category_id)).all()
            q = q.where(Report.subcategory_id.in_(sub_ids))
        q = q.where(Report.created_at >= s).where(Report.created_at < e)
        return q

    # Current period counts
    total_reports = session.exec(_report_filters(select(func.count()).select_from(Report))).one()
    by_status = {
        s.value: session.exec(
            _report_filters(select(func.count()).select_from(Report).where(Report.status == s))
        ).one()
        for s in ReportStatus
    }

    # Previous period counts for % change
    prev_total = session.exec(_report_filters(select(func.count()).select_from(Report), prev_start, prev_end)).one()
    prev_by_status = {
        s.value: session.exec(
            _report_filters(select(func.count()).select_from(Report).where(Report.status == s), prev_start, prev_end)
        ).one()
        for s in ReportStatus
    }

    # Agents online
    cutoff = now - timedelta(seconds=_AGENT_ONLINE_THRESHOLD_SECONDS)
    prev_cutoff = cutoff - window_len
    agents_online = len(session.exec(select(GpsLog.agent_id).where(GpsLog.recorded_at >= cutoff).distinct()).all())
    prev_agents_online = len(session.exec(select(GpsLog.agent_id).where(GpsLog.recorded_at >= prev_cutoff, GpsLog.recorded_at < cutoff).distinct()).all())

    total_tasks = session.exec(select(func.count()).select_from(Task)).one()
    pending_tasks = session.exec(select(func.count()).select_from(Task).where(Task.status == TaskStatus.PENDING)).one()

    # Reports over time (current window, grouped by day)
    rows = session.exec(
        _report_filters(
            select(func.date(Report.created_at).label("day"), func.count().label("count"))
        )
        .group_by(func.date(Report.created_at))
        .order_by(func.date(Report.created_at))
    ).all()
    reports_over_time = [{"day": str(r.day), "count": r.count} for r in rows]

    # Reports by category
    cat_rows = session.exec(
        _report_filters(
            select(SubCategory.name, func.count(Report.id).label("count"))
            .join(Report, Report.subcategory_id == SubCategory.id)
            .group_by(SubCategory.name)
            .order_by(func.count(Report.id).desc())
            .limit(10)
        )
    ).all()
    reports_by_category = [{"name": r.name, "count": r.count} for r in cat_rows]

    # Recent alerts
    recent_rows = session.exec(
        _report_filters(
            select(Report, SubCategory.name.label("subcat_name"), Parish.name.label("parish_name"))
            .join(SubCategory, Report.subcategory_id == SubCategory.id)
            .outerjoin(Parish, Report.parish_id == Parish.id)
            .where(Report.status.in_([ReportStatus.ESCALATED, ReportStatus.SUBMITTED]))
            .order_by(Report.created_at.desc())
            .limit(10)
        )
    ).all()
    recent_alerts = [
        {
            "id": str(r.Report.id),
            "title": r.Report.title,
            "status": r.Report.status.value,
            "subcategory": r.subcat_name,
            "location": r.parish_name or "Unknown",
            "created_at": r.Report.created_at.isoformat() if r.Report.created_at else None,
        }
        for r in recent_rows
    ]

    # Top affected districts with % change
    def _district_counts(start, end):
        rows = session.exec(
            select(District.id, District.name, func.count(Report.id).label("count"))
            .join(County, County.district_id == District.id)
            .join(SubCounty, SubCounty.county_id == County.id)
            .join(Parish, Parish.subcounty_id == SubCounty.id)
            .join(Report, Report.parish_id == Parish.id)
            .where(Report.created_at >= start, Report.created_at < end)
            .group_by(District.id, District.name)
            .order_by(func.count(Report.id).desc())
            .limit(5)
        ).all()
        return {r.name: r.count for r in rows}, [{"district": r.name, "count": r.count} for r in rows]

    prev_district_map, _ = _district_counts(prev_start, prev_end)
    _, top_districts_cur = _district_counts(window_start, window_end)
    top_districts = [
        {
            "district": d["district"],
            "count": d["count"],
            "change": _pct_change(d["count"], prev_district_map.get(d["district"], 0)),
        }
        for d in top_districts_cur
    ]

    return {
        "total_reports": total_reports,
        "total_reports_change": _pct_change(total_reports, prev_total),
        "reports_by_status": by_status,
        "reports_by_status_change": {k: _pct_change(by_status[k], prev_by_status[k]) for k in by_status},
        "total_tasks": total_tasks,
        "pending_tasks": pending_tasks,
        "agents_online": agents_online,
        "agents_online_change": _pct_change(agents_online, prev_agents_online),
        "reports_over_time": reports_over_time,
        "reports_by_category": reports_by_category,
        "recent_alerts": recent_alerts,
        "top_districts": top_districts,
    }
