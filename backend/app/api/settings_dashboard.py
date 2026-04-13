from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models.user import User
from app.schemas.dashboard_settings import DashboardSettingsPublic, DashboardSettingsUpdate
from app.services.dashboard_settings import get_or_create_dashboard_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/dashboard", response_model=DashboardSettingsPublic)
def get_dashboard_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> DashboardSettingsPublic:
    row = get_or_create_dashboard_settings(db)
    return DashboardSettingsPublic(
        refresh_interval_minutes=int(row.refresh_interval_minutes),
        prompt_debug_enabled=bool(row.prompt_debug_enabled),
    )


@router.put("/dashboard", response_model=DashboardSettingsPublic)
def update_dashboard_settings(
    body: DashboardSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> DashboardSettingsPublic:
    row = get_or_create_dashboard_settings(db)
    row.refresh_interval_minutes = int(body.refresh_interval_minutes)
    row.prompt_debug_enabled = bool(body.prompt_debug_enabled)
    db.commit()
    db.refresh(row)
    return DashboardSettingsPublic(
        refresh_interval_minutes=int(row.refresh_interval_minutes),
        prompt_debug_enabled=bool(row.prompt_debug_enabled),
    )
