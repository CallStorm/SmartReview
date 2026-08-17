# -*- coding: utf-8 -*-
"""prompt_history 服务的 diff 记录与查询测试（sqlite 内存库）。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import SchemeTemplate, TemplatePromptHistory
from app.services.prompt_history import (
    list_history,
    load_structure,
    record_field_change,
    record_full_document_diff,
    record_structure_diff,
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


@pytest.fixture()
def template_row(db_session):
    row = SchemeTemplate(
        scheme_type_id=1,
        minio_bucket="review",
        object_key="templates/1/x.docx",
        original_filename="x.docx",
        parsed_structure='{"nodes": []}',
    )
    db_session.add(row)
    db_session.flush()
    return row


def _mk_node(tid, title="t", review_prompt="", ctx_prompt=""):
    return {
        "id": tid,
        "title": title,
        "review_prompt": review_prompt,
        "context_consistency_prompt": ctx_prompt,
    }


def test_structure_diff_records_changed_prompt_fields(db_session, template_row):
    old = {"nodes": [_mk_node("n1", "概况", review_prompt="旧提示", ctx_prompt="旧对照")]}
    new = {"nodes": [_mk_node("n1", "概况", review_prompt="新提示", ctx_prompt="旧对照")]}
    n = record_structure_diff(
        db_session,
        template=template_row,
        old_structure=old,
        new_structure=new,
        changed_by="admin",
    )
    db_session.flush()
    assert n == 1  # 只有 review_prompt 变化
    rows = list_history(db_session, template_id=template_row.id)
    assert len(rows) == 1
    r = rows[0]
    assert r.field == "review_prompt"
    assert r.node_id == "n1"
    assert r.old_value == "旧提示"
    assert r.new_value == "新提示"
    assert r.changed_by == "admin"


def test_structure_diff_new_node_records_all_prompt_fields(db_session, template_row):
    old = {"nodes": []}
    new = {"nodes": [_mk_node("n2", "参数", review_prompt="新节点提示", ctx_prompt="对照要求")]}
    n = record_structure_diff(
        db_session,
        template=template_row,
        old_structure=old,
        new_structure=new,
        changed_by="admin",
    )
    db_session.flush()
    assert n == 2  # 新节点两个提示词字段都从空变化
    fields = {r.field for r in list_history(db_session, template_id=template_row.id)}
    assert fields == {"review_prompt", "context_consistency_prompt"}


def test_field_change_skips_identical_values(db_session, template_row):
    record_field_change(
        db_session,
        template=template_row,
        field="content_review_rules",
        old_value="规则",
        new_value=" 规则 ",  # 归一化后相同
        changed_by="admin",
    )
    db_session.flush()
    assert list_history(db_session, template_id=template_row.id) == []


def test_full_document_diff_flat_prompt(db_session, template_row):
    n = record_full_document_diff(
        db_session,
        template=template_row,
        old_config={"review_prompt": "旧通篇提示"},
        new_config={"review_prompt": "新通篇提示"},
        changed_by="admin",
    )
    db_session.flush()
    assert n == 1
    r = list_history(db_session, template_id=template_row.id)[0]
    assert r.field == "full_document_review_prompt"
    assert r.node_id == ""
    assert r.source == "manual"


def test_field_change_restore_source(db_session, template_row):
    record_field_change(
        db_session,
        template=template_row,
        field="content_review_rules",
        old_value="新规则",
        new_value="旧规则",
        changed_by="admin",
        source="restore",
    )
    db_session.flush()
    r = list_history(db_session, template_id=template_row.id)[0]
    assert r.source == "restore"


def test_load_structure_handles_str_and_none(template_row):
    template_row.parsed_structure = '{"nodes": []}'
    assert load_structure(template_row) == {"nodes": []}
    template_row.parsed_structure = None
    assert load_structure(template_row) is None
