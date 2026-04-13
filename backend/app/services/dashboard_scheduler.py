from __future__ import annotations

import asyncio
import logging

from app.database import SessionLocal
from app.services.dashboard_settings import get_dashboard_refresh_interval_minutes
from app.services.dashboard_snapshot import refresh_all_dashboard_snapshots

logger = logging.getLogger(__name__)


def refresh_dashboard_snapshots_once() -> None:
    db = SessionLocal()
    try:
        refresh_all_dashboard_snapshots(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def run_dashboard_snapshot_scheduler(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            refresh_dashboard_snapshots_once()
            logger.info("dashboard snapshots refreshed")
        except Exception:
            logger.exception("dashboard snapshots refresh failed")

        interval_minutes = 30
        db = SessionLocal()
        try:
            interval_minutes = get_dashboard_refresh_interval_minutes(db)
        except Exception:
            logger.exception("load dashboard refresh interval failed; fallback to 30 minutes")
        finally:
            db.close()

        timeout_sec = max(60, interval_minutes * 60)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=timeout_sec)
        except TimeoutError:
            continue
