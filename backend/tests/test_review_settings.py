# -*- coding: utf-8 -*-
"""运行时设置测试：推理/输出/截断 3 个新开关的默认值与 clamp，adapter thinking 参数。

覆盖计划中的第 11 步：
- get_disable_reasoning 默认 True
- get_llm_max_output_tokens 默认 32768，低于下限/高于上限被 clamp
- get_content_text_cap_chars 默认 16000，低于下限/高于上限被 clamp
- chat_openai_compatible disable_reasoning=True 时 payload 含 thinking:{"type":"disabled"}
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.review_runtime_settings import ReviewRuntimeSettings
from app.services.review_settings import (
    DEFAULT_CONTENT_TEXT_CAP_CHARS,
    DEFAULT_LLM_MAX_OUTPUT_TOKENS,
    MAX_CONTENT_TEXT_CAP_CHARS,
    MAX_LLM_MAX_OUTPUT_TOKENS,
    MIN_CONTENT_TEXT_CAP_CHARS,
    MIN_LLM_MAX_OUTPUT_TOKENS,
    get_content_text_cap_chars,
    get_disable_reasoning,
    get_llm_max_output_tokens,
    get_or_create_review_settings,
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


def test_defaults_on_fresh_row(db_session):
    # 空表：get_or_create 首次建行应带新 3 列默认值
    row = get_or_create_review_settings(db_session)
    assert row.disable_reasoning is True
    assert row.llm_max_output_tokens == DEFAULT_LLM_MAX_OUTPUT_TOKENS == 32768
    assert row.content_text_cap_chars == DEFAULT_CONTENT_TEXT_CAP_CHARS == 16000
    # getter 返回相同默认值
    assert get_disable_reasoning(db_session) is True
    assert get_llm_max_output_tokens(db_session) == 32768
    assert get_content_text_cap_chars(db_session) == 16000


def test_disable_reasoning_toggle(db_session):
    row = get_or_create_review_settings(db_session)
    row.disable_reasoning = False
    db_session.flush()
    assert get_disable_reasoning(db_session) is False


def test_llm_max_output_tokens_clamp(db_session):
    row = get_or_create_review_settings(db_session)
    # 低于下限 -> 下限
    row.llm_max_output_tokens = 1
    db_session.flush()
    assert get_llm_max_output_tokens(db_session) == MIN_LLM_MAX_OUTPUT_TOKENS
    # 高于上限 -> 上限
    row.llm_max_output_tokens = 10**6
    db_session.flush()
    assert get_llm_max_output_tokens(db_session) == MAX_LLM_MAX_OUTPUT_TOKENS
    # 正常值原样返回
    row.llm_max_output_tokens = 20000
    db_session.flush()
    assert get_llm_max_output_tokens(db_session) == 20000


def test_content_text_cap_clamp(db_session):
    row = get_or_create_review_settings(db_session)
    row.content_text_cap_chars = 1
    db_session.flush()
    assert get_content_text_cap_chars(db_session) == MIN_CONTENT_TEXT_CAP_CHARS
    row.content_text_cap_chars = 10**6
    db_session.flush()
    assert get_content_text_cap_chars(db_session) == MAX_CONTENT_TEXT_CAP_CHARS
    row.content_text_cap_chars = 50000
    db_session.flush()
    assert get_content_text_cap_chars(db_session) == 50000


def test_schema_bounds_reject_out_of_range():
    from pydantic import ValidationError

    from app.schemas.review_settings import ReviewSettingsUpdate

    base = dict(
        review_timeout_seconds=120,
        prompt_debug_enabled=False,
        disable_reasoning=True,
        llm_max_output_tokens=32768,
        content_text_cap_chars=16000,
        worker_parallel_tasks=1,
        compilation_basis_concurrency=2,
        context_consistency_concurrency=2,
        content_concurrency=4,
        system_name="智能方案审核",
    )
    ok = ReviewSettingsUpdate(**base)
    assert ok.disable_reasoning is True
    assert ok.llm_max_output_tokens == 32768
    # 越界被 pydantic 拒绝
    for field, bad in (("llm_max_output_tokens", 100), ("content_text_cap_chars", 0)):
        kw = dict(base)
        kw[field] = bad
        with pytest.raises(ValidationError):
            ReviewSettingsUpdate(**kw)


def test_adapter_payload_includes_thinking_disabled(monkeypatch):
    """disable_reasoning=True 时请求体含 thinking:{"type":"disabled"}。"""
    captured: dict = {}

    class _Resp:
        def raise_for_status(self):
            pass

        @property
        def text(self):
            return "{}"

        def json(self):
            return {
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2},
            }

    class _FakeClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["payload"] = json
            return _Resp()

    monkeypatch.setattr("app.services.llm.adapters.openai_compatible.httpx.Client", _FakeClient)

    from app.services.llm.adapters.openai_compatible import chat_openai_compatible

    out = chat_openai_compatible(
        base_url="https://gw.example.com/v1",
        api_key="k",
        model="deepseek-v4-flash",
        user_message="hello",
        max_tokens=1024,
        disable_reasoning=True,
    )
    assert out == '{"ok": true}'
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert captured["payload"]["max_tokens"] == 1024
    assert captured["payload"]["response_format"] == {"type": "json_object"}

    # disable_reasoning=False 时不带 thinking 字段
    captured.clear()
    chat_openai_compatible(
        base_url="https://gw.example.com/v1",
        api_key="k",
        model="deepseek-v4-flash",
        user_message="hello",
        disable_reasoning=False,
    )
    assert "thinking" not in captured["payload"]


def test_fingerprint_includes_llm_settings(db_session):
    """推理/输出/截断参数变化应使缓存指纹变化（否则改设置后复用旧判定）。"""
    from app.services.review_cache import node_fingerprint

    base = dict(
        step_id="content",
        provider="deepseek",
        model="deepseek-v4-flash",
        checklist_sig="sig",
        template_updated_at="t",
        current_text="正文",
        ref_text="引用",
    )
    f1 = node_fingerprint(**base, db=db_session)
    # 改变 disable_reasoning -> 指纹变化
    row = get_or_create_review_settings(db_session)
    row.disable_reasoning = False
    db_session.flush()
    f2 = node_fingerprint(**base, db=db_session)
    assert f1 != f2
    # 改变输出上限 -> 指纹变化
    row.disable_reasoning = True
    row.llm_max_output_tokens = 20000
    db_session.flush()
    f3 = node_fingerprint(**base, db=db_session)
    assert f3 != f1
    # 不传 db -> 不含运行时参数，两次稳定一致
    f_nodb1 = node_fingerprint(**base)
    f_nodb2 = node_fingerprint(**base)
    assert f_nodb1 == f_nodb2
