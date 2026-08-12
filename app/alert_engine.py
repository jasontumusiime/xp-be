"""
ML Alert Categorisation Engine (Feature 5).

Rule-based heuristics + TF-IDF cosine similarity for community tension detection.
Runs on a schedule (every 5 minutes) and can be triggered manually.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import Session, select

from app.models import (
    Alert,
    AlertCategory,
    Report,
    ReportStatus,
    SubCategory,
    Task,
    TaskStatus,
    User,
    UserRole,
    get_datetime_utc,
)

ISO_ROLES = {UserRole.GISO, UserRole.DISO, UserRole.SISO}
OPERATION_KEYWORDS = {"operation", "patrol", "deployment"}

# ── TF-IDF community tension classifier ──────────────────
# Training "documents" representing community tension themes
_TENSION_DOCS = [
    "community tension conflict dispute between groups fighting violence",
    "protest demonstration march rally crowd gathering unrest",
    "tribal ethnic religious clash confrontation hostility",
    "land dispute boundary conflict property disagreement",
    "political tension election violence intimidation threat",
    "meeting assembly gathering tension heated argument",
    "mob crowd unrest disturbance public disorder",
]

_STOP_WORDS = {"the", "a", "an", "is", "in", "on", "at", "to", "of", "and", "or", "for", "with", "was", "has", "had"}


def _tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", text.lower()) if w not in _STOP_WORDS and len(w) > 2]


def _tf(tokens: list[str]) -> dict[str, float]:
    counts = Counter(tokens)
    total = len(tokens) or 1
    return {w: c / total for w, c in counts.items()}


def _build_idf(docs: list[list[str]]) -> dict[str, float]:
    n = len(docs)
    df: dict[str, int] = {}
    for doc in docs:
        for w in set(doc):
            df[w] = df.get(w, 0) + 1
    return {w: math.log((n + 1) / (d + 1)) + 1 for w, d in df.items()}


def _tfidf_vec(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    tf = _tf(tokens)
    return {w: tf[w] * idf.get(w, 1.0) for w in tf}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    dot = sum(a.get(w, 0) * v for w, v in b.items())
    mag_a = math.sqrt(sum(v * v for v in a.values())) or 1
    mag_b = math.sqrt(sum(v * v for v in b.values())) or 1
    return dot / (mag_a * mag_b)


# Pre-compute corpus IDF and centroid vector once at module load
_corpus_tokens = [_tokenize(d) for d in _TENSION_DOCS]
_idf = _build_idf(_corpus_tokens)
_corpus_vecs = [_tfidf_vec(t, _idf) for t in _corpus_tokens]

# Centroid of all tension document vectors
_all_words = set(w for v in _corpus_vecs for w in v)
_centroid: dict[str, float] = {w: sum(v.get(w, 0) for v in _corpus_vecs) / len(_corpus_vecs) for w in _all_words}

TENSION_THRESHOLD = 0.15  # cosine similarity threshold


def _is_tension(text: str) -> bool:
    tokens = _tokenize(text)
    if not tokens:
        return False
    vec = _tfidf_vec(tokens, _idf)
    return _cosine(vec, _centroid) >= TENSION_THRESHOLD


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _upsert_alert(
    session: Session,
    *,
    category: AlertCategory,
    title: str,
    description: str,
    subcounty_id: str | None = None,
    parish_id: str | None = None,
    source_report_id: str | None = None,
    source_task_id: str | None = None,
    severity_score: float = 0.0,
    latitude: float | None = None,
    longitude: float | None = None,
) -> bool:
    """Upsert an alert by (category, source_report_id or source_task_id or subcounty_id). Returns True if created."""
    q = select(Alert).where(Alert.category == category)
    if source_report_id:
        q = q.where(Alert.source_report_id == source_report_id)
    elif source_task_id:
        q = q.where(Alert.source_task_id == source_task_id)
    elif subcounty_id:
        q = q.where(Alert.subcounty_id == subcounty_id)
    else:
        return False

    existing = session.exec(q).first()
    now = get_datetime_utc()
    if existing:
        existing.title = title
        existing.description = description
        existing.severity_score = severity_score
        existing.is_active = True
        existing.updated_at = now
        session.add(existing)
        return False
    else:
        alert = Alert(
            category=category,
            title=title,
            description=description,
            subcounty_id=subcounty_id,
            parish_id=parish_id,
            source_report_id=source_report_id,
            source_task_id=source_task_id,
            severity_score=severity_score,
            latitude=latitude,
            longitude=longitude,
        )
        session.add(alert)
        return True


async def run_alert_engine(session: Session) -> dict[str, Any]:
    cutoff_48h = _now() - timedelta(hours=48)
    cutoff_2h = _now() - timedelta(hours=2)
    created = 0

    # ── Hotspot detection ─────────────────────────────────
    # ≥3 reports from same parish in last 48h
    recent_reports = session.exec(
        select(Report).where(
            Report.created_at >= cutoff_48h,
            Report.subcounty_id != None,  # noqa: E711
        )
    ).all()
    subcounty_counts: dict[str, list[Report]] = {}
    for r in recent_reports:
        key = str(r.subcounty_id)
        subcounty_counts.setdefault(key, []).append(r)

    for subcounty_id, reports in subcounty_counts.items():
        if len(reports) >= 3:
            score = min(len(reports) / 10.0, 1.0)
            if _upsert_alert(
                session,
                category=AlertCategory.HOTSPOT,
                title=f"Hotspot: {len(reports)} reports in 48h",
                description=f"{len(reports)} reports submitted from this sub-county in the last 48 hours.",
                subcounty_id=subcounty_id,
                severity_score=score,
            ):
                created += 1

    # ── Incident detection ────────────────────────────────
    # Unresolved reports older than 2h
    incident_reports = session.exec(
        select(Report).where(
            Report.status.in_([ReportStatus.ESCALATED, ReportStatus.REVIEW]),
            Report.created_at <= cutoff_2h,
        )
    ).all()
    for r in incident_reports:
        if _upsert_alert(
            session,
            category=AlertCategory.INCIDENT,
            title=f"Unresolved: {r.title}",
            description=f"Report has been in {r.status.value} status for over 2 hours.",
            source_report_id=str(r.id),
            severity_score=0.6,
            latitude=r.latitude,
            longitude=r.longitude,
        ):
            created += 1

    # Overdue tasks
    overdue_tasks = session.exec(
        select(Task).where(
            Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
            Task.due_date != None,  # noqa: E711
            Task.due_date <= _now(),
        )
    ).all()
    for t in overdue_tasks:
        if _upsert_alert(
            session,
            category=AlertCategory.INCIDENT,
            title=f"Overdue Task: {t.title}",
            description=f"Task is past its due date and still {t.status.value}.",
            source_task_id=str(t.id),
            severity_score=0.5,
        ):
            created += 1

    # ── Community Tension ─────────────────────────────────
    tension_reports = session.exec(
        select(Report).where(Report.created_at >= cutoff_48h)
    ).all()
    for r in tension_reports:
        subcat = session.get(SubCategory, r.subcategory_id)
        subcat_name = (subcat.name if subcat else "")
        text = f"{r.title} {r.description} {subcat_name}"
        if _is_tension(text):
            if _upsert_alert(
                session,
                category=AlertCategory.COMMUNITY_TENSION,
                title=f"Community Tension: {r.title}",
                description=r.description[:200],
                source_report_id=str(r.id),
                severity_score=0.5,
                latitude=r.latitude,
                longitude=r.longitude,
            ):
                created += 1

    # ── Police Operation ──────────────────────────────────
    iso_user_ids = {
        str(u.id)
        for u in session.exec(select(User).where(User.role.in_(list(ISO_ROLES)))).all()
    }
    op_reports = session.exec(
        select(Report).where(Report.created_at >= cutoff_48h)
    ).all()
    for r in op_reports:
        is_iso = str(r.submitted_by) in iso_user_ids
        text = (r.title + " " + r.description).lower()
        is_op_keyword = any(kw in text for kw in OPERATION_KEYWORDS)
        if is_iso or is_op_keyword:
            if _upsert_alert(
                session,
                category=AlertCategory.POLICE_OPERATION,
                title=f"Operation: {r.title}",
                description=r.description[:200],
                source_report_id=str(r.id),
                severity_score=0.4,
                latitude=r.latitude,
                longitude=r.longitude,
            ):
                created += 1

    op_tasks = session.exec(
        select(Task).where(Task.created_at >= cutoff_48h)
    ).all()
    for t in op_tasks:
        text = (t.title + " " + (t.description or "")).lower()
        if any(kw in text for kw in OPERATION_KEYWORDS):
            if _upsert_alert(
                session,
                category=AlertCategory.POLICE_OPERATION,
                title=f"Operation: {t.title}",
                description=(t.description or "")[:200],
                source_task_id=str(t.id),
                severity_score=0.4,
            ):
                created += 1

    session.commit()

    if created > 0:
        try:
            from app.api.routes.websocket import ws_manager
            await ws_manager.broadcast({"type": "new_alert", "count": created})
        except Exception:
            pass

    return {"alerts_created": created, "ran_at": _now().isoformat()}
