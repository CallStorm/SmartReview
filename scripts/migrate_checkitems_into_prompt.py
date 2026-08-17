# -*- coding: utf-8 -*-
"""
scripts/migrate_checkitems_into_prompt.py
把节点显式 check_items 迁移回 review_prompt(单一事实源),并删除 check_items 字段。

背景：
  显式 check_items 会覆盖 review_prompt 的自动拆分,且前端不可见不可编辑,
  形成维护陷阱(改提示词不生效)。迁移后:
  - review_prompt = 原 check_items 逐条换行拼接(一句一项)
  - 删除 check_items 字段,split_check_items 自动按句切分
  - 迁移前程序验证 roundtrip: split(新prompt) == 原 check_items,不一致则中止

用法:
  python scripts/migrate_checkitems_into_prompt.py --base http://localhost:5173 --dry-run
  python scripts/migrate_checkitems_into_prompt.py --base http://localhost:5173
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from app.services.checklist import split_check_items  # noqa: E402


def api(base: str, method: str, path: str, token: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(f"{base}/api{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def login(base: str, username: str, password: str) -> str:
    return api(base, "POST", "/auth/login", "", {"username": username, "password": password})["access_token"]


def walk(nodes: list):
    for n in nodes:
        yield n
        yield from walk(n.get("children") or [])


def migrate(base: str, scheme_id: int, username: str, password: str, dry_run: bool) -> None:
    token = login(base, username, password)
    tpl = api(base, "GET", f"/scheme-types/{scheme_id}/template", token)
    structure = tpl["parsed_structure"]
    if isinstance(structure, str):
        structure = json.loads(structure)

    changed: list[str] = []
    problems: list[str] = []
    for n in walk(structure.get("nodes", [])):
        raw = n.get("check_items")
        if not isinstance(raw, list) or not raw:
            continue
        tid = str(n.get("id") or "")
        items = [
            (str(e["text"]).strip() if isinstance(e, dict) else str(e).strip())
            for e in raw
            if (e.get("text") if isinstance(e, dict) else e)
        ]
        new_prompt = "\n".join(items)
        # roundtrip 验证:拼接文本重新拆分必须还原出同样的检查项
        rt_items, rt_notes = split_check_items(tid, new_prompt)
        rt_texts = [i["text"] for i in rt_items]
        if rt_texts != items:
            problems.append(
                f"{tid}: roundtrip 不一致\n  原: {items}\n  拆: {rt_texts}\n  附注: {rt_notes}"
            )
            continue
        n["review_prompt"] = new_prompt
        del n["check_items"]
        changed.append(tid)

    if problems:
        print("中止 -- 以下节点 roundtrip 验证失败,未做任何修改:")
        print("\n".join(problems))
        return
    if not changed:
        print("没有需要迁移的节点")
        return
    print(f"待迁移节点: {', '.join(changed)} (roundtrip 全部通过)")
    if dry_run:
        print("dry-run,未写入")
        return
    api(
        base,
        "PUT",
        f"/scheme-types/{scheme_id}/template/structure",
        token,
        {"parsed_structure": structure},
    )
    print("已写入。模板 updated_at 已变化,受影响节点将自动重审(预期行为)。")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5173")
    ap.add_argument("--scheme-id", type=int, default=12)
    ap.add_argument("--username", default="admin")
    ap.add_argument("--password", default="admin1234")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    migrate(args.base, args.scheme_id, args.username, args.password, args.dry_run)


if __name__ == "__main__":
    main()
