from __future__ import annotations

import logging
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.scheme_review_task import ReviewTaskStatus, SchemeReviewTask
from app.services.review_pipeline import run_review_pipeline
from app.services.review_settings import MAX_PARALLELISM, get_worker_parallel_tasks

logger = logging.getLogger(__name__)


def _append_runtime_log(task: SchemeReviewTask, level: str, message: str) -> None:
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    task.review_log = (task.review_log or "") + f"[{ts}] {level.upper()} {message}\n"


def _claim_next_pending_task_id(db: Session) -> int | None:
    stmt: Select[tuple[SchemeReviewTask]] = (
        select(SchemeReviewTask)
        .where(SchemeReviewTask.status == ReviewTaskStatus.pending)
        .order_by(SchemeReviewTask.id.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    row = db.execute(stmt).scalars().first()
    if row is None:
        db.rollback()
        return None
    row.status = ReviewTaskStatus.processing
    _append_runtime_log(row, "info", "任务已被 worker 领取，等待执行")
    db.commit()
    return int(row.id)


def process_scheme_review_task(task_id: int) -> None:
    run_review_pipeline(task_id)


def run_worker_forever(
    *,
    poll_interval_seconds: float = 2.0,
) -> None:
    logger.info(
        "Review worker started (poll_interval=%.1fs)",
        poll_interval_seconds,
    )
    pool = ThreadPoolExecutor(max_workers=MAX_PARALLELISM)
    inflight: dict[Future, int] = {}
    try:
        while True:
            # Reap completed tasks
            done_ids = [f for f in list(inflight) if f.done()]
            for fut in done_ids:
                tid = inflight.pop(fut)
                try:
                    fut.result()
                except Exception:
                    logger.exception("Unexpected worker error while processing task #%d", tid)

            try:
                with SessionLocal() as db:
                    limit = get_worker_parallel_tasks(db)
            except Exception:
                logger.exception("Failed to read worker_parallel_tasks; defaulting to 1")
                limit = 1

            while len(inflight) < limit:
                try:
                    with SessionLocal() as db:
                        task_id = _claim_next_pending_task_id(db)
                except OperationalError:
                    logger.exception("Failed to claim pending task due to database error")
                    break
                except Exception:
                    logger.exception("Failed to claim pending task")
                    break

                if task_id is None:
                    break

                logger.info("Start processing task #%d", task_id)

                def _run(tid: int) -> None:
                    process_scheme_review_task(tid)

                fut = pool.submit(_run, task_id)
                inflight[fut] = task_id

            if not inflight:
                time.sleep(max(0.5, poll_interval_seconds))
            else:
                wait(inflight.keys(), timeout=max(0.5, poll_interval_seconds), return_when=FIRST_COMPLETED)
    finally:
        pool.shutdown(wait=True)
