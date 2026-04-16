import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.scheme_review_task import SchemeReviewTask
from app.schemas.onlyoffice_editor import OnlyofficeCallbackPayload
from app.services import minio_storage
from app.services.onlyoffice import pull_callback_file

router = APIRouter(tags=["onlyoffice"])
logger = logging.getLogger(__name__)


@router.post("/onlyoffice/callback")
async def onlyoffice_callback(
    payload: OnlyofficeCallbackPayload,
    task_id: int = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    logger.info(
        "onlyoffice callback received: task_id=%s status=%s has_url=%s key=%s",
        task_id,
        payload.status,
        bool(payload.url),
        payload.key,
    )
    t = db.get(SchemeReviewTask, task_id)
    if t is None:
        logger.warning("onlyoffice callback task not found: task_id=%s", task_id)
        return {"error": 1, "message": "task not found"}
    if not (t.output_object_key or "").strip():
        logger.warning("onlyoffice callback no output object key: task_id=%s", task_id)
        return {"error": 1, "message": "no output"}

    if payload.status not in {2, 6} or not payload.url:
        logger.info(
            "onlyoffice callback ignored: task_id=%s status=%s has_url=%s",
            task_id,
            payload.status,
            bool(payload.url),
        )
        return {"error": 0}

    try:
        content = await pull_callback_file(payload.url)
    except Exception:
        logger.exception("onlyoffice callback download failed: task_id=%s", task_id)
        return {"error": 1, "message": "download failed"}

    key = t.output_object_key.strip()
    try:
        minio_storage.put_object(
            key,
            content,
            length=len(content),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except Exception:
        logger.exception("onlyoffice callback storage failed: task_id=%s key=%s", task_id, key)
        return {"error": 1, "message": "storage failed"}

    t.updated_at = datetime.now(UTC)
    db.add(t)
    db.commit()
    logger.info("onlyoffice callback persisted: task_id=%s key=%s bytes=%s", task_id, key, len(content))
    return {"error": 0}
