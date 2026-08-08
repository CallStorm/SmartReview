"""批量清理 `templates.parsed_structure.nodes[].review_prompt` 里的指定文本。

默认 dry-run：只打印哪些节点会被改，不写 DB。
传 `--apply` 才真正写库。

幂等：再次运行不会有任何改动（target 文本已被删除）。

用法（从仓库根目录）：
    python backend/scripts/strip_review_prompt_phrase.py            # dry-run
    python backend/scripts/strip_review_prompt_phrase.py --apply    # 真正改库
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.scheme_template import SchemeTemplate

# 要从每个 review_prompt 里删掉的整段子串（精确匹配）
TARGET = "检查该小节中是否含有错别字和错乱的序号，统一指出。序号错乱只需检查序号的数值是否错乱即可"

# 打印时显示前后各多少字符的上下文
SNIPPET_PAD = 24


def _walk_nodes(nodes, *, on_match) -> tuple[int, int]:
    """递归遍历 nodes 树，命中 review_prompt 含 TARGET 的节点就调 on_match。

    返回 (扫描的节点数, 改动的节点数)。
    """
    scanned = 0
    modified = 0
    for n in nodes or []:
        scanned += 1
        rp = n.get("review_prompt")
        if isinstance(rp, str) and TARGET in rp:
            on_match(n)
            n["review_prompt"] = rp.replace(TARGET, "")
            modified += 1
        if n.get("children"):
            child_scanned, child_modified = _walk_nodes(
                n["children"], on_match=on_match
            )
            scanned += child_scanned
            modified += child_modified
    return scanned, modified


def _snippet(text: str, anchor: str | None = None) -> str:
    """截取片段用于打印：包含 anchor 前后 SNIPPET_PAD 字符（若 anchor 不在 text 里则取前 60 字符）。"""
    if not text:
        return "(空)"
    if anchor is None or anchor not in text:
        return text[:60] + ("…" if len(text) > 60 else "")
    pos = text.index(anchor)
    s = max(0, pos - SNIPPET_PAD)
    e = min(len(text), pos + len(anchor) + SNIPPET_PAD)
    out = text[s:e]
    if s > 0:
        out = "…" + out
    if e < len(text):
        out = out + "…"
    return out


def run(*, apply: bool) -> int:
    db: Session = SessionLocal()
    try:
        templates = db.query(SchemeTemplate).order_by(SchemeTemplate.id.asc()).all()

        templates_scanned = 0
        nodes_scanned = 0
        templates_modified = 0
        nodes_modified = 0

        try:
            for t in templates:
                templates_scanned += 1
                if not (t.parsed_structure or "").strip():
                    continue
                try:
                    struct = json.loads(t.parsed_structure)
                except json.JSONDecodeError as e:
                    print(
                        f"⚠️  跳过 template id={t.id}: parsed_structure 解析失败 {e}",
                        file=sys.stderr,
                    )
                    continue

                nodes = struct.get("nodes") if isinstance(struct, dict) else None
                if not isinstance(nodes, list):
                    continue

                # 用闭包捕获当前 template 的展示信息
                def _on_match(n: dict) -> None:
                    scheme = t.scheme_type
                    scheme_label = (
                        f"{scheme.category} / {scheme.name}"
                        if scheme is not None
                        else "(无方案类型)"
                    )
                    old_rp = n.get("review_prompt") or ""
                    print(
                        f"  template id={t.id}  方案={scheme_label}\n"
                        f"    节点 id={n.get('id')!r}  标题={n.get('title')!r}  层级={n.get('level')}\n"
                        f"    before: {_snippet(old_rp, TARGET)}\n"
                        f"    after : {_snippet(old_rp.replace(TARGET, ''))}"
                    )

                scanned, modified = _walk_nodes(nodes, on_match=_on_match)
                nodes_scanned += scanned
                if modified:
                    nodes_modified += modified
                    templates_modified += 1
                    t.parsed_structure = json.dumps(struct, ensure_ascii=False)

            if apply and nodes_modified:
                db.commit()
            else:
                # dry-run 或无改动：回滚（保证 db 状态不变）
                db.rollback()
        except Exception:
            db.rollback()
            raise

        mode = "已应用" if (apply and nodes_modified) else "dry-run（未改库）"
        print("")
        print("=" * 60)
        print(f"模式: {mode}")
        print(f"扫描模板: {templates_scanned}")
        print(f"扫描节点: {nodes_scanned}")
        print(f"改动模板: {templates_modified}")
        print(f"改动节点: {nodes_modified}")
        print("=" * 60)
        if not apply:
            print("提示：传 --apply 才会真正写库。")
        return 0
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="批量清理模板树节点 review_prompt 里的指定子串"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正写入数据库（默认 dry-run）",
    )
    args = parser.parse_args()
    sys.exit(run(apply=args.apply))


if __name__ == "__main__":
    main()
