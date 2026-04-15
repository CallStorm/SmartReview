from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.models.basis_item import BasisItem
from app.models.scheme_review_task import ReviewTaskStatus, SchemeReviewTask
from app.models.scheme_template import SchemeTemplate
from app.models.scheme_type import SchemeType
from app.models.user import User, UserRole
from app.schemas.admin_dashboard import (
    DashboardSummary,
    DifyDashboardBlock,
    DifyDatasetItem,
    TaskCountByDayItem,
    TaskCountBySchemeTypeItem,
    TaskCountByStatusItem,
    TokenCountByDayItem,
)
from app.services.dify_client import collect_dify_kb_metrics
from app.services.dify_settings import get_dify_url_and_key

BEIJING_TZ = ZoneInfo("Asia/Shanghai")

_DIFY_CACHE: dict[str, object] = {}


def _sum_tokens(db: Session, *criterion: object) -> tuple[int, int, int]:
    """Returns (input_sum, output_sum, total_sum) with NULL treated as 0."""
    q = db.query(
        func.coalesce(func.sum(SchemeReviewTask.input_tokens), 0),
        func.coalesce(func.sum(SchemeReviewTask.output_tokens), 0),
        func.coalesce(func.sum(SchemeReviewTask.total_tokens), 0),
    )
    for c in criterion:
        q = q.filter(c)
    row = q.one()
    return int(row[0]), int(row[1]), int(row[2])
_DIFY_CACHE_TTL_SEC = 120.0


def _empty_dify_block(*, configured: bool, error: str | None = None) -> DifyDashboardBlock:
    return DifyDashboardBlock(
        configured=configured,
        dataset_count=0,
        segment_total=0,
        datasets=[],
        error=error,
        truncated=False,
    )


def _load_dify_block(db: Session) -> DifyDashboardBlock:
    url, key = get_dify_url_and_key(db)
    if not url.strip() or not key.strip():
        return _empty_dify_block(configured=False)

    cache_key = f"{url.strip()}|{len(key)}"
    now = time.monotonic()
    hit = _DIFY_CACHE.get("until")
    if (
        isinstance(hit, float)
        and now < hit
        and _DIFY_CACHE.get("key") == cache_key
        and isinstance(_DIFY_CACHE.get("block"), DifyDashboardBlock)
    ):
        return _DIFY_CACHE["block"]  # type: ignore[return-value]

    m = collect_dify_kb_metrics(url, key)
    block = DifyDashboardBlock(
        configured=m.configured,
        dataset_count=m.dataset_count,
        segment_total=m.segment_total,
        datasets=[
            DifyDatasetItem(
                id=d.id,
                name=d.name,
                segment_count=d.segment_count,
                truncated=d.truncated,
            )
            for d in m.datasets
        ],
        error=m.error,
        truncated=m.truncated,
    )
    _DIFY_CACHE["key"] = cache_key
    _DIFY_CACHE["block"] = block
    _DIFY_CACHE["until"] = now + _DIFY_CACHE_TTL_SEC
    return block


def build_dashboard_summary(db: Session, *, days: int) -> DashboardSummary:
    users_total = int(db.query(func.count(User.id)).scalar() or 0)
    users_admin = int(db.query(func.count(User.id)).filter(User.role == UserRole.admin).scalar() or 0)
    users_regular = users_total - users_admin

    scheme_types_total = int(db.query(func.count(SchemeType.id)).scalar() or 0)
    templates_total = int(db.query(func.count(SchemeTemplate.id)).scalar() or 0)
    basis_items_total = int(db.query(func.count(BasisItem.id)).scalar() or 0)
    review_tasks_total = int(db.query(func.count(SchemeReviewTask.id)).scalar() or 0)

    now = datetime.now(UTC)
    now_bj = now.astimezone(BEIJING_TZ)
    bj_day_start = now_bj.replace(hour=0, minute=0, second=0, microsecond=0)
    bj_day_end = bj_day_start + timedelta(days=1)
    day_start_utc = bj_day_start.astimezone(UTC)
    day_end_utc = bj_day_end.astimezone(UTC)
    review_tasks_today = int(
        db.query(func.count(SchemeReviewTask.id))
        .filter(SchemeReviewTask.created_at >= day_start_utc, SchemeReviewTask.created_at < day_end_utc)
        .scalar()
        or 0
    )

    week_ago = now - timedelta(days=7)
    active_submitters_7d = int(
        db.query(func.count(distinct(SchemeReviewTask.user_id)))
        .filter(SchemeReviewTask.created_at >= week_ago)
        .scalar()
        or 0
    )

    status_rows = (
        db.query(SchemeReviewTask.status, func.count(SchemeReviewTask.id))
        .group_by(SchemeReviewTask.status)
        .all()
    )
    by_status = {str(r[0]): int(r[1]) for r in status_rows}
    succeeded_n = by_status.get(ReviewTaskStatus.succeeded, 0)
    failed_n = by_status.get(ReviewTaskStatus.failed, 0)
    denom = succeeded_n + failed_n
    completion_rate = (succeeded_n / denom) if denom > 0 else None

    input_tokens_total, output_tokens_total, tokens_total_all = _sum_tokens(db)
    input_tokens_today, output_tokens_today, tokens_today_total = _sum_tokens(
        db,
        SchemeReviewTask.created_at >= day_start_utc,
        SchemeReviewTask.created_at < day_end_utc,
    )

    today_bj = now_bj.date()
    first_day_bj = today_bj - timedelta(days=days - 1)
    since_utc = datetime(
        first_day_bj.year,
        first_day_bj.month,
        first_day_bj.day,
        tzinfo=BEIJING_TZ,
    ).astimezone(UTC)
    input_tokens_window, output_tokens_window, tokens_window_total = _sum_tokens(
        db,
        SchemeReviewTask.created_at >= since_utc,
    )

    created_at_bj = func.convert_tz(SchemeReviewTask.created_at, "+00:00", "+08:00")
    day_col = func.date(created_at_bj)
    per_day_rows = (
        db.query(
            day_col,
            func.count(SchemeReviewTask.id),
            func.coalesce(func.sum(SchemeReviewTask.input_tokens), 0),
            func.coalesce(func.sum(SchemeReviewTask.output_tokens), 0),
            func.coalesce(func.sum(SchemeReviewTask.total_tokens), 0),
        )
        .filter(SchemeReviewTask.created_at >= since_utc)
        .group_by(day_col)
        .order_by(day_col)
        .all()
    )
    tasks_per_day: list[TaskCountByDayItem] = []
    tokens_per_day: list[TokenCountByDayItem] = []
    for d, c, in_sum, out_sum, tot_sum in per_day_rows:
        if d is None:
            continue
        ds = d.isoformat() if hasattr(d, "isoformat") else str(d)
        tasks_per_day.append(TaskCountByDayItem(date=ds, count=int(c)))
        tokens_per_day.append(
            TokenCountByDayItem(
                date=ds,
                input_tokens=int(in_sum),
                output_tokens=int(out_sum),
                total_tokens=int(tot_sum),
            )
        )

    tasks_by_status = [TaskCountByStatusItem(status=k, count=v) for k, v in sorted(by_status.items())]

    scheme_rows = (
        db.query(
            SchemeReviewTask.scheme_type_id,
            SchemeType.category,
            SchemeType.name,
            func.count(SchemeReviewTask.id).label("cnt"),
        )
        .join(SchemeType, SchemeType.id == SchemeReviewTask.scheme_type_id)
        .group_by(SchemeReviewTask.scheme_type_id, SchemeType.category, SchemeType.name)
        .order_by(func.count(SchemeReviewTask.id).desc())
        .limit(10)
        .all()
    )
    tasks_by_scheme_type = [
        TaskCountBySchemeTypeItem(
            scheme_type_id=int(stid),
            scheme_category=str(cat or ""),
            scheme_name=str(name or ""),
            count=int(cnt),
        )
        for stid, cat, name, cnt in scheme_rows
    ]

    return DashboardSummary(
        users_total=users_total,
        users_admin=users_admin,
        users_regular=users_regular,
        scheme_types_total=scheme_types_total,
        templates_total=templates_total,
        basis_items_total=basis_items_total,
        review_tasks_total=review_tasks_total,
        review_tasks_today=review_tasks_today,
        active_submitters_7d=active_submitters_7d,
        completion_rate=completion_rate,
        tokens_total_all=tokens_total_all,
        input_tokens_total=input_tokens_total,
        output_tokens_total=output_tokens_total,
        tokens_today_total=tokens_today_total,
        input_tokens_today=input_tokens_today,
        output_tokens_today=output_tokens_today,
        tokens_window_total=tokens_window_total,
        input_tokens_window=input_tokens_window,
        output_tokens_window=output_tokens_window,
        tasks_per_day=tasks_per_day,
        tokens_per_day=tokens_per_day,
        tasks_by_status=tasks_by_status,
        tasks_by_scheme_type=tasks_by_scheme_type,
        dify=_load_dify_block(db),
    )
