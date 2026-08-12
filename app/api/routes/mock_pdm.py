from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/mock/pdm", tags=["mock-pdm"])

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "pdm"


def _load_json(name: str) -> list[dict[str, Any]]:
    with open(DATA_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


class ApiResponse(BaseModel):
    success: bool
    data: list[dict[str, Any]]
    meta: dict[str, Any]


@router.get("/beneficiaries", response_model=ApiResponse)
async def get_mock_beneficiaries() -> ApiResponse:
    data = _load_json("beneficiaries.json")
    return ApiResponse(
        success=True,
        data=data,
        meta={"source": "mock_pdm", "entity": "beneficiaries", "synced_at": datetime.now(timezone.utc).isoformat(), "record_count": len(data)},
    )


@router.get("/disbursements", response_model=ApiResponse)
async def get_mock_disbursements() -> ApiResponse:
    data = _load_json("disbursements.json")
    return ApiResponse(
        success=True,
        data=data,
        meta={"source": "mock_pdm", "entity": "disbursements", "synced_at": datetime.now(timezone.utc).isoformat(), "record_count": len(data)},
    )
