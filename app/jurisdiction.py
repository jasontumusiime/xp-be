"""
Jurisdiction scoping helpers.

user.geographical_id → subcounty.id

Role → Intelligence scope (subcounty-based):
  HQ_ADMIN / DG  → entire country
  RISO           → all subcounties in their Region
  SISO           → all subcounties in their Sector
  DISO           → all subcounties in their District
  GISO           → their SubCounty
  AGENT          → self only

Role → PDM scope (parish-based, GISO manages parish/village):
  HQ_ADMIN / DG  → entire country
  RISO           → all parishes in their Region
  SISO           → all parishes in their Sector
  DISO           → all parishes in their District
  GISO           → all parishes in their SubCounty
  AGENT          → parishes in their SubCounty (same as GISO)
"""
from __future__ import annotations
import uuid
from sqlmodel import Session, select
from app.models import User, Parish, SubCounty, County, District, Sector, Region, UserRole


def _subcounty_ids_for_user(session: Session, current_user: User) -> list[uuid.UUID] | None:
    """
    Returns subcounty IDs visible to the user, or None meaning 'all'.
    Used internally by both intelligence and PDM scoping.
    """
    role = current_user.role
    geo = current_user.geographical_id  # subcounty id

    if role in (UserRole.HQ_ADMIN, UserRole.DG):
        return None

    if geo is None:
        return None

    subcounty = session.get(SubCounty, geo)
    if not subcounty:
        return []

    if role in (UserRole.GISO, UserRole.AGENT):
        return [subcounty.id]

    county = session.get(County, subcounty.county_id)
    if not county:
        return []

    district = session.get(District, county.district_id)
    if not district:
        return []

    if role == UserRole.DISO:
        county_ids = session.exec(select(County.id).where(County.district_id == district.id)).all()
        return session.exec(select(SubCounty.id).where(SubCounty.county_id.in_(county_ids))).all()

    sector = session.get(Sector, district.sector_id)
    if not sector:
        return []

    if role == UserRole.SISO:
        district_ids = session.exec(select(District.id).where(District.sector_id == sector.id)).all()
        county_ids = session.exec(select(County.id).where(County.district_id.in_(district_ids))).all()
        return session.exec(select(SubCounty.id).where(SubCounty.county_id.in_(county_ids))).all()

    region = session.get(Region, sector.region_id)
    if not region:
        return []

    if role == UserRole.RISO:
        sector_ids = session.exec(select(Sector.id).where(Sector.region_id == region.id)).all()
        district_ids = session.exec(select(District.id).where(District.sector_id.in_(sector_ids))).all()
        county_ids = session.exec(select(County.id).where(County.district_id.in_(district_ids))).all()
        return session.exec(select(SubCounty.id).where(SubCounty.county_id.in_(county_ids))).all()

    return None


def get_agent_ids_in_jurisdiction(session: Session, current_user: User) -> list[uuid.UUID] | None:
    """
    Intelligence scoping: returns agent User IDs visible to current_user.
    Returns None meaning 'all agents'.
    """
    if current_user.role in (UserRole.HQ_ADMIN, UserRole.DG):
        return None

    if current_user.role == UserRole.AGENT:
        return [current_user.id]

    subcounty_ids = _subcounty_ids_for_user(session, current_user)
    if subcounty_ids is None:
        return None

    return session.exec(
        select(User.id).where(
            User.geographical_id.in_(subcounty_ids),
            User.role == UserRole.AGENT,
        )
    ).all()


def get_parish_ids_in_jurisdiction(session: Session, current_user: User) -> list[uuid.UUID] | None:
    """
    PDM scoping: returns Parish IDs visible to current_user.
    Returns None meaning 'all parishes'.
    GISO manages all parishes within their SubCounty.
    """
    if current_user.role in (UserRole.HQ_ADMIN, UserRole.DG):
        return None

    subcounty_ids = _subcounty_ids_for_user(session, current_user)
    if subcounty_ids is None:
        return None

    return session.exec(
        select(Parish.id).where(Parish.subcounty_id.in_(subcounty_ids))
    ).all()
