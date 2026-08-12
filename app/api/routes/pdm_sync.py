"""
PDM sync service — pulls from mock PDM API and upserts into pdm_beneficiaries / pdm_disbursements.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import CurrentUser, SessionDep, require_roles
from app.api.routes.mock_pdm import _load_json
from app.models import UserRole

router = APIRouter(prefix="/pdm/sync", tags=["pdm-sync"])

SYNC_ROLES = (UserRole.HQ_ADMIN, UserRole.DG)


@router.post("/", dependencies=[require_roles(*SYNC_ROLES)])
async def trigger_sync(session: SessionDep) -> Any:
    started_at = datetime.now(timezone.utc)

    beneficiaries = _load_json("beneficiaries.json")
    disbursements = _load_json("disbursements.json")

    ben_count = 0
    for item in beneficiaries:
        session.execute(
            text("""
                insert into pdm_beneficiaries (
                    external_beneficiary_id, full_name, phone_number, national_id,
                    district, sub_county, parish, program_type, enterprise,
                    raw_payload, last_synced_at, updated_at
                ) values (
                    :external_id, :full_name, :phone_number, :national_id,
                    :district, :sub_county, :parish, :program_type, :enterprise,
                    cast(:raw_payload as jsonb), now(), now()
                )
                on conflict (external_beneficiary_id) do update set
                    full_name = excluded.full_name,
                    phone_number = excluded.phone_number,
                    national_id = excluded.national_id,
                    district = excluded.district,
                    sub_county = excluded.sub_county,
                    parish = excluded.parish,
                    program_type = excluded.program_type,
                    enterprise = excluded.enterprise,
                    raw_payload = excluded.raw_payload,
                    last_synced_at = now(),
                    updated_at = now()
            """),
            {
                "external_id": item["external_id"],
                "full_name": item["full_name"],
                "phone_number": item.get("phone_number"),
                "national_id": item.get("national_id"),
                "district": item.get("district"),
                "sub_county": item.get("sub_county"),
                "parish": item.get("parish"),
                "program_type": item.get("program_type"),
                "enterprise": item.get("enterprise"),
                "raw_payload": json.dumps(item),
            },
        )
        ben_count += 1

    dis_count = 0
    for item in disbursements:
        session.execute(
            text("""
                insert into pdm_disbursements (
                    external_disbursement_id, beneficiary_id, beneficiary_external_id,
                    amount, currency, disbursement_date, status,
                    raw_payload, last_synced_at, updated_at
                )
                select
                    :external_id, b.id, :beneficiary_external_id,
                    :amount, :currency, :disbursement_date, :status,
                    cast(:raw_payload as jsonb), now(), now()
                from pdm_beneficiaries b
                where b.external_beneficiary_id = :beneficiary_external_id
                on conflict (external_disbursement_id) do update set
                    beneficiary_id = excluded.beneficiary_id,
                    beneficiary_external_id = excluded.beneficiary_external_id,
                    amount = excluded.amount,
                    currency = excluded.currency,
                    disbursement_date = excluded.disbursement_date,
                    status = excluded.status,
                    raw_payload = excluded.raw_payload,
                    last_synced_at = now(),
                    updated_at = now()
            """),
            {
                "external_id": item["external_id"],
                "beneficiary_external_id": item["beneficiary_external_id"],
                "amount": item["amount"],
                "currency": item.get("currency", "UGX"),
                "disbursement_date": item.get("disbursement_date"),
                "status": item.get("status"),
                "raw_payload": json.dumps(item),
            },
        )
        dis_count += 1

    ended_at = datetime.now(timezone.utc)
    session.execute(
        text("""
            insert into pdm_sync_logs (source_name, sync_type, status, records_processed, started_at, ended_at, details)
            values (:source_name, :sync_type, :status, :records_processed, :started_at, :ended_at, cast(:details as jsonb))
        """),
        {
            "source_name": "mock_pdm",
            "sync_type": "FULL",
            "status": "SUCCESS",
            "records_processed": ben_count + dis_count,
            "started_at": started_at,
            "ended_at": ended_at,
            "details": json.dumps({"beneficiaries": ben_count, "disbursements": dis_count}),
        },
    )
    session.commit()

    return {
        "success": True,
        "beneficiaries_synced": ben_count,
        "disbursements_synced": dis_count,
    }


@router.get("/status")
def sync_status(session: SessionDep, current_user: CurrentUser) -> Any:
    result = session.execute(
        text("select * from pdm_sync_logs order by started_at desc limit 1")
    ).first()
    if not result:
        return {"last_sync": None}
    return {"last_sync": dict(result._mapping)}


@router.get("/beneficiaries", dependencies=[require_roles(*SYNC_ROLES)])
def list_synced_beneficiaries(
    session: SessionDep,
    search: str | None = None,
    district: str | None = None,
    program_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> Any:
    where_clauses = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if search:
        where_clauses.append("(full_name ilike :search or national_id ilike :search)")
        params["search"] = f"%{search}%"
    if district:
        where_clauses.append("district = :district")
        params["district"] = district
    if program_type:
        where_clauses.append("program_type = :program_type")
        params["program_type"] = program_type
    where = ("where " + " and ".join(where_clauses)) if where_clauses else ""
    rows = session.execute(
        text(f"select * from pdm_beneficiaries {where} order by full_name limit :limit offset :offset").bindparams(**params)
    ).all()
    count_row = session.execute(
        text(f"select count(*) from pdm_beneficiaries {where}").bindparams(
            **{k: v for k, v in params.items() if k not in ("limit", "offset")}
        )
    ).first()
    return {"data": [dict(r._mapping) for r in rows], "count": count_row[0] if count_row else 0}


@router.get("/disbursements", dependencies=[require_roles(*SYNC_ROLES)])
def list_synced_disbursements(
    session: SessionDep,
    beneficiary_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> Any:
    where = "where beneficiary_id = :bid" if beneficiary_id else ""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if beneficiary_id:
        params["bid"] = beneficiary_id
    rows = session.execute(
        text(f"select * from pdm_disbursements {where} order by disbursement_date desc limit :limit offset :offset").bindparams(**params)
    ).all()
    return {"data": [dict(r._mapping) for r in rows]}
