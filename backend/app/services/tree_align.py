"""Align user document tree to template tree by heading titles (same level order)."""

from __future__ import annotations

from typing import Any


def norm_title(title: str) -> str:
    return " ".join((title or "").strip().split())


def title_path_str(path: list[str]) -> str:
    return " > ".join(path) if path else ""


def _node_title(n: dict[str, Any]) -> str:
    return norm_title(str(n.get("title") or ""))


def align_template_user_trees(
    template_nodes: list[dict[str, Any]],
    user_nodes: list[dict[str, Any]],
    *,
    path_prefix: list[str] | None = None,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """
    Returns (template_id -> user_node, structure_issues).
    Each issue: kind in missing_section|extra_section|order_mismatch, message, template_node_id,
    user_title, title_path, heading_para_index (when applicable).
    """
    path_prefix = path_prefix or []
    mapping: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []

    def walk(
        t_children: list[dict[str, Any]],
        u_children: list[dict[str, Any]],
        path: list[str],
    ) -> None:
        ui = 0
        for tc in t_children:
            tid = str(tc.get("id") or "")
            want = _node_title(tc)
            found_j: int | None = None
            for j in range(ui, len(u_children)):
                if _node_title(u_children[j]) == want:
                    found_j = j
                    break
            if found_j is None:
                issues.append(
                    {
                        "kind": "missing_section",
                        "message": f"缺少章节：{want}",
                        "template_node_id": tid,
                        "title_path": path + [want],
                    }
                )
                continue
            for k in range(ui, found_j):
                ut = _node_title(u_children[k])
                hpi = u_children[k].get("heading_para_index")
                issues.append(
                    {
                        "kind": "extra_section",
                        "message": f"多余章节：{ut}",
                        "user_title": ut,
                        "title_path": path + [ut],
                        "heading_para_index": hpi,
                    }
                )
            if found_j > ui:
                issues.append(
                    {
                        "kind": "order_mismatch",
                        "message": f"章节顺序与模板不一致：期望「{want}」前存在未对齐的段落",
                        "template_node_id": tid,
                        "title_path": path + [want],
                        "heading_para_index": u_children[found_j].get("heading_para_index"),
                    }
                )
            uc = u_children[found_j]
            if tid:
                mapping[tid] = uc
            walk(tc.get("children") or [], uc.get("children") or [], path + [want])
            ui = found_j + 1
        for k in range(ui, len(u_children)):
            ut = _node_title(u_children[k])
            hpi = u_children[k].get("heading_para_index")
            issues.append(
                {
                    "kind": "extra_section",
                    "message": f"多余章节：{ut}",
                    "user_title": ut,
                    "title_path": path + [ut],
                    "heading_para_index": hpi,
                }
            )

    walk(template_nodes, user_nodes, path_prefix)
    return mapping, issues
