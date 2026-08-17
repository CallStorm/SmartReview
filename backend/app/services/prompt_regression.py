"""提示词回归测试：模板提示词修改后，对最近 N 份历史文档自动重跑并对比问题集。

利用节点结果缓存：只有检查项清单/全局规则/模板版本变化的节点会重新调用
LLM，其余节点直接命中缓存，回归成本低。回归任务由管理员触发，文件名带
「[回归]」前缀，文档对象复用原任务的 MinIO 对象（拷贝新 key，避免删源
任务时连带删除）。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SchemeReviewTask
from app.models.scheme_review_task import ReviewTaskStatus
from app.services import minio_storage

REGRESSION_PREFIX = "[回归]"


def create_regression_tasks(
    db: Session,
    *,
    scheme_id: int,
    admin_user_id: int,
    task_limit: int,
) -> list[dict[str, Any]]:
    """把该方案类型最近 task_limit 份成功任务重新提交为回归任务。"""
    limit = max(1, min(task_limit, 20))
    rows = (
        db.query(SchemeReviewTask)
        .filter(
            SchemeReviewTask.scheme_type_id == scheme_id,
            SchemeReviewTask.status == ReviewTaskStatus.succeeded,
            ~SchemeReviewTask.original_filename.like(f"{REGRESSION_PREFIX}%"),
        )
        .order_by(SchemeReviewTask.id.desc())
        .limit(limit)
        .all()
    )
    pairs: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    ts = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    for src in rows:
        new_key = f"reviews/{scheme_id}/reg-{uuid.uuid4().hex}.docx"
        client = minio_storage.get_client()
        from minio.commonconfig import CopySource

        client.copy_object(
            src.minio_bucket,
            new_key,
            CopySource(src.minio_bucket, src.object_key),
        )
        row = SchemeReviewTask(
            scheme_type_id=scheme_id,
            user_id=admin_user_id,
            status=ReviewTaskStatus.pending,
            minio_bucket=src.minio_bucket,
            object_key=new_key,
            original_filename=f"{REGRESSION_PREFIX}{src.original_filename}",
            created_at=now,
            updated_at=now,
            review_log=f"[{ts}] INFO 回归测试任务（源任务 #{src.id}），等待处理\n",
        )
        db.add(row)
        db.flush()
        pairs.append(
            {
                "original_task_id": src.id,
                "rerun_task_id": row.id,
                "filename": src.original_filename,
            }
        )
    db.commit()
    return pairs


def _issue_key(step_id: str, node_id: str, check_item_id: str) -> str:
    """以 步骤|节点|检查项 作为问题身份，不含 message：LLM 措辞抖动
    不应被计入回归差异，同一问题换个说法仍是同一问题。"""
    return f"{step_id}|{node_id}|{check_item_id}"


def _report_issues(task: SchemeReviewTask) -> list[dict[str, str]]:
    import json as _json

    raw = task.review_result_json
    report = _json.loads(raw) if isinstance(raw, str) else (raw or {})
    out: list[dict[str, str]] = []
    for s in report.get("steps") or []:
        step_id = str(s.get("step_id") or "")
        for i in s.get("issues") or []:
            anchor = i.get("anchor") or {}
            rel = i.get("related") or {}
            out.append(
                {
                    "step": step_id,
                    "node_id": str(anchor.get("template_node_id") or ""),
                    "check_item_id": str(rel.get("check_item_id") or ""),
                    "severity": str(i.get("severity") or ""),
                    "message": str(i.get("message") or ""),
                }
            )
    return out


def compare_regression_pair(
    db: Session,
    *,
    original_id: int,
    rerun_id: int,
) -> dict[str, Any]:
    """对比源任务与回归任务的问题集差异。"""
    orig = db.get(SchemeReviewTask, original_id)
    rerun = db.get(SchemeReviewTask, rerun_id)
    if orig is None or rerun is None:
        raise ValueError("源任务或回归任务不存在")
    if orig.status != ReviewTaskStatus.succeeded or rerun.status != ReviewTaskStatus.succeeded:
        raise ValueError("两个任务都需处于 succeeded 状态才能对比")

    orig_issues = _report_issues(orig)
    rerun_issues = _report_issues(rerun)
    orig_map = {_issue_key(i["step"], i["node_id"], i["check_item_id"]): i for i in orig_issues}
    rerun_map = {_issue_key(i["step"], i["node_id"], i["check_item_id"]): i for i in rerun_issues}
    added = [rerun_map[k] for k in rerun_map.keys() - orig_map.keys()]
    removed = [orig_map[k] for k in orig_map.keys() - rerun_map.keys()]
    return {
        "original_task_id": original_id,
        "rerun_task_id": rerun_id,
        "filename": orig.original_filename,
        "original_issue_count": len(orig_issues),
        "rerun_issue_count": len(rerun_issues),
        "added": added,
        "removed": removed,
    }
