from __future__ import annotations

from io import BytesIO

from app.database import SessionLocal
from app.models.scheme_review_task import ReviewTaskStatus, SchemeReviewTask
from app.services import minio_storage
from app.services.word_parser import parse_docx_to_tree


def _collect_titles(nodes: list, out: list[str], limit: int = 24) -> None:
    for n in nodes:
        if len(out) >= limit:
            return
        title = (n.get("title") or "").strip()
        if title:
            out.append(title)
        _collect_titles(n.get("children") or [], out, limit)


def process_scheme_review_task(task_id: int) -> None:
    db = SessionLocal()
    try:
        task = db.get(SchemeReviewTask, task_id)
        if task is None:
            return
        task.status = ReviewTaskStatus.processing
        task.error_message = None
        db.commit()

        raw = minio_storage.get_object_bytes(task.object_key)
        tree = parse_docx_to_tree(BytesIO(raw))
        titles: list[str] = []
        _collect_titles(tree.get("nodes") or [], titles)
        if titles:
            body = "文档目录摘要（前几级标题）：\n" + "\n".join(f"- {t}" for t in titles)
        else:
            body = "未在文档中识别到标准标题样式；已接收文件并完成初检。"

        task = db.get(SchemeReviewTask, task_id)
        if task is None:
            return
        task.status = ReviewTaskStatus.succeeded
        task.result_text = body + "\n\n（后续可在此接入大模型与知识库进行完整审核。）"
        db.commit()
    except Exception as e:
        db.rollback()
        try:
            task = db.get(SchemeReviewTask, task_id)
            if task is not None:
                task.status = ReviewTaskStatus.failed
                task.error_message = str(e)
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
