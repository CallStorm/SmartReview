"""Helpers for walking template/user document trees."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, TypedDict


class UserHeadingEntry(TypedDict):
    heading_para_index: int
    title_path: list[str]
    title_path_text: str
    depth: int
    title: str


def iter_nodes(nodes: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for n in nodes:
        yield n
        yield from iter_nodes(n.get("children") or [])


def collect_subtree_text(node: dict[str, Any]) -> str:
    """Current node body lines + each child title + subtree (depth-first)."""
    lines: list[str] = []
    for line in node.get("content") or []:
        s = str(line).strip()
        if s:
            lines.append(s)
    for ch in node.get("children") or []:
        t = str(ch.get("title") or "").strip()
        if t:
            lines.append(t)
        sub = collect_subtree_text(ch)
        if sub:
            lines.append(sub)
    return "\n".join(lines)


def title_path_for_node(root_nodes: list[dict[str, Any]], target_id: str) -> list[str]:
    path: list[str] = []

    def walk(nodes: list[dict[str, Any]], acc: list[str]) -> bool:
        for n in nodes:
            tid = str(n.get("id") or "")
            title = str(n.get("title") or "").strip()
            next_acc = acc + ([title] if title else [])
            if tid == target_id:
                path.extend(next_acc)
                return True
            if walk(n.get("children") or [], next_acc):
                return True
        return False

    walk(root_nodes, [])
    return path


def resolve_user_node(mapping: dict[str, dict[str, Any]], template_node_id: str) -> dict[str, Any] | None:
    return mapping.get(template_node_id)


def collect_full_document_text(nodes: list[dict[str, Any]]) -> str:
    """Depth-first full document text with [hpi=N] markers on headings for LLM anchoring."""
    lines: list[str] = []

    def walk(ns: list[dict[str, Any]], depth: int = 0) -> None:
        for n in ns:
            title = str(n.get("title") or "").strip()
            hpi = n.get("heading_para_index")
            if title:
                prefix = "#" * min(max(depth, 1), 6)
                marker = f" {title}"
                if isinstance(hpi, int):
                    marker += f" [hpi={hpi}]"
                lines.append(f"{prefix}{marker}")
            for line in n.get("content") or []:
                s = str(line).strip()
                if s:
                    lines.append(s)
            walk(n.get("children") or [], depth + 1)

    walk(nodes)
    return "\n".join(lines)


def normalize_heading_title(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s.rstrip("。.;；,，、")


def parse_title_path_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [normalize_heading_title(str(x)) for x in value if normalize_heading_title(str(x))]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        parts = re.split(r"\s*[>＞]\s*", raw)
        return [normalize_heading_title(p) for p in parts if normalize_heading_title(p)]
    return []


def build_user_heading_index(nodes: list[dict[str, Any]]) -> list[UserHeadingEntry]:
    """Depth-first index of user document headings for full-document review anchoring."""
    index: list[UserHeadingEntry] = []

    def walk(ns: list[dict[str, Any]], acc: list[str], depth: int) -> None:
        for n in ns:
            title = normalize_heading_title(str(n.get("title") or ""))
            next_acc = acc + ([title] if title else [])
            hpi = n.get("heading_para_index")
            if title and isinstance(hpi, int):
                index.append(
                    UserHeadingEntry(
                        heading_para_index=hpi,
                        title_path=list(next_acc),
                        title_path_text=" > ".join(next_acc),
                        depth=depth,
                        title=title,
                    )
                )
            walk(n.get("children") or [], next_acc, depth + 1)

    walk(nodes, [], 0)
    return index


def format_heading_catalog(
    index: list[UserHeadingEntry],
    *,
    max_entries: int = 300,
) -> tuple[str, bool]:
    """Compact catalog for LLM prompt. Returns (text, truncated)."""
    if not index:
        return "(文档中未解析到带段落索引的标题)", False
    truncated = len(index) > max_entries
    shown = index[:max_entries]
    lines = [f"- [hpi={e['heading_para_index']}] {e['title_path_text']}" for e in shown]
    if truncated:
        lines.append(f"- … 另有 {len(index) - max_entries} 条标题未列出，请以正文 [hpi=N] 为准")
    return "\n".join(lines), truncated


def resolve_heading_from_index(
    index: list[UserHeadingEntry],
    *,
    hpi: int | None = None,
    title_path: list[str] | None = None,
) -> UserHeadingEntry | None:
    """Resolve a heading entry: hpi first, then exact/normalized/suffix path match."""
    if not index:
        return None

    by_hpi = {e["heading_para_index"]: e for e in index}

    if hpi is not None and hpi in by_hpi:
        return by_hpi[hpi]

    path = [normalize_heading_title(x) for x in (title_path or []) if normalize_heading_title(x)]
    if not path:
        return None

    path_text = " > ".join(path)
    path_norm = normalize_heading_title(path_text)

    exact = [e for e in index if e["title_path"] == path or e["title_path_text"] == path_text]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return max(exact, key=lambda e: e["depth"])

    norm_matches = [
        e
        for e in index
        if normalize_heading_title(e["title_path_text"]) == path_norm
        or normalize_heading_title(" > ".join(e["title_path"])) == path_norm
    ]
    if len(norm_matches) == 1:
        return norm_matches[0]
    if len(norm_matches) > 1:
        return max(norm_matches, key=lambda e: e["depth"])

    for n_levels in (2, 1):
        if len(path) < n_levels:
            continue
        suffix = path[-n_levels:]
        candidates = [e for e in index if e["title_path"][-n_levels:] == suffix]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            return max(candidates, key=lambda e: e["depth"])

    leaf = path[-1]
    leaf_hits = [e for e in index if e["title"] == leaf]
    if len(leaf_hits) == 1:
        return leaf_hits[0]

    return None


def find_heading_para_index_by_title_path(
    nodes: list[dict[str, Any]],
    title_path: list[str],
) -> int | None:
    """Resolve heading_para_index from a title path (best-effort for full-document issues)."""
    entry = resolve_heading_from_index(build_user_heading_index(nodes), title_path=title_path)
    return entry["heading_para_index"] if entry else None
