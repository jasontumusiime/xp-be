import uuid
from typing import Any
from fastapi import APIRouter, HTTPException
from sqlmodel import select
from pydantic import BaseModel

from app.api.deps import SessionDep, require_roles
from app.models import (
    Region, RegionPublic,
    Sector, SectorPublic,
    District, DistrictPublic,
    County, CountyPublic,
    SubCounty, SubCountyPublic,
    Parish, ParishPublic,
    Village, VillagePublic,
    UserRole,
)

router = APIRouter(prefix="/geographical", tags=["geographical"])


# --- Request schemas ---

class RegionCreate(BaseModel):
    name: str

class SectorCreate(BaseModel):
    name: str
    region_id: uuid.UUID

class DistrictCreate(BaseModel):
    name: str
    sector_id: uuid.UUID

class CountyCreate(BaseModel):
    name: str
    district_id: uuid.UUID

class SubCountyCreate(BaseModel):
    name: str
    county_id: uuid.UUID

class ParishCreate(BaseModel):
    name: str
    subcounty_id: uuid.UUID

class VillageCreate(BaseModel):
    name: str
    parish_id: uuid.UUID


# --- Paginated response helpers ---

class RegionsPublic(BaseModel):
    data: list[RegionPublic]
    count: int

class SectorsPublic(BaseModel):
    data: list[SectorPublic]
    count: int

class DistrictsPublic(BaseModel):
    data: list[DistrictPublic]
    count: int

class CountiesPublic(BaseModel):
    data: list[CountyPublic]
    count: int

class SubCountiesPublic(BaseModel):
    data: list[SubCountyPublic]
    count: int

class ParishesPublic(BaseModel):
    data: list[ParishPublic]
    count: int

class VillagesPublic(BaseModel):
    data: list[VillagePublic]
    count: int


# ── Regions ──────────────────────────────────────────────

@router.get("/regions", response_model=RegionsPublic)
def list_regions(session: SessionDep) -> Any:
    items = session.exec(select(Region).order_by(Region.name)).all()
    return RegionsPublic(data=items, count=len(items))

@router.post("/regions", response_model=RegionPublic, dependencies=[require_roles(UserRole.HQ_ADMIN)])
def create_region(*, session: SessionDep, body: RegionCreate) -> Any:
    if session.exec(select(Region).where(Region.name == body.name)).first():
        raise HTTPException(status_code=409, detail="Region already exists.")
    region = Region(name=body.name)
    session.add(region)
    session.commit()
    session.refresh(region)
    return region

@router.delete("/regions/{region_id}", dependencies=[require_roles(UserRole.HQ_ADMIN)])
def delete_region(*, session: SessionDep, region_id: uuid.UUID) -> Any:
    region = session.get(Region, region_id)
    if not region:
        raise HTTPException(status_code=404, detail="Region not found.")
    session.delete(region)
    session.commit()
    return {"message": "Deleted successfully"}


# ── Sectors ───────────────────────────────────────────────

@router.get("/sectors", response_model=SectorsPublic)
def list_sectors(session: SessionDep, region_id: uuid.UUID | None = None) -> Any:
    q = select(Sector).order_by(Sector.name)
    if region_id:
        q = q.where(Sector.region_id == region_id)
    items = session.exec(q).all()
    return SectorsPublic(data=items, count=len(items))

@router.post("/sectors", response_model=SectorPublic, dependencies=[require_roles(UserRole.HQ_ADMIN)])
def create_sector(*, session: SessionDep, body: SectorCreate) -> Any:
    if not session.get(Region, body.region_id):
        raise HTTPException(status_code=404, detail="Region not found.")
    if session.exec(select(Sector).where(Sector.name == body.name, Sector.region_id == body.region_id)).first():
        raise HTTPException(status_code=409, detail="Sector already exists in this region.")
    obj = Sector(name=body.name, region_id=body.region_id)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj

@router.delete("/sectors/{sector_id}", dependencies=[require_roles(UserRole.HQ_ADMIN)])
def delete_sector(*, session: SessionDep, sector_id: uuid.UUID) -> Any:
    obj = session.get(Sector, sector_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Sector not found.")
    session.delete(obj)
    session.commit()
    return {"message": "Deleted successfully"}


# ── Districts ─────────────────────────────────────────────

@router.get("/districts", response_model=DistrictsPublic)
def list_districts(session: SessionDep, sector_id: uuid.UUID | None = None) -> Any:
    q = select(District).order_by(District.name)
    if sector_id:
        q = q.where(District.sector_id == sector_id)
    items = session.exec(q).all()
    return DistrictsPublic(data=items, count=len(items))

@router.post("/districts", response_model=DistrictPublic, dependencies=[require_roles(UserRole.HQ_ADMIN)])
def create_district(*, session: SessionDep, body: DistrictCreate) -> Any:
    if not session.get(Sector, body.sector_id):
        raise HTTPException(status_code=404, detail="Sector not found.")
    if session.exec(select(District).where(District.name == body.name, District.sector_id == body.sector_id)).first():
        raise HTTPException(status_code=409, detail="District already exists in this sector.")
    obj = District(name=body.name, sector_id=body.sector_id)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj

@router.delete("/districts/{district_id}", dependencies=[require_roles(UserRole.HQ_ADMIN)])
def delete_district(*, session: SessionDep, district_id: uuid.UUID) -> Any:
    obj = session.get(District, district_id)
    if not obj:
        raise HTTPException(status_code=404, detail="District not found.")
    session.delete(obj)
    session.commit()
    return {"message": "Deleted successfully"}


# ── Counties ──────────────────────────────────────────────

@router.get("/counties", response_model=CountiesPublic)
def list_counties(session: SessionDep, district_id: uuid.UUID | None = None) -> Any:
    q = select(County).order_by(County.name)
    if district_id:
        q = q.where(County.district_id == district_id)
    items = session.exec(q).all()
    return CountiesPublic(data=items, count=len(items))

@router.post("/counties", response_model=CountyPublic, dependencies=[require_roles(UserRole.HQ_ADMIN)])
def create_county(*, session: SessionDep, body: CountyCreate) -> Any:
    if not session.get(District, body.district_id):
        raise HTTPException(status_code=404, detail="District not found.")
    if session.exec(select(County).where(County.name == body.name, County.district_id == body.district_id)).first():
        raise HTTPException(status_code=409, detail="County already exists in this district.")
    obj = County(name=body.name, district_id=body.district_id)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj

@router.delete("/counties/{county_id}", dependencies=[require_roles(UserRole.HQ_ADMIN)])
def delete_county(*, session: SessionDep, county_id: uuid.UUID) -> Any:
    obj = session.get(County, county_id)
    if not obj:
        raise HTTPException(status_code=404, detail="County not found.")
    session.delete(obj)
    session.commit()
    return {"message": "Deleted successfully"}


# ── SubCounties ───────────────────────────────────────────

@router.get("/subcounties", response_model=SubCountiesPublic)
def list_subcounties(session: SessionDep, county_id: uuid.UUID | None = None) -> Any:
    q = select(SubCounty).order_by(SubCounty.name)
    if county_id:
        q = q.where(SubCounty.county_id == county_id)
    items = session.exec(q).all()
    return SubCountiesPublic(data=items, count=len(items))

@router.post("/subcounties", response_model=SubCountyPublic, dependencies=[require_roles(UserRole.HQ_ADMIN)])
def create_subcounty(*, session: SessionDep, body: SubCountyCreate) -> Any:
    if not session.get(County, body.county_id):
        raise HTTPException(status_code=404, detail="County not found.")
    if session.exec(select(SubCounty).where(SubCounty.name == body.name, SubCounty.county_id == body.county_id)).first():
        raise HTTPException(status_code=409, detail="SubCounty already exists in this county.")
    obj = SubCounty(name=body.name, county_id=body.county_id)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj

@router.delete("/subcounties/{subcounty_id}", dependencies=[require_roles(UserRole.HQ_ADMIN)])
def delete_subcounty(*, session: SessionDep, subcounty_id: uuid.UUID) -> Any:
    obj = session.get(SubCounty, subcounty_id)
    if not obj:
        raise HTTPException(status_code=404, detail="SubCounty not found.")
    session.delete(obj)
    session.commit()
    return {"message": "Deleted successfully"}


# ── Parishes ──────────────────────────────────────────────

@router.get("/parishes", response_model=ParishesPublic)
def list_parishes(session: SessionDep, subcounty_id: uuid.UUID | None = None) -> Any:
    q = select(Parish).order_by(Parish.name)
    if subcounty_id:
        q = q.where(Parish.subcounty_id == subcounty_id)
    items = session.exec(q).all()
    return ParishesPublic(data=items, count=len(items))

@router.get("/parishes/{parish_id}", response_model=ParishPublic)
def get_parish(*, session: SessionDep, parish_id: uuid.UUID) -> Any:
    parish = session.get(Parish, parish_id)
    if not parish:
        raise HTTPException(status_code=404, detail="Parish not found.")
    return parish

@router.post("/parishes", response_model=ParishPublic, dependencies=[require_roles(UserRole.HQ_ADMIN)])
def create_parish(*, session: SessionDep, body: ParishCreate) -> Any:
    if not session.get(SubCounty, body.subcounty_id):
        raise HTTPException(status_code=404, detail="SubCounty not found.")
    if session.exec(select(Parish).where(Parish.name == body.name, Parish.subcounty_id == body.subcounty_id)).first():
        raise HTTPException(status_code=409, detail="Parish already exists in this subcounty.")
    obj = Parish(name=body.name, subcounty_id=body.subcounty_id)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj

@router.delete("/parishes/{parish_id}", dependencies=[require_roles(UserRole.HQ_ADMIN)])
def delete_parish(*, session: SessionDep, parish_id: uuid.UUID) -> Any:
    obj = session.get(Parish, parish_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Parish not found.")
    session.delete(obj)
    session.commit()
    return {"message": "Deleted successfully"}


# ── Villages ──────────────────────────────────────────────

@router.get("/villages", response_model=VillagesPublic)
def list_villages(session: SessionDep, parish_id: uuid.UUID | None = None) -> Any:
    q = select(Village).order_by(Village.name)
    if parish_id:
        q = q.where(Village.parish_id == parish_id)
    items = session.exec(q).all()
    return VillagesPublic(data=items, count=len(items))

@router.post("/villages", response_model=VillagePublic, dependencies=[require_roles(UserRole.HQ_ADMIN)])
def create_village(*, session: SessionDep, body: VillageCreate) -> Any:
    if not session.get(Parish, body.parish_id):
        raise HTTPException(status_code=404, detail="Parish not found.")
    if session.exec(select(Village).where(Village.name == body.name, Village.parish_id == body.parish_id)).first():
        raise HTTPException(status_code=409, detail="Village already exists in this parish.")
    obj = Village(name=body.name, parish_id=body.parish_id)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj

@router.delete("/villages/{village_id}", dependencies=[require_roles(UserRole.HQ_ADMIN)])
def delete_village(*, session: SessionDep, village_id: uuid.UUID) -> Any:
    obj = session.get(Village, village_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Village not found.")
    session.delete(obj)
    session.commit()
    return {"message": "Deleted successfully"}
