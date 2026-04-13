from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.dashboard_runtime_settings import DashboardRuntimeSettings

MIN_REFRESH_INTERVAL_MINUTES = 5
MAX_REFRESH_INTERVAL_MINUTES = 240
DEFAULT_REFRESH_INTERVAL_MINUTES = 30


def get_or_create_dashboard_settings(db: Session) -> DashboardRuntimeSettings:
    row = db.query(DashboardRuntimeSettings).order_by(DashboardRuntimeSettings.id.asc()).first()
    if row is None:
        row = DashboardRuntimeSettings(refresh_interval_minutes=DEFAULT_REFRESH_INTERVAL_MINUTES)
        db.add(row)
        db.flush()
    return row


def get_dashboard_refresh_interval_minutes(db: Session) -> int:
    row = get_or_create_dashboard_settings(db)
    value = int(row.refresh_interval_minutes or DEFAULT_REFRESH_INTERVAL_MINUTES)
    if value < MIN_REFRESH_INTERVAL_MINUTES:
        return MIN_REFRESH_INTERVAL_MINUTES
    if value > MAX_REFRESH_INTERVAL_MINUTES:
        return MAX_REFRESH_INTERVAL_MINUTES
    return value
