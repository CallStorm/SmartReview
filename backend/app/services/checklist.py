"""内容审核检查项清单（checklist）工具。

把模板节点的散文式 review_prompt 确定性地拆成带编号的检查项，供
per-node 内容审核以「逐项判定」方式构造 prompt，并把 LLM 的 checks[]
结果归一化为 ReportIssue。

拆分完全确定性（不调 LLM），保证同一 prompt 每次拆分结果一致——这是
审核结果可复现的前提之一。
"""

from __future__ import annotations

import json
import re
from typing import Any

# 提示词/判定逻辑变更时 bump 此版本号（结果缓存指纹的组成部分）
CHECKLIST_VERSION = "1"

# 句子边界：。；？！与换行（保留分隔符）
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。；？！])|\n+")

# 带圈序号 ①-⑳
_CIRCLED_SPLIT_RE = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]")
_CIRCLED_CHARS = set("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳")

# 判定说明句（审核方法/判级指引，不是检查项）——以这些前缀开头的句子归入附注
_NOTE_PREFIXES = (
    "如果判断",
    "若判断",
    "注意",
    "以上确实",
    "无需",
    "不需要",
    "列举以",
    "该节中的",
    "路线方面，如果",  # n37 特例：附图亦可，属判定说明
)

# 「若无 X，则属于严重缺陷」类判级说明整句归附注
_SEVERITY_HINT_RE = re.compile(r"^(若无|如无|缺少).{0,40}?(则属于|属于|为)?严重缺陷")

# 澄清/放宽类说明（不是检查项）：包含即视为附注
_CLARIFY_CONTAINS = (
    "概念相同",
    "意思接近就行",
    "不需要完全一致",
    "只要写了就行",
    "不必深究",
    "不需要纠结",
    "只需要含有",
    "只要有",
    "只需要与",
)


_TRIM_CHARS = " \t\r\n。．.（）()；;，,、"

# 可自由去除的首尾标点（括号除外，见 _clean_segment 的配平逻辑）
_PLAIN_TRIM_CHARS = " \t\r\n。．.；;，,、"

_OPEN_PARENS = "（("
_CLOSE_PARENS = "）)"


def _paren_imbalance(text: str) -> int:
    """开括号数量 - 闭括号数量。"""
    opens = sum(1 for ch in text if ch in _OPEN_PARENS)
    closes = sum(1 for ch in text if ch in _CLOSE_PARENS)
    return opens - closes


def _clean_segment(text: str) -> str:
    """去掉句子两端残留的悬空标点。

    括号只有在「悬空」（去掉后剩余文本括号更配平）时才去除；
    与句内开括号配对的尾括号属于正文，必须保留。
    """
    s = text.strip().strip(_PLAIN_TRIM_CHARS)
    # 尾部：闭括号没有可配对的开括号（剩余文本开括号无富余）时去除
    while s and s[-1] in _CLOSE_PARENS and _paren_imbalance(s[:-1]) <= 0:
        s = s[:-1].rstrip(_PLAIN_TRIM_CHARS)
    # 尾部：开括号一律异常，去到非括号为止
    while s and s[-1] in _OPEN_PARENS:
        s = s[:-1].rstrip(_PLAIN_TRIM_CHARS)
    # 首部：开括号没有可配对的闭括号时去除
    while s and s[0] in _OPEN_PARENS and _paren_imbalance(s[1:]) >= 0:
        s = s[1:].lstrip(_PLAIN_TRIM_CHARS)
    # 首部：闭括号一律异常，去到非括号为止
    while s and s[0] in _CLOSE_PARENS:
        s = s[1:].lstrip(_PLAIN_TRIM_CHARS)
    return s.strip(_PLAIN_TRIM_CHARS).strip()


def _is_note(sentence: str) -> bool:
    s = sentence.strip()
    if not _clean_segment(s):
        return True
    for prefix in _NOTE_PREFIXES:
        if s.startswith(prefix):
            return True
    if _SEVERITY_HINT_RE.match(s):
        return True
    for marker in _CLARIFY_CONTAINS:
        if marker in s:
            return True
    return False


def _split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text)]
    return [p for p in parts if p]


def _strip_circled_markers(text: str) -> str:
    return _CIRCLED_SPLIT_RE.sub("", text).strip()


def _items_from_sentences(sentences: list[str], node_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    items: list[dict[str, Any]] = []
    notes: list[str] = []
    for s in sentences:
        cleaned = _clean_segment(s)
        if not cleaned:
            continue
        if _is_note(s):
            notes.append(cleaned)
        else:
            items.append({"id": f"{node_id}-{len(items) + 1}", "text": _strip_circled_markers(cleaned)})
    return items, notes


def explicit_check_items(node: dict[str, Any]) -> list[dict[str, Any]] | None:
    """读取节点显式配置的 check_items（parsed_structure 内）。未配置返回 None。

    支持两种形态：
    - [{"id": "...", "text": "..."}, ...]
    - ["纯文本", ...]（id 自动生成）
    """
    raw = node.get("check_items")
    if not isinstance(raw, list) or not raw:
        return None
    node_id = str(node.get("id") or "")
    items: list[dict[str, Any]] = []
    for i, entry in enumerate(raw):
        if isinstance(entry, str) and entry.strip():
            items.append({"id": f"{node_id}-{i + 1}", "text": entry.strip()})
        elif isinstance(entry, dict):
            text = str(entry.get("text") or "").strip()
            if not text:
                continue
            item_id = str(entry.get("id") or "").strip() or f"{node_id}-{i + 1}"
            items.append({"id": item_id, "text": text})
    return items or None


def split_check_items(
    node_id: str,
    review_prompt: str,
    *,
    node: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """把 review_prompt 拆成 (检查项列表, 判定附注列表)。

    规则（确定性）：
    1. 节点显式配置 check_items 时直接使用（附注为空）。
    2. prompt 内出现 >=2 个带圈序号时：序号前导句按句拆为检查项，
       每个 ①…/②… 段落各成一条检查项（去掉序号标记）。
    3. 否则按句号/分号/问号切句，判定说明句归附注，其余每句一条检查项。
    """
    prompt = (review_prompt or "").strip()
    if not prompt:
        return [], []

    if node is not None:
        explicit = explicit_check_items(node)
        if explicit:
            return explicit, []

    circled_count = sum(1 for ch in prompt if ch in _CIRCLED_CHARS)
    if circled_count >= 2:
        head, *marked = _CIRCLED_SPLIT_RE.split(prompt)
        items: list[dict[str, Any]] = []
        notes: list[str] = []
        head_items, head_notes = _items_from_sentences(_split_sentences(head), node_id)
        items.extend(head_items)
        notes.extend(head_notes)
        for seg in marked:
            seg = _strip_circled_markers(seg)
            if not seg:
                continue
            seg_sentences = _split_sentences(seg)
            # 带圈段落视为一条检查项：整段合并，剔除段内混入的判定说明句
            kept = [_clean_segment(s) for s in seg_sentences if not _is_note(s)]
            kept = [k for k in kept if k]
            if kept:
                items.append({"id": f"{node_id}-{len(items) + 1}", "text": " ".join(kept)})
            notes.extend(
                _clean_segment(s) for s in seg_sentences if _is_note(s) and _clean_segment(s)
            )
        return items, notes

    return _items_from_sentences(_split_sentences(prompt), node_id)


def build_checklist_block(items: list[dict[str, Any]], notes: list[str]) -> str:
    """渲染【检查项清单】+【判定附注】文本块。"""
    parts: list[str] = []
    if items:
        lines = [f"[{it['id']}] {it['text']}" for it in items]
        parts.append(
            "【检查项清单】（共 %d 项；判定结果必须逐项回填 item_id，不得遗漏、不得新增）\n%s"
            % (len(items), "\n".join(lines))
        )
    if notes:
        parts.append("【判定附注】（判定时遵守，不属于检查项，不得据此新增检查项）\n" + "\n".join(f"- {n}" for n in notes))
    return "\n\n".join(parts)


def checklist_signature(
    items: list[dict[str, Any]],
    notes: list[str],
    global_rules: str = "",
) -> str:
    """检查项清单的稳定签名（结果缓存指纹组成部分）。"""
    payload = {
        "v": CHECKLIST_VERSION,
        "items": items,
        "notes": notes,
        "global_rules": (global_rules or "").strip(),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
