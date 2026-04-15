from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.api import (
    admin_dashboard,
    auth,
    basis,
    onlyoffice_callback,
    review_tasks,
    settings_dashboard,
    settings_review,
    scheme_types,
    settings_kb,
    settings_model,
    settings_onlyoffice,
    templates,
    users,
)
from app.config import get_settings
from app.database import SessionLocal
from app.models.user import User, UserRole
from app.core.security import hash_password
from app.services.dashboard_scheduler import run_dashboard_snapshot_scheduler


def bootstrap_admin() -> None:
    settings = get_settings()
    if not settings.admin_bootstrap or not settings.admin_username or not settings.admin_password:
        return
    db: Session = SessionLocal()
    try:
        exists = db.query(User).filter(User.username == settings.admin_username).first()
        if exists:
            return
        user = User(
            username=settings.admin_username,
            phone=settings.admin_phone or "00000000000",
            password_hash=hash_password(settings.admin_password),
            role=UserRole.admin,
        )
        db.add(user)
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap_admin()
    stop_event = asyncio.Event()
    scheduler_task = asyncio.create_task(run_dashboard_snapshot_scheduler(stop_event))
    yield
    stop_event.set()
    await scheduler_task


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="SmartReview API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(admin_dashboard.router)
    app.include_router(users.router)
    app.include_router(scheme_types.router)
    app.include_router(basis.router)
    app.include_router(templates.router)
    app.include_router(review_tasks.router)
    app.include_router(settings_kb.router)
    app.include_router(settings_dashboard.router)
    app.include_router(settings_review.router)
    app.include_router(settings_onlyoffice.router)
    app.include_router(settings_model.router)
    app.include_router(onlyoffice_callback.router)
    return app


app = create_app()
