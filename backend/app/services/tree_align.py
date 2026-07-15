"""Align user document tree to template tree by heading titles."""

from __future__ import annotations

from typing import Any, Callable, Literal

SEMANTIC_LOW_CONFIDENCE_THRESHOLD = 0.6


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


def _record(
    *,
    tid: str,
    title: str,
    path: list[str],
    user_title: str | None,
    hpi: int | None,
    method: str,
    confidence: float | None = None,
    low_confidence: bool = False,
) -> dict[str, Any]:
    return {
        "template_node_id": tid,
        "template_title": title,
        "title_path": list(path),
        "user_title": user_title,
        "heading_para_index": hpi,
        "match_method": method,
        "confidence": confidence,
        "low_confidence": low_confidence,
    }


def _normalized_match(
    want: str,
    candidates: list[tuple[int, dict[str, Any]]],
) -> tuple[int | None, str]:
    """Exact-on-normalized match. Returns (candidate_index, method)."""
    from app.services.title_normalize import normalize_title_for_match

    want_n = normalize_title_for_match(want)
    for idx, uc in candidates:
        if normalize_title_for_match(_node_title(uc)) == want_n:
            return idx, "normalized"
    return None, "normalized"


def _resolve_llm_pairs(
    raw: list[dict[str, Any]],
    still_pending: list[dict[str, Any]],
    remaining: list[tuple[int, dict[str, Any]]],
    used: set[int],
) -> list[tuple[dict[str, Any], int | None, float, bool]]:
    """Enforce 1:1 from LLM output. Higher confidence wins on conflicts."""
    if not isinstance(raw, list):
        return []
    title_to_tc = {str(tc.get("title") or ""): tc for tc in still_pending}
    title_to_uj = {str(uc.get("title") or ""): j for j, uc in remaining}
    candidates: dict[str, list[tuple[int, float, bool]]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        t_title = str(item.get("template_title") or "").strip()
        u_title = item.get("user_title")
        matched = bool(item.get("matched"))
        conf = item.get("confidence")
        try:
            conf_f = float(conf) if conf is not None else 0.0
        except (TypeError, ValueError):
            conf_f = 0.0
        tc = title_to_tc.get(t_title)
        if tc is None or not matched or not isinstance(u_title, str):
            continue
        uj = title_to_uj.get(u_title.strip())
        if uj is None or uj in used:
            continue
        candidates.setdefault(t_title, []).append((uj, conf_f, True))

    out: list[tuple[dict[str, Any], int | None, float, bool]] = []
    assigned_u: set[int] = set()
    order = sorted(
        still_pending,
        key=lambda tc: max(
            (c for _, c, _ in candidates.get(str(tc.get("title") or ""), [])),
            default=0.0,
        ),
        reverse=True,
    )
    for tc in order:
        t_title = str(tc.get("title") or "")
        cands = [
            (uj, c, m)
            for uj, c, m in candidates.get(t_title, [])
            if uj not in assigned_u
        ]
        if not cands:
            out.append((tc, None, 0.0, False))
            continue
        uj, c, m = max(cands, key=lambda x: x[1])
        assigned_u.add(uj)
        out.append((tc, uj, c, m))
    return out


def align_template_user_trees(
    template_nodes: list[dict[str, Any]],
    user_nodes: list[dict[str, Any]],
    *,
    match_mode: Literal["exact", "fuzzy"] = "exact",
    llm_matcher: Callable[[list[str], list[str]], list[dict[str, Any]]] | None = None,
    path_prefix: list[str] | None = None,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Returns (template_id -> user_node, structure_issues, match_records).

    match_mode:
      - exact (default): whitespace-normalized exact equality only; extra user
        sections silently ignored (backward compatible).
      - fuzzy: exact -> normalized -> LLM (via llm_matcher) per level; unmatched
        template sections become missing_section (error); extra user sections
        become extra_section (info).

    match_records: one entry per template node with match_method in
    exact|normalized|semantic|missing.
    """
    path_prefix = path_prefix or []
    original_user_nodes = user_nodes
    max_depth = _template_max_depth(template_nodes)
    if max_depth > 0:
        user_nodes = _prune_user_tree_to_depth(user_nodes, max_depth)
    mapping: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    original_nodes_by_hpi: dict[int, dict[str, Any]] = {}
    _index_nodes_by_heading_para(original_user_nodes, original_nodes_by_hpi)

    def _map_user_node(tid: str, uc: dict[str, Any]) -> None:
        if not tid:
            return
        hpi = uc.get("heading_para_index")
        if isinstance(hpi, int) and hpi in original_nodes_by_hpi:
            mapping[tid] = original_nodes_by_hpi[hpi]
        else:
            mapping[tid] = uc

    def _report_extras(
        u_children: list[dict[str, Any]],
        used: set[int],
        path: list[str],
    ) -> None:
        if match_mode != "fuzzy":
            return
        for j, uc in enumerate(u_children):
            if j in used:
                continue
            utitle = str(uc.get("title") or "")
            issues.append(
                {
                    "kind": "extra_section",
                    "message": f"多余章节：{utitle}",
                    "user_title": utitle,
                    "heading_para_index": uc.get("heading_para_index"),
                    "title_path": path + [utitle],
                }
            )

    def _recurse(
        tc: dict[str, Any],
        uc: dict[str, Any] | None,
        path: list[str],
    ) -> None:
        next_t = tc.get("children") or []
        if not next_t:
            return
        if uc is None:
            for sub in next_t:
                sid = str(sub.get("id") or "")
                swant = _node_title(sub)
                issues.append(
                    {
                        "kind": "missing_section",
                        "message": f"缺少章节：{swant}",
                        "template_node_id": sid,
                        "title_path": path + [swant],
                    }
                )
                records.append(
                    _record(
                        tid=sid,
                        title=swant,
                        path=path + [swant],
                        user_title=None,
                        hpi=None,
                        method="missing",
                    )
                )
                _recurse(sub, None, path + [swant])
        else:
            walk(next_t, uc.get("children") or [], path)

    def walk(
        t_children: list[dict[str, Any]],
        u_children: list[dict[str, Any]],
        path: list[str],
    ) -> None:
        used: set[int] = set()
        pending_t: list[dict[str, Any]] = []
        for tc in t_children:
            tid = str(tc.get("id") or "")
            want = _node_title(tc)
            found_j: int | None = None
            for j in range(len(u_children)):
                if j in used:
                    continue
                if _node_title(u_children[j]) == want:
                    found_j = j
                    break
            if found_j is not None:
                used.add(found_j)
                uc = u_children[found_j]
                _map_user_node(tid, uc)
                records.append(
                    _record(
                        tid=tid,
                        title=want,
                        path=path + [want],
                        user_title=str(uc.get("title") or ""),
                        hpi=uc.get("heading_para_index"),
                        method="exact",
                    )
                )
                _recurse(tc, uc, path + [want])
            else:
                pending_t.append(tc)

        if match_mode != "fuzzy" or not pending_t:
            for tc in pending_t:
                tid = str(tc.get("id") or "")
                want = _node_title(tc)
                issues.append(
                    {
                        "kind": "missing_section",
                        "message": f"缺少章节：{want}",
                        "template_node_id": tid,
                        "title_path": path + [want],
                    }
                )
                records.append(
                    _record(
                        tid=tid,
                        title=want,
                        path=path + [want],
                        user_title=None,
                        hpi=None,
                        method="missing",
                    )
                )
                if match_mode == "fuzzy":
                    _recurse(tc, None, path + [want])
            if match_mode == "fuzzy":
                _report_extras(u_children, used, path)
            return

        still_pending: list[dict[str, Any]] = []
        for tc in pending_t:
            tid = str(tc.get("id") or "")
            want = _node_title(tc)
            cand = [(j, u_children[j]) for j in range(len(u_children)) if j not in used]
            idx, _ = _normalized_match(want, cand)
            if idx is not None:
                used.add(idx)
                uc = u_children[idx]
                _map_user_node(tid, uc)
                records.append(
                    _record(
                        tid=tid,
                        title=want,
                        path=path + [want],
                        user_title=str(uc.get("title") or ""),
                        hpi=uc.get("heading_para_index"),
                        method="normalized",
                    )
                )
                _recurse(tc, uc, path + [want])
            else:
                still_pending.append(tc)

        if still_pending:
            remaining = [(j, u_children[j]) for j in range(len(u_children)) if j not in used]
            llm_pairs: list[tuple[dict[str, Any], int | None, float, bool]] = []
            if llm_matcher is not None and remaining:
                t_titles = [str(tc.get("title") or "") for tc in still_pending]
                u_titles = [str(uc.get("title") or "") for _, uc in remaining]
                try:
                    raw = llm_matcher(t_titles, u_titles)
                except Exception:
                    raw = []
                llm_pairs = _resolve_llm_pairs(raw, still_pending, remaining, used)
            for tc in still_pending:
                tid = str(tc.get("id") or "")
                want = _node_title(tc)
                pair = next((p for p in llm_pairs if p[0] is tc), None)
                if pair is not None and pair[1] is not None:
                    uc = u_children[pair[1]]
                    used.add(pair[1])
                    _map_user_node(tid, uc)
                    conf = pair[2]
                    low = conf < SEMANTIC_LOW_CONFIDENCE_THRESHOLD
                    records.append(
                        _record(
                            tid=tid,
                            title=want,
                            path=path + [want],
                            user_title=str(uc.get("title") or ""),
                            hpi=uc.get("heading_para_index"),
                            method="semantic",
                            confidence=conf,
                            low_confidence=low,
                        )
                    )
                    _recurse(tc, uc, path + [want])
                else:
                    issues.append(
                        {
                            "kind": "missing_section",
                            "message": f"缺少章节：{want}",
                            "template_node_id": tid,
                            "title_path": path + [want],
                        }
                    )
                    records.append(
                        _record(
                            tid=tid,
                            title=want,
                            path=path + [want],
                            user_title=None,
                            hpi=None,
                            method="missing",
                        )
                    )
                    _recurse(tc, None, path + [want])

        _report_extras(u_children, used, path)

    walk(template_nodes, user_nodes, path_prefix)
    return mapping, issues, records
