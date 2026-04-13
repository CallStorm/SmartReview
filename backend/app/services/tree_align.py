"""Align user document tree to template tree by heading titles (same level order)."""

from __future__ import annotations

from typing import Any


def norm_title(title: str) -> str:
    return " ".join((title or "").strip().split())


def title_path_str(path: list[str]) -> str:
    return " > ".join(path) if path else ""


def _node_title(n: dict[str, Any]) -> str:
    return norm_title(str(n.get("title") or ""))


def _template_max_depth(nodes: list[dict[str, Any]]) -> int:
    """Height of the template forest: 0 for empty, 1 for roots-only, etc."""
    if not nodes:
        return 0
    return 1 + max(
        _template_max_depth(n.get("children") or []) for n in nodes
    )


def _prune_user_tree_to_depth(
    nodes: list[dict[str, Any]],
    max_depth: int,
    depth: int = 1,
) -> list[dict[str, Any]]:
    """
    Keep only the first ``max_depth`` levels of the user outline.
    Deeper headings (e.g. user uses Heading 3–9 where the template only defines two levels)
    are dropped from structure comparison; body/content under kept nodes is unchanged
    on the dict, but their ``children`` lists are cleared at the cutoff.
    """
    if max_depth <= 0:
        return []
    out: list[dict[str, Any]] = []
    for n in nodes:
        ch = n.get("children") or []
        if depth >= max_depth:
            new_children: list[dict[str, Any]] = []
        else:
            new_children = _prune_user_tree_to_depth(ch, max_depth, depth + 1)
        out.append({**n, "children": new_children})
    return out


def _index_nodes_by_heading_para(
    nodes: list[dict[str, Any]],
    out: dict[int, dict[str, Any]],
) -> None:
    for n in nodes:
        hpi = n.get("heading_para_index")
        if isinstance(hpi, int):
            out[hpi] = n
        _index_nodes_by_heading_para(n.get("children") or [], out)


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

    Comparison depth follows the **template** only:

    - The user outline is pruned to ``_template_max_depth(template)`` so only the same number
      of outline levels as the template participate in matching (extra deeper headings are
      ignored for structure checks).
    - If a template node has no children, any further headings under the matched user node
      are ignored (not reported as extra sections).
    """
    path_prefix = path_prefix or []
    original_user_nodes = user_nodes
    max_depth = _template_max_depth(template_nodes)
    if max_depth > 0:
        user_nodes = _prune_user_tree_to_depth(user_nodes, max_depth)
    mapping: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    original_nodes_by_hpi: dict[int, dict[str, Any]] = {}
    _index_nodes_by_heading_para(original_user_nodes, original_nodes_by_hpi)

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
                hpi = uc.get("heading_para_index")
                if isinstance(hpi, int) and hpi in original_nodes_by_hpi:
                    mapping[tid] = original_nodes_by_hpi[hpi]
                else:
                    # Fallback to the compared node if index lookup is unavailable.
                    mapping[tid] = uc
            next_t = tc.get("children") or []
            if not next_t:
                # Template ends here: deeper headings in the user file are out of scope.
                walk([], [], path + [want])
            else:
                walk(next_t, uc.get("children") or [], path + [want])
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
