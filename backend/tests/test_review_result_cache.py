"""节点结果缓存指纹（services/review_cache.py）单测。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.schemas.review_report import ReportIssue, ReportStep
from app.services.review_cache import (
    cache_lookup,
    cache_store,
    is_llm_parse_failure_step,
    node_fingerprint,
)

BASE = dict(
    step_id="content",
    provider="deepseek",
    model="deepseek-v4-flash",
    checklist_sig='{"v":"1"}',
    template_updated_at="2026-08-15T00:00:00+00:00",
    current_text="正文A",
    ref_text="引用B",
    dataset_id="ds-1",
    query="钢管 扣件",
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def test_same_inputs_same_fingerprint():
    assert node_fingerprint(**BASE) == node_fingerprint(**BASE)


def test_any_component_change_changes_fingerprint():
    fp0 = node_fingerprint(**BASE)
    variants = [
        {**BASE, "current_text": "正文A（已修改）"},
        {**BASE, "ref_text": "引用B2"},
        {**BASE, "checklist_sig": '{"v":"2"}'},
        {**BASE, "template_updated_at": "2026-08-16T00:00:00+00:00"},
        {**BASE, "model": "deepseek-v4"},
        {**BASE, "provider": "minimax"},
        {**BASE, "step_id": "context_consistency"},
        {**BASE, "dataset_id": "ds-2"},
        {**BASE, "query": "工字钢"},
    ]
    for v in variants:
        assert node_fingerprint(**v) != fp0, f"指纹未变化: {v}"


def test_fingerprint_is_sha256_hex():
    fp = node_fingerprint(**BASE)
    assert len(fp) == 64
    int(fp, 16)  # 合法十六进制


def test_is_llm_parse_failure_step_detects_placeholder():
    step = ReportStep(
        step_id="content",
        passed=False,
        summary="模型调用或 JSON 解析失败（ValueError）",
        issues=[
            ReportIssue(
                severity="error",
                message="模型输出未能解析为结构化结果，请稍后重试或联系管理员。",
            )
        ],
    )
    assert is_llm_parse_failure_step(step) is True


def test_cache_store_skips_parse_failure(db_session):
    step = ReportStep(
        step_id="content",
        passed=False,
        summary="模型调用或 JSON 解析失败（ValueError）",
        issues=[
            ReportIssue(
                severity="error",
                message="模型输出未能解析为结构化结果，请稍后重试或联系管理员。",
            )
        ],
    )
    cache_store(
        db_session,
        fingerprint="deadbeef" * 8,
        step_id="content",
        template_node_id="n4",
        step=step,
    )
    assert cache_lookup(db_session, "deadbeef" * 8) is None
