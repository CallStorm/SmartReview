from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models.user import User
from app.schemas.admin_dashboard import DashboardSummary
from app.services.dashboard_snapshot import DASHBOARD_WINDOWS, read_dashboard_summary_snapshot

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_admin)],
    days: int = Query(30, ge=1, le=90),
) -> DashboardSummary:
    if days not in DASHBOARD_WINDOWS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"仅支持 days={DASHBOARD_WINDOWS}",
        )
    row = read_dashboard_summary_snapshot(db, days=days)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="看板快照尚未就绪，请稍后重试",
        )
    return row
