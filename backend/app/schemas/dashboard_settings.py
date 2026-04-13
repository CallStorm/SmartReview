from pydantic import BaseModel, Field

from app.services.dashboard_settings import (
    MAX_REFRESH_INTERVAL_MINUTES,
    MIN_REFRESH_INTERVAL_MINUTES,
)


class DashboardSettingsPublic(BaseModel):
    refresh_interval_minutes: int = Field(
        ...,
        ge=MIN_REFRESH_INTERVAL_MINUTES,
        le=MAX_REFRESH_INTERVAL_MINUTES,
    )


class DashboardSettingsUpdate(BaseModel):
    refresh_interval_minutes: int = Field(
        ...,
        ge=MIN_REFRESH_INTERVAL_MINUTES,
        le=MAX_REFRESH_INTERVAL_MINUTES,
    )
