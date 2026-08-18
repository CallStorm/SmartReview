# -*- coding: utf-8 -*-
"""图审核服务测试：配置解析、图片收集、指纹稳定性、存在性判定、压缩。"""

from __future__ import annotations

import io

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.services.image_review import (
    NodeImageConfig,
    collect_node_images,
    compress_image_bytes,
    image_node_fingerprint,
    parse_node_image_config,
    review_node_images,
)
from app.services.llm.resolve import ImageReviewConfig


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


def _cfg(**kw):
    base = dict(
        enabled=True,
        base_url="https://api.minimaxi.com/anthropic",
        api_key="k",
        model="vl-test",
        max_side=512,
        max_per_node=2,
    )
    base.update(kw)
    return ImageReviewConfig(**base)


def test_parse_node_image_config():
    # 未配置 / 未启用 -> None
    assert parse_node_image_config({}) is None
    assert parse_node_image_config({"image_review": {"enabled": False}}) is None
    assert parse_node_image_config({"image_review": {"enabled": True}}) is None  # 全空

    tn = {
        "image_review": {
            "enabled": True,
            "existence": {"enabled": True, "note": "平面布置图"},
            "kind": {"enabled": False},
            "content": {"enabled": True, "note": "集合点"},
        }
    }
    c = parse_node_image_config(tn)
    assert c is not None
    assert c.existence_note == "平面布置图"
    assert c.kind_note == ""
    assert c.content_note == "集合点"
    assert c.needs_vision


def test_collect_node_images_with_caption():
    user_node = {
        "id": "u1",
        "content": [
            "图2-1 施工总平面布置图",
            "[附图] reviews/1/images/p0001_0001.png",
            "[表格第1行] a | b",
            "[附图] reviews/1/images/p0002_0002.png",
        ],
        "children": [
            {"id": "u2", "content": ["立面图"], "children": []},
        ],
    }
    imgs = collect_node_images(user_node)
    assert [i.object_key for i in imgs] == [
        "reviews/1/images/p0001_0001.png",
        "reviews/1/images/p0002_0002.png",
    ]
    # 第一张取前一行文字为图说明；第二张跳过表格行，沿用最近文字行
    assert imgs[0].caption == "图2-1 施工总平面布置图"
    assert imgs[1].caption == "图2-1 施工总平面布置图"


def test_fingerprint_stable_and_content_sensitive():
    a = image_node_fingerprint(
        model="m1",
        config=NodeImageConfig(kind_note="路线图"),
        global_rules="",
        template_updated_at="t1",
        max_side=1024,
        images=[("h1", "cap1"), ("h2", "cap2")],
    )
    b = image_node_fingerprint(
        model="m1",
        config=NodeImageConfig(kind_note="路线图"),
        global_rules="",
        template_updated_at="t1",
        max_side=1024,
        images=[("h1", "cap1"), ("h2", "cap2")],
    )
    assert a == b
    # 图片内容哈希变化 -> 指纹变化
    c = image_node_fingerprint(
        model="m1",
        config=NodeImageConfig(kind_note="路线图"),
        global_rules="",
        template_updated_at="t1",
        max_side=1024,
        images=[("h1", "cap1"), ("hX", "cap2")],
    )
    assert a != c
    # 压缩参数变化 -> 指纹变化
    d = image_node_fingerprint(
        model="m1",
        config=NodeImageConfig(kind_note="路线图"),
        global_rules="",
        template_updated_at="t1",
        max_side=2048,
        images=[("h1", "cap1"), ("h2", "cap2")],
    )
    assert a != d


def test_existence_check_missing_image(db_session, monkeypatch):
    user_node = {"id": "u1", "content": ["正文无图"], "children": []}
    res = review_node_images(
        ldb=db_session,
        cfg=_cfg(),
        template_node_id="n3",
        node_title_path="二、施工平面布置",
        config=NodeImageConfig(existence_note="施工总平面布置图"),
        user_node=user_node,
        global_rules="",
        template_updated_at="t1",
    )
    assert res.passed is False
    assert len(res.issues) == 1
    assert res.issues[0].related["check_item_id"] == "n3-exist-1"
    assert "缺少附图" in res.issues[0].message


def test_existence_check_with_image_passes(db_session, monkeypatch):
    user_node = {
        "id": "u1",
        "content": ["图2-1 平面布置图", "[附图] reviews/1/images/p0001_0001.png"],
        "children": [],
    }
    res = review_node_images(
        ldb=db_session,
        cfg=_cfg(),
        template_node_id="n3",
        node_title_path="二、施工平面布置",
        config=NodeImageConfig(existence_note="施工总平面布置图"),
        user_node=user_node,
        global_rules="",
        template_updated_at="t1",
    )
    # 仅存在性且已有图：无需视觉，直接通过，不触达 MinIO/LLM
    assert res.passed is True
    assert res.issues == []


def test_vision_missing_image_creates_missing_issue(db_session):
    # 只配置图种/内容要素（视觉检查）但节点未检出附图（任务 561 场景）：
    # 应生成一条可配置的「无图审核」提示进问题列表
    user_node = {"id": "u1", "content": ["正文无图"], "children": []}
    res = review_node_images(
        ldb=db_session,
        cfg=_cfg(),
        template_node_id="n37",
        node_title_path="3.救援医院信息",
        config=NodeImageConfig(kind_note="包含路线图"),
        user_node=user_node,
        global_rules="",
        template_updated_at="t1",
        title_path=["3.救援医院信息"],
    )
    assert res.passed is True
    assert res.summary == "无图审核"
    assert len(res.issues) == 1
    iss = res.issues[0]
    assert iss.severity == "info"
    assert iss.message == "无图审核"
    assert iss.related["check_item_id"] == "n37-img-none"
    assert iss.anchor["template_node_id"] == "n37"
    assert iss.anchor["title_path"] == ["3.救援医院信息"]


def test_vision_missing_image_uses_custom_text(db_session):
    user_node = {"id": "u1", "content": ["正文无图"], "children": []}
    res = review_node_images(
        ldb=db_session,
        cfg=_cfg(),
        template_node_id="n37",
        node_title_path="3.救援医院信息",
        config=NodeImageConfig(kind_note="包含路线图"),
        user_node=user_node,
        global_rules="",
        template_updated_at="t1",
        missing_text="配置了图审核但缺少图",
    )
    assert res.issues[0].message == "配置了图审核但缺少图"
    assert res.summary == "配置了图审核但缺少图"


def test_existence_missing_does_not_duplicate_missing_text(db_session):
    # 存在性缺图已有「缺少附图」error issue，不再追加「无图审核」提示
    user_node = {"id": "u1", "content": ["正文无图"], "children": []}
    res = review_node_images(
        ldb=db_session,
        cfg=_cfg(),
        template_node_id="n37",
        node_title_path="3.救援医院信息",
        config=NodeImageConfig(existence_note="施工总平面布置图", kind_note="包含路线图"),
        user_node=user_node,
        global_rules="",
        template_updated_at="t1",
    )
    assert res.passed is False
    assert len(res.issues) == 1
    assert res.issues[0].severity == "error"
    assert "缺少附图" in res.issues[0].message


def test_vision_guardrail_over_limit(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.image_review.minio_storage.get_object_bytes",
        lambda key: b"fake",
    )

    class _Img:
        def __init__(self, size, mode="RGB"):
            self._size, self._mode = size, mode

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    # 压缩走真实 Pillow，用小图字节
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), "red").save(buf, format="PNG")
    monkeypatch.setattr(
        "app.services.image_review.minio_storage.get_object_bytes",
        lambda key: buf.getvalue(),
    )
    # 视觉判定打桩：直接通过
    monkeypatch.setattr(
        "app.services.image_review._vision_judge_image",
        lambda **kw: {"passed": True, "summary": "通过", "issues": []},
    )

    user_node = {
        "id": "u1",
        "content": [
            "[附图] reviews/1/images/p0001_0001.png",
            "[附图] reviews/1/images/p0002_0002.png",
            "[附图] reviews/1/images/p0003_0003.png",
        ],
        "children": [],
    }
    res = review_node_images(
        ldb=db_session,
        cfg=_cfg(max_per_node=2),
        template_node_id="n3",
        node_title_path="二、施工平面布置",
        config=NodeImageConfig(kind_note="布置图"),
        user_node=user_node,
        global_rules="",
        template_updated_at="t1",
    )
    assert res.passed is True
    assert any(i.related.get("check_item_id") == "n3-img-overflow" for i in res.issues)


def test_compress_image_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (2000, 1000), "blue").save(buf, format="PNG")
    media, b64 = compress_image_bytes(buf.getvalue(), max_side=512)
    assert media == "image/jpeg"
    out = io.BytesIO(__import__("base64").b64decode(b64))
    with Image.open(out) as im:
        assert max(im.size) <= 512
