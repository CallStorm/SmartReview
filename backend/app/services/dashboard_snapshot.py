from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.dashboard_summary_snapshot import DashboardSummarySnapshot
from app.schemas.admin_dashboard import DashboardSummary
from app.services.dashboard_stats import build_dashboard_summary

DASHBOARD_WINDOWS = (7, 30, 90)


def _get_snapshot_row(db: Session, *, days: int) -> DashboardSummarySnapshot | None:
    return (
        db.query(DashboardSummarySnapshot)
        .filter(DashboardSummarySnapshot.window_days == days)
        .order_by(DashboardSummarySnapshot.id.asc())
        .first()
    )


def refresh_dashboard_snapshot(db: Session, *, days: int) -> DashboardSummarySnapshot:
    summary = build_dashboard_summary(db, days=days)
    refreshed_at = datetime.now(UTC)
    payload = summary.model_dump(mode="json")
    row = _get_snapshot_row(db, days=days)
    if row is None:
        row = DashboardSummarySnapshot(window_days=days, payload_json=payload, refreshed_at=refreshed_at)
        db.add(row)
    else:
        row.payload_json = payload
        row.refreshed_at = refreshed_at
    return row


def refresh_all_dashboard_snapshots(db: Session, *, windows: tuple[int, ...] = DASHBOARD_WINDOWS) -> None:
    for days in windows:
        refresh_dashboard_snapshot(db, days=days)
    db.commit()


def read_dashboard_summary_snapshot(db: Session, *, days: int) -> DashboardSummary | None:
    row = _get_snapshot_row(db, days=days)
    if row is None:
        return None
    payload = dict(row.payload_json or {})
    payload["refreshed_at"] = row.refreshed_at
    return DashboardSummary.model_validate(payload)
