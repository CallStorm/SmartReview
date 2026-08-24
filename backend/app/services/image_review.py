"""图审核（独立于内容审核）：存在性确定性检查 + 两段式识图/审核。

模板节点配置（parsed_structure 节点上的 image_review 字段）：
    {
      "enabled": true,
      "existence": {"enabled": true, "note": "施工总平面布置图"},
      "kind":      {"enabled": true, "note": "应急救援路线图"},
      "content":   {"enabled": true, "note": "集合点、疏散路线方向、安全出口"}
    }

- existence：纯确定性（子树内是否存在 [附图] 标记），不调 LLM、零成本。
- kind / content：视觉模型逐图识图（kind + description），文本 LLM 节点级一次判定
  （Task 2 接入流水线；本模块提供 prompt 纯函数与双指纹）。
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
from app.services.llm.chat import extract_json_object
from app.services.llm.resolve import ImageReviewConfig
from app.services.review_cache import cache_lookup, cache_store

IMAGE_REVIEW_VERSION = "img-3"
DESCRIBE_PROMPT_VERSION = "desc-1"
JUDGE_PROMPT_VERSION = "judge-1"
IMAGE_STEP_ID = "image_review"

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


_IMAGE_SYSTEM_BASE = (
    "你是建筑施工方案审核专家，负责审核文档中的附图。逐项核对审核要求与图片实际内容，"
    "判定必须基于图片中真实可见的要素，不得凭图说明文字推测。"
    "通过(passed=true)时 summary 必须概括图中实际看到了什么作为引证；"
    "不通过时 issues 给出 severity/message/evidence，evidence 引用图中可见内容或其缺失。"
    "输出经 tool_use 提交结构化 JSON。"
)

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


def _image_user_prompt(
    *,
    node_title_path: str,
    caption: str,
    config: NodeImageConfig,
    global_rules: str,
) -> str:
    """图审核 prompt：审核要求只来自「启用图审核」配置的文本框（kind/content note），
    不拼接内容审核的 review_prompt。图说明仅是背景参考，明确标注不构成审核要求，
    避免模型把文档文字误当要求（任务 551 曾因此误判导航截图不满足"包含路线图"）。"""
    checks: list[str] = []
    if config.kind_note:
        checks.append(f"图种识别：{config.kind_note}")
    if config.content_note:
        checks.append(f"内容要素：{config.content_note}")
    lines = [
        "请审核下方这张附图。",
        f"所在章节：{node_title_path}",
        f"图说明（仅作背景参考，不作为审核要求）：{caption or '（无）'}",
        "【审核要求】只按下列文本框配置逐项核对：",
    ]
    lines.extend(f"{i}. {c}" for i, c in enumerate(checks, start=1))
    lines.append(
        "判定原则：只依据上述【审核要求】与图片实际内容对照；"
        "要求图上标明的要素若实际未标出，视为不通过；"
        "图片与要求的图种不符（如要求路线图但为照片），视为不通过。"
    )
    if global_rules.strip():
        lines.append(f"【图审核全局规则】\n{global_rules.strip()}")
    return "\n".join(lines)


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


def image_node_fingerprint(
    *,
    model: str,
    config: NodeImageConfig,
    global_rules: str,
    template_updated_at: str,
    max_side: int,
    images: list[tuple[str, str]],
) -> str:
    """images: [(sha256, caption)]。图片身份用内容哈希（object_key 含每次
    上传的 UUID，纳入会导致同图重传永远 miss）；压缩参数 max_side 影响
    送审输入，一并纳入。"""
    payload = {
        "v": IMAGE_REVIEW_VERSION,
        "model": model,
        "cfg": {
            "existence": config.existence_note,
            "kind": config.kind_note,
            "content": config.content_note,
        },
        "rules": (global_rules or "").strip(),
        "tmpl": template_updated_at or "",
        "max_side": max_side,
        "imgs": [{"h": h, "cap": c} for h, c in images],
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _vision_judge_image(
    *,
    cfg: ImageReviewConfig,
    user_prompt: str,
    global_rules: str,
    image_bytes: bytes,
) -> dict[str, Any]:
    media_type, b64 = compress_image_bytes(image_bytes, max_side=cfg.max_side)
    system = _IMAGE_SYSTEM_BASE
    if global_rules.strip():
        system = f"{system}\n【图审核全局规则】\n{global_rules.strip()}"
    text = chat_anthropic_messages(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        model=cfg.model,
        user_message=user_prompt,
        system=system,
        max_tokens=1024,
        timeout=120.0,
        images=[(media_type, b64)],
    )
    return extract_json_object(text)


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
    """审核单个模板节点（含子树）的附图。视觉部分带结果缓存。

    多图判定语义：只要有一张附图满足文本框要求即通过（任一通过 → 节点通过）；
    仅当所有图都不满足时才判不通过并汇总各图问题。
    debug_prompts：调试开关开启时逐图追加（step_id=image_review）的拼接提示词。
    missing_text：配置了图种/内容要素视觉检查但未检出附图时，在问题列表展示的
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

    # 2) 视觉判定：无图或未勾选图种/要素时直接收尾
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

    # 缓存查询（节点级：全部图的判定结果）
    # 调试模式（debug_prompts 传入）跳过缓存：调试要看真实 prompt 与判定，命中缓存会采不到。
    fingerprint = image_node_fingerprint(
        model=cfg.model,
        config=config,
        global_rules=global_rules,
        template_updated_at=template_updated_at,
        max_side=cfg.max_side,
        images=[(h, c) for h, c, _key, _b in reviewed],
    )
    cached = None
    if debug_prompts is not None:
        res.logs.append(
            ("info", f"图审核节点 {template_node_id} 调试模式跳过结果缓存，重新视觉判定")
        )
    else:
        try:
            cached = cache_lookup(ldb, fingerprint)
        except Exception:
            cached = None
        # 只读缓存查询后立即归还连接：后续逐图视觉判定（每图 LLM 调用）期间
        # 连接可能空闲数分钟，若中间层（NAT/防火墙 ~300s 空闲超时）回收，
        # 写缓存时会 Lost connection(2013)。回池后由 pool_pre_ping/recycle 接管。
        try:
            ldb.rollback()
        except Exception:
            pass
    if cached is not None:
        res.cached = True
        res.passed = res.passed and cached.passed
        res.summary = cached.summary or res.summary
        res.issues.extend(cached.issues)
        res.image_items = cached.image_items or []
        res.logs.append(
            ("info", f"图审核节点 {template_node_id} 命中结果缓存（图件与规则未变化）")
        )
        return res

    vision_failed = 0
    passed_any = False
    passed_imgs: list[int] = []
    failed_issues: list[ReportIssue] = []
    passed_summary: str = ""
    # 审图类别：视觉判定行对应节点配置的图种/内容要素检查组合
    review_category = "+".join(
        cat for cat, on in (("kind", config.kind_note), ("content", config.content_note)) if on
    ) or "vision"
    for k, (sha, caption, object_key, data) in enumerate(reviewed, start=1):
        user_prompt = _image_user_prompt(
            node_title_path=node_title_path,
            caption=caption,
            config=config,
            global_rules=global_rules,
        )
        dbg_entry: dict[str, Any] = {
            "step_id": IMAGE_STEP_ID,
            "template_node_id": template_node_id,
            "title_path": title_path or [],
            "prompt_text": user_prompt,
            "prompt_length": len(user_prompt),
            "image_object_key": object_key,
            "image_caption": caption,
            "created_at": datetime.now(UTC).isoformat(),
        }
        if debug_prompts is not None:
            debug_prompts.append(dbg_entry)
        try:
            verdict = _vision_judge_image(
                cfg=cfg, user_prompt=user_prompt, global_rules=global_rules, image_bytes=data
            )
        except Exception as e:
            vision_failed += 1
            res.logs.append(("error", f"图审核节点 {template_node_id} 第 {k} 张图判定失败: {e!s}"))
            continue
        sub_passed = bool(verdict.get("passed"))
        # 补上模型判定结果（识别出的图内容），供前端调试表格展示
        dbg_entry["model_passed"] = sub_passed
        dbg_entry["model_summary"] = str(verdict.get("summary") or "")
        # 逐图结果（非调试依赖，供通过列表/问题列表展示）
        item_issues: list[dict[str, Any]] = []
        if sub_passed:
            passed_any = True
            passed_imgs.append(k)
            if not passed_summary:
                passed_summary = str(verdict.get("summary") or "满足图审核要求")
        else:
            for it in verdict.get("issues") or []:
                if not isinstance(it, dict):
                    continue
                item_issues.append(
                    {
                        "severity": str(it.get("severity") or "error"),
                        "message": str(it.get("message") or "不满足图审核要求"),
                        "evidence": str(it.get("evidence") or ""),
                    }
                )
                failed_issues.append(
                    ReportIssue(
                        severity=str(it.get("severity") or "error"),
                        message=f"第 {k} 张附图：{it.get('message') or '不满足图审核要求'}",
                        evidence=str(it.get("evidence") or ""),
                        anchor={"template_node_id": template_node_id},
                        related={
                            "check_item_id": f"{template_node_id}-img{k}",
                            "image_caption": caption,
                            "image_object_key": object_key,
                            "image_sha256": sha[:16],
                        },
                    )
                )
        res.image_items.append(
            {
                "template_node_id": template_node_id,
                "title_path": title_path or [],
                "review_category": review_category,
                "image_object_key": object_key,
                "image_caption": caption,
                "passed": sub_passed,
                "summary": str(verdict.get("summary") or ""),
                "issues": item_issues,
            }
        )

    # 多图判定：任一图满足文本框要求即节点通过；仅当全部不满足时才汇总问题
    if passed_any:
        res.passed = True
        res.summary = (
            f"通过：第 {'、'.join(str(i) for i in passed_imgs)} 张附图满足图审核要求"
            f"（{passed_summary}）"
        )
    else:
        res.passed = False
        res.issues.extend(failed_issues)
        if res.issues and not res.summary:
            res.summary = f"未发现满足图审核要求的附图（{len(failed_issues)} 条问题）"

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
    if vision_failed == len(reviewed) and reviewed:
        res.summary = "存在性审核通过；视觉模型调用失败，图种/要素审核未执行"
        res.logs.append(("error", f"图审核节点 {template_node_id} 视觉判定全部失败"))
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

    # 缓存写入：仅在全部图判定成功时写入，避免把失败状态缓存住
    if vision_failed == 0:
        try:
            cache_store(
                ldb,
                fingerprint=fingerprint,
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
            res.logs.append(("warning", f"图审核节点 {template_node_id} 结果缓存写入失败: {e!s}"))

    return res
