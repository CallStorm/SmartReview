"""Helpers for walking template/user document trees."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


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
