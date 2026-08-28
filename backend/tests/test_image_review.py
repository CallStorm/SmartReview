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
    IMAGE_REVIEW_VERSION,
    NodeImageConfig,
    _vision_describe_image,
    build_describe_user_prompt,
    build_judge_user_prompt,
    collect_node_images,
    compress_image_bytes,
    image_describe_fingerprint,
    image_judge_fingerprint,
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
    a = image_describe_fingerprint(model="m1", max_side=1024, image_sha256="h1")
    b = image_describe_fingerprint(model="m1", max_side=1024, image_sha256="h1")
    assert a == b
    # 图片内容哈希变化 -> 识图指纹变化
    c = image_describe_fingerprint(model="m1", max_side=1024, image_sha256="hX")
    assert a != c
    # 压缩参数变化 -> 识图指纹变化
    d = image_describe_fingerprint(model="m1", max_side=2048, image_sha256="h1")
    assert a != d
    j1 = image_judge_fingerprint(
        text_provider="deepseek",
        text_model="m1",
        config=NodeImageConfig(kind_note="路线图"),
        global_rules="",
        template_updated_at="t1",
        descriptions=[("路线图", "有路径", "cap1"), ("照片", "工地", "cap2")],
    )
    j2 = image_judge_fingerprint(
        text_provider="deepseek",
        text_model="m1",
        config=NodeImageConfig(kind_note="路线图"),
        global_rules="",
        template_updated_at="t1",
        descriptions=[("路线图", "有路径", "cap1"), ("照片", "工地", "cap2")],
    )
    assert j1 == j2
    j3 = image_judge_fingerprint(
        text_provider="deepseek",
        text_model="m1",
        config=NodeImageConfig(kind_note="路线图"),
        global_rules="",
        template_updated_at="t1",
        descriptions=[("路线图", "有路径", "cap1"), ("照片", "其他现场", "cap2")],
    )
    assert j1 != j3


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
        lambda key: b"fake-image-bytes",
    )
    monkeypatch.setattr(
        "app.services.image_review._vision_describe_image",
        lambda **kw: {"kind": "布置图", "description": "平面布置"},
    )
    monkeypatch.setattr(
        "app.services.image_review.chat_json",
        lambda *a, **k: {
            "passed": True,
            "summary": "通过",
            "issues": [],
            "matched_image_indexes": [1],
        },
    )
    monkeypatch.setattr(
        "app.services.image_review.compress_image_bytes",
        lambda data, *, max_side: ("image/jpeg", "aaa"),
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


def test_image_review_version_is_img3():
    assert IMAGE_REVIEW_VERSION == "img-3"


def test_build_describe_user_prompt_is_short_and_non_judging():
    p = build_describe_user_prompt()
    assert "不要判断是否合格" in p
    assert "路线图" in p  # 示例图种
    assert "审核要求" not in p


def test_build_judge_user_prompt_includes_all_descriptions_and_kind_only():
    p = build_judge_user_prompt(
        node_title_path="八、应急 > 3.救援医院信息",
        config=NodeImageConfig(kind_note="路线图"),
        global_rules="",
        captions=["丹凤县江南医院…"],
        descriptions=[("路线图", "绿色路径从营销中心到医院方向")],
    )
    assert "路线图" in p
    assert "图1" in p
    assert "绿色路径" in p
    assert "不要额外提高标准" in p
    assert "至少一张" in p
    assert "matched_image_indexes" in p
    # 未启用 content → 不应出现空的内容要素行强加标准
    assert "内容要素：" not in p or "内容要素：\n" not in p


def test_describe_and_judge_fingerprints_differ_by_inputs():
    d1 = image_describe_fingerprint(model="vl", max_side=1536, image_sha256="aaa")
    d2 = image_describe_fingerprint(model="vl", max_side=1536, image_sha256="bbb")
    assert d1 != d2
    j1 = image_judge_fingerprint(
        text_provider="deepseek",
        text_model="deepseek-v4-flash",
        config=NodeImageConfig(kind_note="路线图"),
        global_rules="",
        template_updated_at="t1",
        descriptions=[("路线图", "有路径", "cap")],
    )
    j2 = image_judge_fingerprint(
        text_provider="deepseek",
        text_model="deepseek-v4-flash",
        config=NodeImageConfig(kind_note="平面布置图"),
        global_rules="",
        template_updated_at="t1",
        descriptions=[("路线图", "有路径", "cap")],
    )
    assert j1 != j2


def test_compress_image_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (2000, 1000), "blue").save(buf, format="PNG")
    media, b64 = compress_image_bytes(buf.getvalue(), max_side=512)
    assert media == "image/jpeg"
    out = io.BytesIO(__import__("base64").b64decode(b64))
    with Image.open(out) as im:
        assert max(im.size) <= 512


def test_two_stage_kind_route_map_any_pass(db_session, monkeypatch):
    """视觉只描述；文本判定图1为路线图 → 节点通过；两图都有 description；带 review_prompt_text。"""
    calls = {"vision": 0, "text": 0}

    def fake_get(key):
        # 按 object_key 区分字节，避免两张图内容哈希相同导致识图缓存命中、只调一次视觉
        return f"fake-image-bytes:{key}".encode()

    def fake_describe(*, cfg, image_bytes):
        calls["vision"] += 1
        # 按调用次序：第一张路线图，第二张照片
        if calls["vision"] == 1:
            return {"kind": "路线图", "description": "绿线路径与推荐路线面板"}
        return {"kind": "照片", "description": "工地现场"}

    def fake_judge(ldb, *, user_message, system, max_tokens=2048):
        calls["text"] += 1
        assert "路线图" in user_message
        assert "图1" in user_message and "图2" in user_message
        return {
            "passed": True,
            "summary": "第1张为路线图，满足要求",
            "issues": [],
            "matched_image_indexes": [1],
        }

    monkeypatch.setattr("app.services.image_review.minio_storage.get_object_bytes", fake_get)
    monkeypatch.setattr("app.services.image_review._vision_describe_image", fake_describe)
    monkeypatch.setattr("app.services.image_review.chat_json", fake_judge)
    # 避免真实压缩依赖有效图片
    monkeypatch.setattr(
        "app.services.image_review.compress_image_bytes",
        lambda data, *, max_side: ("image/jpeg", "aaa"),
    )

    user_node = {
        "id": "u1",
        "content": [
            "cap-a",
            "[附图] reviews/1/images/a.png",
            "cap-b",
            "[附图] reviews/1/images/b.png",
        ],
        "children": [],
    }
    res = review_node_images(
        ldb=db_session,
        cfg=_cfg(max_per_node=10),
        template_node_id="n37",
        node_title_path="八、应急 > 3.救援医院信息",
        config=NodeImageConfig(kind_note="路线图"),
        user_node=user_node,
        global_rules="",
        template_updated_at="t1",
        title_path=["八、应急", "3.救援医院信息"],
    )
    assert res.passed is True
    assert calls["vision"] == 2
    assert calls["text"] == 1
    assert len(res.image_items) == 2
    assert res.image_items[0]["passed"] is True
    assert res.image_items[1]["passed"] is False
    assert "路线图" in res.image_items[0]["summary"]
    assert res.image_items[0]["description"]
    assert "至少一张" in res.image_items[0]["review_prompt_text"]
    assert res.image_items[0]["review_prompt_text"] == res.image_items[1]["review_prompt_text"]
    assert res.image_items[0]["describe_prompt_text"]


def test_two_stage_all_fail_still_has_descriptions(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.image_review.minio_storage.get_object_bytes", lambda k: b"x"
    )
    monkeypatch.setattr(
        "app.services.image_review._vision_describe_image",
        lambda **kw: {"kind": "照片", "description": "无路径"},
    )
    monkeypatch.setattr(
        "app.services.image_review.chat_json",
        lambda *a, **k: {
            "passed": False,
            "summary": "无路线图",
            "issues": [{"severity": "error", "message": "未见路线图", "evidence": "均为照片"}],
            "matched_image_indexes": [],
        },
    )
    monkeypatch.setattr(
        "app.services.image_review.compress_image_bytes",
        lambda data, *, max_side: ("image/jpeg", "aaa"),
    )
    user_node = {
        "id": "u1",
        "content": ["c", "[附图] reviews/1/images/a.png"],
        "children": [],
    }
    res = review_node_images(
        ldb=db_session,
        cfg=_cfg(),
        template_node_id="n1",
        node_title_path="x",
        config=NodeImageConfig(kind_note="路线图"),
        user_node=user_node,
        global_rules="",
        template_updated_at="t1",
    )
    assert res.passed is False
    assert len(res.issues) >= 1
    assert res.image_items[0]["passed"] is False
    assert res.image_items[0]["description"] == "无路径"
    assert res.image_items[0]["review_prompt_text"]


def test_vision_all_describe_fail_does_not_pass(db_session, monkeypatch):
    """识图全部失败时不得把 kind/content 节点标为通过。"""
    calls = {"text": 0}

    def boom(*, cfg, image_bytes):
        raise RuntimeError("vision down")

    def fake_judge(*a, **k):
        calls["text"] += 1
        return {"passed": True, "summary": "不应走到判定", "issues": [], "matched_image_indexes": [1]}

    monkeypatch.setattr(
        "app.services.image_review.minio_storage.get_object_bytes", lambda k: b"x"
    )
    monkeypatch.setattr("app.services.image_review._vision_describe_image", boom)
    monkeypatch.setattr("app.services.image_review.chat_json", fake_judge)
    monkeypatch.setattr(
        "app.services.image_review.compress_image_bytes",
        lambda data, *, max_side: ("image/jpeg", "aaa"),
    )
    user_node = {
        "id": "u1",
        "content": ["c", "[附图] reviews/1/images/a.png"],
        "children": [],
    }
    res = review_node_images(
        ldb=db_session,
        cfg=_cfg(),
        template_node_id="n37",
        node_title_path="x",
        config=NodeImageConfig(kind_note="路线图"),
        user_node=user_node,
        global_rules="",
        template_updated_at="t1",
    )
    assert res.passed is False
    assert calls["text"] == 0
    assert "视觉识图未得到有效描述" in res.summary
    assert any(i.related.get("check_item_id") == "n37-img-err" for i in res.issues)


def test_judge_passed_true_empty_matched_is_fail(db_session, monkeypatch):
    """LLM passed=true 但 matched 为空 → 节点不通过。"""
    monkeypatch.setattr(
        "app.services.image_review.minio_storage.get_object_bytes", lambda k: b"x"
    )
    monkeypatch.setattr(
        "app.services.image_review._vision_describe_image",
        lambda **kw: {"kind": "照片", "description": "工地"},
    )
    monkeypatch.setattr(
        "app.services.image_review.chat_json",
        lambda *a, **k: {
            "passed": True,
            "summary": "模型声称通过",
            "issues": [],
            "matched_image_indexes": [],
        },
    )
    monkeypatch.setattr(
        "app.services.image_review.compress_image_bytes",
        lambda data, *, max_side: ("image/jpeg", "aaa"),
    )
    user_node = {
        "id": "u1",
        "content": ["c", "[附图] reviews/1/images/a.png"],
        "children": [],
    }
    res = review_node_images(
        ldb=db_session,
        cfg=_cfg(),
        template_node_id="n1",
        node_title_path="x",
        config=NodeImageConfig(kind_note="路线图"),
        user_node=user_node,
        global_rules="",
        template_updated_at="t1",
    )
    assert res.passed is False
    assert res.image_items[0]["passed"] is False


def test_judge_passed_false_nonempty_matched_is_pass(db_session, monkeypatch):
    """LLM passed=false 但 matched 非空 → 以索引 any-pass 为准。"""
    monkeypatch.setattr(
        "app.services.image_review.minio_storage.get_object_bytes",
        lambda k: f"bytes:{k}".encode(),
    )
    monkeypatch.setattr(
        "app.services.image_review._vision_describe_image",
        lambda **kw: {"kind": "路线图", "description": "绿线路径"},
    )
    monkeypatch.setattr(
        "app.services.image_review.chat_json",
        lambda *a, **k: {
            "passed": False,
            "summary": "模型声称不通过",
            "issues": [{"severity": "error", "message": "未见路线图", "evidence": ""}],
            "matched_image_indexes": [1],
        },
    )
    monkeypatch.setattr(
        "app.services.image_review.compress_image_bytes",
        lambda data, *, max_side: ("image/jpeg", "aaa"),
    )
    user_node = {
        "id": "u1",
        "content": [
            "cap-a",
            "[附图] reviews/1/images/a.png",
            "cap-b",
            "[附图] reviews/1/images/b.png",
        ],
        "children": [],
    }
    res = review_node_images(
        ldb=db_session,
        cfg=_cfg(max_per_node=10),
        template_node_id="n1",
        node_title_path="x",
        config=NodeImageConfig(kind_note="路线图"),
        user_node=user_node,
        global_rules="",
        template_updated_at="t1",
    )
    assert res.passed is True
    assert res.image_items[0]["passed"] is True
    assert res.image_items[1]["passed"] is False


def _tiny_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, format="PNG")
    return buf.getvalue()


def test_vision_describe_uses_kind_description_tool_schema(monkeypatch):
    captured: dict = {}

    def fake_chat(**kwargs):
        captured.update(kwargs)
        return '{"kind": "路线图", "description": "绿色路径从营销中心到医院"}'

    monkeypatch.setattr("app.services.image_review.chat_anthropic_messages", fake_chat)
    result = _vision_describe_image(cfg=_cfg(), image_bytes=_tiny_png())
    tools = captured.get("tools") or []
    assert tools, "describe 必须传入识图专用 tools"
    schema = tools[0]
    assert schema["name"] == "submit_image_description"
    required = schema["input_schema"]["required"]
    assert "kind" in required
    assert "description" in required
    assert result["kind"] == "路线图"
    assert result["description"] == "绿色路径从营销中心到医院"


def test_vision_describe_empty_kind_and_description_raises(monkeypatch):
    monkeypatch.setattr(
        "app.services.image_review.chat_anthropic_messages",
        lambda **kwargs: '{"kind": "", "description": ""}',
    )
    with pytest.raises(ValueError):
        _vision_describe_image(cfg=_cfg(), image_bytes=_tiny_png())


def test_vision_describe_falls_back_to_prose_when_json_missing(monkeypatch):
    """MiniMax 等网关偶发不走 tool_use，返回散文描述时仍应可用作 description。"""
    prose = (
        "这是一张手机导航App的路线规划截图。\n\n"
        "顶部显示起点与终点为府谷县中医院，主图显示绿色规划路线。"
    )
    monkeypatch.setattr(
        "app.services.image_review.chat_anthropic_messages",
        lambda **kwargs: prose,
    )
    result = _vision_describe_image(cfg=_cfg(), image_bytes=_tiny_png())
    assert result["kind"] == ""
    assert "府谷县中医院" in result["description"]
    assert "路线规划" in result["description"]


def test_vision_describe_blank_prose_still_raises(monkeypatch):
    monkeypatch.setattr(
        "app.services.image_review.chat_anthropic_messages",
        lambda **kwargs: "   \n  ",
    )
    with pytest.raises(ValueError):
        _vision_describe_image(cfg=_cfg(), image_bytes=_tiny_png())
