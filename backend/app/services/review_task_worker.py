from __future__ import annotations

from app.services.review_pipeline import run_review_pipeline


def process_scheme_review_task(task_id: int) -> None:
    run_review_pipeline(task_id)
