from __future__ import annotations

import traceback
from datetime import UTC, datetime
from io import BytesIO

from sqlalchemy.orm import Session

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


def _append_log(db: Session, task: SchemeReviewTask, level: str, message: str) -> None:
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {level.upper()} {message}\n"
    task.review_log = (task.review_log or "") + line


def process_scheme_review_task(task_id: int) -> None:
    db = SessionLocal()
    try:
        task = db.get(SchemeReviewTask, task_id)
        if task is None:
            return
        task.status = ReviewTaskStatus.processing
        task.error_message = None
        _append_log(db, task, "info", "任务开始处理")
        db.commit()

        _append_log(db, task, "info", "从对象存储读取审核文件…")
        db.commit()
        raw = minio_storage.get_object_bytes(task.object_key)
        _append_log(db, task, "info", f"已读取文件，大小 {len(raw)} 字节")
        db.commit()

        tree = parse_docx_to_tree(BytesIO(raw))
        titles: list[str] = []
        _collect_titles(tree.get("nodes") or [], titles)
        _append_log(
            db,
            task,
            "info",
            f"Word 解析完成，识别标题节点 {len(titles)} 个",
        )
        db.commit()

        if titles:
            body = "文档目录摘要（前几级标题）：\n" + "\n".join(f"- {t}" for t in titles)
        else:
            body = "未在文档中识别到标准标题样式；已接收文件并完成初检。"

        db.refresh(task)
        task.status = ReviewTaskStatus.succeeded
        task.result_text = body + "\n\n（后续可在此接入大模型与知识库进行完整审核。）"
        _append_log(db, task, "info", "任务处理成功")
        db.commit()
    except Exception as e:
        db.rollback()
        try:
            task = db.get(SchemeReviewTask, task_id)
            if task is not None:
                err_text = str(e)
                tb = traceback.format_exc()
                _append_log(db, task, "error", f"处理失败: {err_text}")
                _append_log(db, task, "error", f"异常堆栈:\n{tb}")
                task.status = ReviewTaskStatus.failed
                task.error_message = err_text
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
