"""图审核（独立于内容审核）：存在性确定性检查 + 两段式识图/审核。

模板节点配置（parsed_structure 节点上的 image_review 字段）：
    {
      "enabled": true,
      "existence": {"enabled": true, "note": "施工总平面布置图"},
      "kind":      {"enabled": true, "note": "应急救援路线图"},
      "content":   {"enabled": true, "note": "集合点、疏散路线方向、安全出口"}
    }

- existence：纯确定性（子树内是否存在 [附图] 标记），不调 LLM、零成本。
- kind / content：视觉模型逐图识图（kind + description），文本 LLM 节点级一次判定。
- 缓存拆两段：识图指纹（图内容 + 视觉模型）与审核指纹（描述集合 + 文本模型 + 规则）。
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from datetime import UTC, datetime
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.review_report import ReportIssue, ReportStep
from app.services import minio_storage
from app.services.doc_tree_utils import iter_nodes
from app.services.llm.adapters.anthropic import chat_anthropic_messages
from app.services.llm.chat import chat_json, extract_json_object
from app.services.llm.resolve import ImageReviewConfig
from app.services.review_cache import cache_lookup, cache_store, provider_model_pair

IMAGE_REVIEW_VERSION = "img-3"
DESCRIBE_PROMPT_VERSION = "desc-1"
JUDGE_PROMPT_VERSION = "judge-1"
IMAGE_STEP_ID = "image_review"
DESCRIBE_STEP_ID = "image_describe"

_IMAGE_MARKER_RE = re.compile(r"^\[附图\]\s+(\S+)\s*$")
# 图说明候选：[附图] 行之前最近的普通文字行（通常就是图题/图说明）
_CAPTION_SKIP_RE = re.compile(r"^\[表格第\d+行\]")


@dataclass
class NodeImage:
    object_key: str
    caption: str = ""


@dataclass
class NodeImageConfig:
    """节点图审核配置（勾选式三类检查 + 补充说明）。"""

    existence_note: str = ""
    kind_note: str = ""
    content_note: str = ""

    @property
    def needs_vision(self) -> bool:
        return bool(self.kind_note or self.content_note)


def parse_node_image_config(tn: dict[str, Any]) -> NodeImageConfig | None:
    """解析模板节点的 image_review 配置；未启用或全空返回 None（该节点不审图）。"""
    raw = tn.get("image_review")
    if not isinstance(raw, dict) or not raw.get("enabled"):
        return None

    def _note(cat: str) -> str:
        c = raw.get(cat)
        if isinstance(c, dict) and c.get("enabled"):
            return str(c.get("note") or "").strip()
        return ""

    cfg = NodeImageConfig(
        existence_note=_note("existence"),
        kind_note=_note("kind"),
        content_note=_note("content"),
    )
    if not (cfg.existence_note or cfg.kind_note or cfg.content_note):
        return None
    return cfg


def collect_node_images(user_node: dict[str, Any]) -> list[NodeImage]:
    """按文档顺序收集节点（含子树）内所有 [附图] 标记及其图说明。

    图说明启发式：[附图] 行之前最近的非标记、非表格文字行。
    """
    images: list[NodeImage] = []
    caption_hint = ""
    for node in iter_nodes([user_node]):
        content = node.get("content")
        if not isinstance(content, list):
            continue
        for line in content:
            if not isinstance(line, str):
                continue
            m = _IMAGE_MARKER_RE.match(line.strip())
            if m:
                images.append(NodeImage(object_key=m.group(1), caption=caption_hint.strip()))
            elif line.strip() and not _CAPTION_SKIP_RE.match(line.strip()):
                caption_hint = line.strip()
    return images


def compress_image_bytes(data: bytes, *, max_side: int) -> tuple[str, str]:
    """送审前内部压缩：长边不超过 max_side，统一转 JPEG。返回 (media_type, base64)。"""
    from PIL import Image

    with Image.open(io.BytesIO(data)) as im:
        im.load()
        if im.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", im.size, (255, 255, 255))
            im2 = im.convert("RGBA")
            background.paste(im2, mask=im2.split()[-1])
            im = background
        elif im.mode != "RGB":
            im = im.convert("RGB")
        if max(im.size) > max_side:
            im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
    return "image/jpeg", base64.b64encode(buf.getvalue()).decode("ascii")


DESCRIBE_SYSTEM = "只描述图片中实际可见的内容，不判定是否合格。"
JUDGE_SYSTEM = "你是方案附图审核助手，只依据审核要求与识别结果判定，不要额外加严标准。"


def build_describe_user_prompt() -> str:
    """视觉识图 user prompt（极短，不含章节要求与判定语义）。"""
    return (
        "用一两段中文描述这张图实际看到的内容。\n"
        "必须包含：\n"
        "1) 图种（如：路线图/平面布置图/照片/表格截图/其他）\n"
        "2) 图上可见的关键文字、标注、符号、路径或对象\n"
        "不要判断是否合格，不要引用章节要求。"
    )


def build_judge_user_prompt(
    *,
    node_title_path: str,
    config: NodeImageConfig,
    global_rules: str,
    captions: list[str],
    descriptions: list[tuple[str, str]],
) -> str:
    """文本 LLM 节点级审核 user prompt（精简要求 + 全部图识别结果）。"""
    lines = [
        "根据【审核要求】与下列【附图识别结果】判定本章节附图是否通过。",
        "规则：至少一张图满足全部已启用的要求 → 通过；否则不通过。",
        "只依据识别结果中的可见内容，不要臆造图上没有的信息。",
        "图说明仅供参考，不作为通过条件。",
        "图种匹配时语义同类即可（如「路线图」含导航/路径规划截图），不要额外提高标准。",
        "",
        f"所在章节：{node_title_path}",
        "【审核要求】",
    ]
    if config.kind_note:
        lines.append(f"- 图种：{config.kind_note}")
    if config.content_note:
        lines.append(f"- 内容要素：{config.content_note}")
    if global_rules.strip():
        lines.append(f"【全局规则】\n{global_rules.strip()}")
    lines.append("")
    lines.append("【附图识别结果】")
    for i, (kind, desc) in enumerate(descriptions, start=1):
        cap = captions[i - 1] if i - 1 < len(captions) else ""
        part = f"图{i}：图种={kind}；描述={desc}"
        if cap:
            part += f"；图说明={cap}"
        lines.append(part)
    return "\n".join(lines)


def image_describe_fingerprint(*, model: str, max_side: int, image_sha256: str) -> str:
    payload = {
        "v": IMAGE_REVIEW_VERSION,
        "prompt_v": DESCRIBE_PROMPT_VERSION,
        "model": model,
        "max_side": max_side,
        "image_sha256": image_sha256,
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def image_judge_fingerprint(
    *,
    text_provider: str,
    text_model: str,
    config: NodeImageConfig,
    global_rules: str,
    template_updated_at: str,
    descriptions: list[tuple[str, str, str]],
) -> str:
    """descriptions 项为 (kind, description, caption)。"""
    payload = {
        "v": IMAGE_REVIEW_VERSION,
        "prompt_v": JUDGE_PROMPT_VERSION,
        "text_provider": text_provider,
        "text_model": text_model,
        "cfg": {
            "kind": config.kind_note,
            "content": config.content_note,
        },
        "rules": (global_rules or "").strip(),
        "tmpl": template_updated_at or "",
        "descriptions": [
            {"kind": k, "desc": d, "cap": c} for k, d, c in descriptions
        ],
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class NodeImageReviewResult:
    passed: bool = True
    summary: str = ""
    issues: list[ReportIssue] = field(default_factory=list)
    logs: list[tuple[str, str]] = field(default_factory=list)
    cached: bool = False
    # 逐图结果（供前端通过列表/问题列表展示，独立于调试开关）：
    #   {image_object_key, image_caption, passed, summary, issues:[{severity,message,evidence}]}
    image_items: list[dict[str, Any]] = field(default_factory=list)


def _release_ldb(ldb: Session) -> None:
    """只读缓存查询后立即归还连接，避免后续 LLM 空闲期间连接被中间层回收。"""
    try:
        ldb.rollback()
    except Exception:
        pass


def _parse_describe_payload(summary: str) -> dict[str, str] | None:
    try:
        data = json.loads(summary or "")
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return {
        "kind": str(data.get("kind") or "").strip(),
        "description": str(data.get("description") or "").strip(),
    }


def _vision_describe_image(*, cfg: ImageReviewConfig, image_bytes: bytes) -> dict[str, Any]:
    """视觉模型只识图，返回规范化的 kind / description。"""
    media_type, b64 = compress_image_bytes(image_bytes, max_side=cfg.max_side)
    text = chat_anthropic_messages(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        model=cfg.model,
        user_message=build_describe_user_prompt(),
        system=DESCRIBE_SYSTEM,
        max_tokens=1024,
        timeout=120.0,
        images=[(media_type, b64)],
    )
    parsed = extract_json_object(text)
    return {
        "kind": str(parsed.get("kind") or "").strip(),
        "description": str(parsed.get("description") or "").strip(),
    }


def _text_judge_node(ldb: Session, user_prompt: str) -> dict[str, Any]:
    """文本 LLM 节点级一次判定。"""
    return chat_json(
        ldb,
        user_message=user_prompt,
        system=JUDGE_SYSTEM,
        max_tokens=2048,
    )


def _matched_index_set(raw: Any) -> set[int]:
    matched: set[int] = set()
    for idx in raw or []:
        try:
            matched.add(int(idx))
        except (TypeError, ValueError):
            continue
    return matched


def review_node_images(
    *,
    ldb: Session,
    cfg: ImageReviewConfig,
    template_node_id: str,
    node_title_path: str,
    config: NodeImageConfig,
    user_node: dict[str, Any],
    global_rules: str,
    template_updated_at: str,
    debug_prompts: list[dict[str, Any]] | None = None,
    title_path: list[str] | None = None,
    missing_text: str = "无图审核",
) -> NodeImageReviewResult:
    """审核单个模板节点（含子树）的附图。两段式：视觉识图 + 文本判定。

    多图判定语义：只要有一张附图满足文本框要求即通过（任一通过 → 节点通过）；
    仅当所有图都不满足时才判不通过并汇总问题。
    图审核提示词始终写入 image_items，不依赖 debug_prompts。
    missing_text：配置了图种/内容要素但未检出附图时，在问题列表展示的
    可配置说明文字（模板级「缺图提示文案」），默认「无图审核」。
    """
    res = NodeImageReviewResult()
    images = collect_node_images(user_node)

    # 1) 存在性：确定性，无需模型，也无需缓存
    if config.existence_note and not images:
        res.passed = False
        res.issues.append(
            ReportIssue(
                severity="error",
                message=f"缺少附图：{config.existence_note}",
                evidence="本章节及子章节未检出任何附图标记（[附图]），视为未给出图件",
                anchor={"template_node_id": template_node_id},
                related={"check_item_id": f"{template_node_id}-exist-1"},
            )
        )
        res.summary = f"存在性审核未通过：{config.existence_note}"
        if not config.needs_vision:
            return res
    elif config.existence_note and images:
        res.logs.append(
            ("info", f"图审核节点 {template_node_id} 存在性通过（{len(images)} 张附图）")
        )

    # 2) 无图或未勾选图种/要素时直接收尾（不调视觉/文本）
    if not config.needs_vision or not images:
        if not res.summary:
            if config.existence_note:
                res.summary = "存在性审核通过"
            elif config.needs_vision and not res.issues:
                # 配置了图种/内容要素视觉检查但未检出附图：生成一条可配置提示
                # 进问题列表，让审核人员知晓该节点的图审核规则未能执行（任务 561）
                res.summary = missing_text.strip() or "无图审核"
                res.issues.append(
                    ReportIssue(
                        severity="info",
                        message=res.summary,
                        evidence="本章节及子章节未检出任何附图标记（[附图]），图种/内容要素视觉审核未执行",
                        anchor={
                            "template_node_id": template_node_id,
                            "title_path": title_path or [],
                        },
                        related={"check_item_id": f"{template_node_id}-img-none"},
                    )
                )
            else:
                res.summary = "无需图审核"
        # 存在性通过的节点也进通过列表（节点/图展示时不被遗漏）
        if config.existence_note and images and res.passed:
            res.image_items.append(
                {
                    "template_node_id": template_node_id,
                    "title_path": title_path or [],
                    "review_category": "existence",
                    "image_object_key": "",
                    "image_caption": "",
                    "passed": True,
                    "summary": (
                        f"存在性审核通过（检出 {len(images)} 张附图，"
                        "未配置图种/要素视觉判定）"
                    ),
                    "issues": [],
                }
            )
        return res

    # 取图 + 内容哈希（缓存身份用内容哈希，object_key 含 UUID 不可用）
    fetched: list[tuple[str, str, str, bytes]] = []  # (sha256, caption, object_key, bytes)
    for img in images:
        try:
            data = minio_storage.get_object_bytes(img.object_key)
        except Exception as e:
            res.logs.append(("warning", f"图审核取图失败 {img.object_key}: {e!s}"))
            continue
        fetched.append((hashlib.sha256(data).hexdigest(), img.caption, img.object_key, data))
    if not fetched:
        res.summary = "存在性审核通过；图片对象读取失败，视觉审核未执行"
        return res

    # 护栏：单节点图数上限，超限部分标记未审核而不是失败
    reviewed = fetched
    overflow = 0
    if len(fetched) > cfg.max_per_node:
        overflow = len(fetched) - cfg.max_per_node
        reviewed = fetched[: cfg.max_per_node]
        res.logs.append(
            ("warning", f"图审核节点 {template_node_id} 附图 {len(fetched)} 张超上限，仅审核前 {cfg.max_per_node} 张")
        )

    review_category = "+".join(
        cat for cat, on in (("kind", config.kind_note), ("content", config.content_note)) if on
    ) or "vision"
    describe_prompt = build_describe_user_prompt()

    described: list[tuple[str, str, str, str, str]] = []
    # (sha, caption, object_key, kind, description)
    vision_failed = 0
    for k, (sha, caption, object_key, data) in enumerate(reviewed, start=1):
        fp = image_describe_fingerprint(model=cfg.model, max_side=cfg.max_side, image_sha256=sha)
        cached_desc = None
        try:
            cached_desc = cache_lookup(ldb, fp)
        except Exception:
            cached_desc = None
        _release_ldb(ldb)
        payload = _parse_describe_payload(cached_desc.summary) if cached_desc is not None else None
        if payload is not None:
            described.append((sha, caption, object_key, payload["kind"], payload["description"]))
            continue
        try:
            verdict = _vision_describe_image(cfg=cfg, image_bytes=data)
        except Exception as e:
            vision_failed += 1
            res.logs.append(("error", f"图审核节点 {template_node_id} 第 {k} 张图识图失败: {e!s}"))
            described.append((sha, caption, object_key, "", ""))
            continue
        kind = str(verdict.get("kind") or "").strip()
        description = str(verdict.get("description") or "").strip()
        described.append((sha, caption, object_key, kind, description))
        try:
            cache_store(
                ldb,
                fingerprint=fp,
                step_id=DESCRIBE_STEP_ID,
                template_node_id=template_node_id,
                step=ReportStep(
                    step_id=DESCRIBE_STEP_ID,
                    passed=True,
                    summary=json.dumps({"kind": kind, "description": description}, ensure_ascii=False),
                ),
            )
        except Exception as e:
            res.logs.append(("warning", f"图审核节点 {template_node_id} 识图缓存写入失败: {e!s}"))

    if vision_failed == len(reviewed) and reviewed:
        res.summary = "存在性审核通过；视觉模型调用失败，图种/要素审核未执行"
        res.logs.append(("error", f"图审核节点 {template_node_id} 视觉识图全部失败"))
        res.issues.append(
            ReportIssue(
                severity="info",
                message=(
                    f"视觉模型调用失败（{vision_failed}/{len(reviewed)} 张），"
                    "图种与内容要素审核未执行，请检查图审核模型配置"
                ),
                evidence="",
                anchor={"template_node_id": template_node_id},
                related={"check_item_id": f"{template_node_id}-img-err"},
            )
        )
        if overflow:
            res.issues.append(
                ReportIssue(
                    severity="info",
                    message=f"本节点附图共 {len(fetched)} 张，超出单节点审核上限 {cfg.max_per_node} 张，"
                    f"后 {overflow} 张未审核（可在模型设置的图审核护栏中调整上限）",
                    evidence="",
                    anchor={"template_node_id": template_node_id},
                    related={"check_item_id": f"{template_node_id}-img-overflow"},
                )
            )
        return res

    captions = [cap for _sha, cap, _key, _kind, _desc in described]
    desc_pairs = [(kind, desc) for _sha, _cap, _key, kind, desc in described]
    judge_prompt = build_judge_user_prompt(
        node_title_path=node_title_path,
        config=config,
        global_rules=global_rules,
        captions=captions,
        descriptions=desc_pairs,
    )
    if debug_prompts is not None:
        debug_prompts.append(
            {
                "step_id": IMAGE_STEP_ID,
                "template_node_id": template_node_id,
                "title_path": title_path or [],
                "prompt_text": judge_prompt,
                "prompt_length": len(judge_prompt),
                "created_at": datetime.now(UTC).isoformat(),
            }
        )

    text_provider, text_model = provider_model_pair(ldb)
    judge_fp = image_judge_fingerprint(
        text_provider=text_provider,
        text_model=text_model,
        config=config,
        global_rules=global_rules,
        template_updated_at=template_updated_at,
        descriptions=[(kind, desc, cap) for _sha, cap, _key, kind, desc in described],
    )
    cached_judge = None
    try:
        cached_judge = cache_lookup(ldb, judge_fp)
    except Exception:
        cached_judge = None
    _release_ldb(ldb)
    if cached_judge is not None:
        res.cached = True
        res.passed = bool(cached_judge.passed)
        res.summary = cached_judge.summary or res.summary
        res.issues.extend(cached_judge.issues)
        res.image_items = cached_judge.image_items or []
        res.logs.append(
            ("info", f"图审核节点 {template_node_id} 命中审核结果缓存（描述与规则未变化）")
        )
        return res

    try:
        verdict = _text_judge_node(ldb, judge_prompt)
    except Exception as e:
        res.passed = False
        res.summary = "存在性审核通过；文本模型调用失败，图种/要素审核未执行"
        res.logs.append(("error", f"图审核节点 {template_node_id} 文本判定失败: {e!s}"))
        res.issues.append(
            ReportIssue(
                severity="info",
                message="文本模型调用失败，图种与内容要素审核未执行，请检查默认文本模型配置",
                evidence=str(e),
                anchor={"template_node_id": template_node_id},
                related={"check_item_id": f"{template_node_id}-img-judge-err"},
            )
        )
        if overflow:
            res.issues.append(
                ReportIssue(
                    severity="info",
                    message=f"本节点附图共 {len(fetched)} 张，超出单节点审核上限 {cfg.max_per_node} 张，"
                    f"后 {overflow} 张未审核（可在模型设置的图审核护栏中调整上限）",
                    evidence="",
                    anchor={"template_node_id": template_node_id},
                    related={"check_item_id": f"{template_node_id}-img-overflow"},
                )
            )
        return res

    matched = _matched_index_set(verdict.get("matched_image_indexes"))
    node_passed = bool(verdict.get("passed"))
    res.passed = node_passed
    res.summary = str(verdict.get("summary") or ("满足图审核要求" if node_passed else "未发现满足图审核要求的附图"))

    judge_issue_dicts: list[dict[str, Any]] = []
    for it in verdict.get("issues") or []:
        if isinstance(it, dict):
            judge_issue_dicts.append(
                {
                    "severity": str(it.get("severity") or "error"),
                    "message": str(it.get("message") or "不满足图审核要求"),
                    "evidence": str(it.get("evidence") or ""),
                }
            )

    for k, (sha, caption, object_key, kind, description) in enumerate(described, start=1):
        item_passed = k in matched
        item_issues = [] if item_passed else list(judge_issue_dicts)
        res.image_items.append(
            {
                "template_node_id": template_node_id,
                "title_path": title_path or [],
                "review_category": review_category,
                "image_object_key": object_key,
                "image_caption": caption,
                "kind": kind,
                "description": description,
                "summary": f"{kind}。{description}" if (kind or description) else "",
                "passed": item_passed,
                "issues": item_issues,
                "review_prompt_text": judge_prompt,
                "describe_prompt_text": describe_prompt,
            }
        )

    if not node_passed:
        unmatched = [i for i in range(1, len(described) + 1) if i not in matched]
        attach_k = unmatched[0] if unmatched else 1
        for it in judge_issue_dicts:
            related: dict[str, Any] = {"check_item_id": f"{template_node_id}-img-judge"}
            if 1 <= attach_k <= len(described):
                _sha, cap, object_key, kind, description = described[attach_k - 1]
                related.update(
                    {
                        "image_caption": cap,
                        "image_object_key": object_key,
                        "description": description,
                    }
                )
            res.issues.append(
                ReportIssue(
                    severity=it["severity"] if it["severity"] in ("error", "warning", "info") else "error",
                    message=it["message"],
                    evidence=it["evidence"],
                    anchor={"template_node_id": template_node_id},
                    related=related,
                )
            )

    if overflow:
        res.issues.append(
            ReportIssue(
                severity="info",
                message=f"本节点附图共 {len(fetched)} 张，超出单节点审核上限 {cfg.max_per_node} 张，"
                f"后 {overflow} 张未审核（可在模型设置的图审核护栏中调整上限）",
                evidence="",
                anchor={"template_node_id": template_node_id},
                related={"check_item_id": f"{template_node_id}-img-overflow"},
            )
        )

    # 仅在判定成功时写入审核缓存；识图失败的图不把失败态写入识图缓存（上已跳过）
    try:
        cache_store(
            ldb,
            fingerprint=judge_fp,
            step_id=IMAGE_STEP_ID,
            template_node_id=template_node_id,
            step=ReportStep(
                step_id=IMAGE_STEP_ID,
                passed=res.passed,
                summary=res.summary,
                issues=res.issues,
                image_items=res.image_items,
            ),
        )
    except Exception as e:
        res.logs.append(("warning", f"图审核节点 {template_node_id} 审核结果缓存写入失败: {e!s}"))

    return res
