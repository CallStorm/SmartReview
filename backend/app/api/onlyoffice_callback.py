from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.scheme_review_task import SchemeReviewTask
from app.schemas.onlyoffice_editor import OnlyofficeCallbackPayload
from app.services import minio_storage
from app.services.onlyoffice import pull_callback_file

router = APIRouter(tags=["onlyoffice"])


@router.post("/onlyoffice/callback")
async def onlyoffice_callback(
    payload: OnlyofficeCallbackPayload,
    task_id: int = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    t = db.get(SchemeReviewTask, task_id)
    if t is None:
        return {"error": 1, "message": "task not found"}
    if not (t.output_object_key or "").strip():
        return {"error": 1, "message": "no output"}

    if payload.status not in {2, 6} or not payload.url:
        return {"error": 0}

    try:
        content = await pull_callback_file(payload.url)
    except Exception:
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
        return {"error": 1, "message": "storage failed"}

    t.updated_at = datetime.now(UTC)
    db.add(t)
    db.commit()
    return {"error": 0}
