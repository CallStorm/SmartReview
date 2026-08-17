"""节点结果缓存指纹（services/review_cache.py）单测。"""

from __future__ import annotations

from app.services.review_cache import node_fingerprint

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
