# -*- coding: utf-8 -*-
"""
scripts/batch_upload_fixed_templates.py
批量把本地修复后的 docx 覆盖到 MinIO 的**原 object_key**（原地覆盖）。

策略：原 key PUT 替换 → DB templates 表无需改动 → 系统下次审核自动读到新版。
不做 DB UPDATE，不做 parsed_at 重置，不做旧文件备份。

用法:
  # 1) 预览计划：什么都不上传
  python scripts/batch_upload_fixed_templates.py --dry-run

  # 2) 单文件试水：只覆盖 scheme_type_id=9
  python scripts/batch_upload_fixed_templates.py --only 9 --dry-run
  python scripts/batch_upload_fixed_templates.py --only 9

  # 3) 多个试水：9,10,11
  python scripts/batch_upload_fixed_templates.py --only 9,10,11

  # 4) 全部 26 个批量覆盖
  python scripts/batch_upload_fixed_templates.py

  # 5) 跳过已成功上传过的（看 _upload_log.csv 里 result==ok 的）
  python scripts/batch_upload_fixed_templates.py --skip-uploaded

输入:
  C:\\Users\\Administrator\\Desktop\\一建方案审核\\修复方案\\_manifest.json

输出:
  同目录下 _upload_log.csv  (追加，列: timestamp, scheme_type_id, template_id,
                             minio_bucket, object_key, local_path, size_bytes,
                             result, error)

依赖:
  pip install minio
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# MinIO 配置
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "10.73.2.21:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET_DEFAULT = os.environ.get("MINIO_BUCKET", "review")
MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() == "true"

DEFAULT_MANIFEST_DIR = r"C:\Users\Administrator\Desktop\一建方案审核\修复方案"
DEFAULT_MANIFEST = "_manifest.json"
LOG_FILENAME = "_upload_log.csv"

LOG_HEADER = [
    "timestamp", "scheme_type_id", "template_id",
    "minio_bucket", "object_key", "original_filename",
    "local_path", "size_bytes",
    "result", "error",
]


def load_manifest(manifest_path: Path) -> list[dict]:
    """读 _manifest.json，返回 templates 列表"""
    if not manifest_path.exists():
        print(f"[ERROR] manifest not found: {manifest_path}")
        sys.exit(1)
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    templates = data.get("templates", [])
    if not templates:
        print(f"[ERROR] manifest has no templates: {manifest_path}")
        sys.exit(1)
    return templates


def filter_by_only(templates: list[dict], only: list[int] | None) -> list[dict]:
    """按 --only 给出的 scheme_type_id 列表过滤"""
    if not only:
        return templates
    only_set = set(only)
    filtered = [t for t in templates if t["scheme_type_id"] in only_set]
    missed = only_set - {t["scheme_type_id"] for t in filtered}
    if missed:
        print(f"[WARN] --only 中未匹配的 scheme_type_id: {sorted(missed)}")
    return filtered


def already_uploaded_ids(log_path: Path) -> set[int]:
    """读日志，返回已 result==ok 的 scheme_type_id 集合（用于 --skip-uploaded）"""
    if not log_path.exists():
        return set()
    ids = set()
    with open(log_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("result") == "ok":
                try:
                    ids.add(int(row["scheme_type_id"]))
                except (KeyError, ValueError):
                    pass
    return ids


def append_log(log_path: Path, row: dict) -> None:
    new_file = not log_path.exists()
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_HEADER)
        if new_file:
            w.writeheader()
        # 只取 header 中存在的字段，缺失填空
        w.writerow({k: row.get(k, "") for k in LOG_HEADER})


def minio_connect():
    from minio import Minio
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )
    buckets = [b.name for b in client.list_buckets()]
    print(f"[OK] MinIO connected: {MINIO_ENDPOINT}  buckets={buckets}")
    return client


def stat_object(client, bucket: str, obj_key: str) -> dict | None:
    """拿 MinIO 上现有对象的元数据（size/etag）。失败返回 None"""
    try:
        stat = client.stat_object(bucket, obj_key)
        return {
            "size": stat.size,
            "etag": stat.etag,
            "last_modified": stat.last_modified.isoformat() if stat.last_modified else "",
        }
    except Exception as e:
        return None


def upload_one(client, t: dict, dry_run: bool) -> dict:
    """上传一个模板，返回 log row dict"""
    scheme_id = t["scheme_type_id"]
    bucket = t.get("minio_bucket") or MINIO_BUCKET_DEFAULT
    obj_key = t["object_key"]
    local_path = Path(t["local_path"])
    orig_filename = t.get("original_filename", "")

    row = {
        "timestamp": datetime.now().isoformat(),
        "scheme_type_id": scheme_id,
        "template_id": t.get("template_id", ""),
        "minio_bucket": bucket,
        "object_key": obj_key,
        "original_filename": orig_filename,
        "local_path": str(local_path),
        "size_bytes": 0,
        "result": "",
        "error": "",
    }

    # 1. 本地文件校验
    if not local_path.exists():
        row["result"] = "local_missing"
        row["error"] = f"local file not found: {local_path}"
        return row
    if local_path.name.startswith("~$"):
        row["result"] = "skip_lock_file"
        row["error"] = "Word lock file, skipped"
        return row
    if local_path.suffix.lower() != ".docx":
        row["result"] = "skip_non_docx"
        row["error"] = f"not a .docx file: {local_path.name}"
        return row

    local_size = local_path.stat().st_size
    row["size_bytes"] = local_size

    # 2. 拿 MinIO 上现有对象的 size（用于后面日志对比）
    old_stat = stat_object(client, bucket, obj_key)
    old_size = old_stat["size"] if old_stat else "(不存在)"

    print(f"\n[{'DRY-RUN' if dry_run else 'UPLOAD'}] scheme_type_id={scheme_id}  template_id={t.get('template_id')}")
    print(f"  local : {local_path}  ({local_size} bytes)")
    print(f"  remote: {bucket}/{obj_key}  (current size={old_size})")

    if dry_run:
        row["result"] = "dry-run"
        return row

    # 3. PUT 覆盖（用 fput_object 直接传文件路径，避免新版 SDK 对 length=-1 的限制）
    try:
        ct = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        result = client.fput_object(
            bucket, obj_key,
            str(local_path),
            content_type=ct,
        )
        # 4. 校验：再 stat 一次
        new_stat = stat_object(client, bucket, obj_key)
        new_size = new_stat["size"] if new_stat else "?"
        new_etag = new_stat["etag"] if new_stat else "?"
        print(f"  [OK]   uploaded etag={result.etag}  remote_size={new_size}")
        if new_stat and new_stat["size"] != local_size:
            row["result"] = "size_mismatch"
            row["error"] = f"remote size {new_stat['size']} != local {local_size}"
            return row
        row["result"] = "ok"
        row["error"] = f"etag={result.etag}; remote_size={new_size}"
        return row
    except Exception as e:
        row["result"] = "upload_fail"
        row["error"] = f"{type(e).__name__}: {e}"
        return row


def main():
    parser = argparse.ArgumentParser(
        description="批量覆盖 MinIO 原 object_key（原地覆盖，DB 不动）"
    )
    parser.add_argument("--manifest-dir", default=DEFAULT_MANIFEST_DIR,
                        help=f"含 _manifest.json 的目录 (default: {DEFAULT_MANIFEST_DIR})")
    parser.add_argument("--only", type=str, default=None,
                        help="只上传指定 scheme_type_id，逗号分隔，如 '9' 或 '9,10,11'")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印计划，不上传")
    parser.add_argument("--skip-uploaded", action="store_true",
                        help="跳过 _upload_log.csv 里 result==ok 的")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="跳过交互确认")
    args = parser.parse_args()

    manifest_path = Path(args.manifest_dir) / DEFAULT_MANIFEST
    log_path = Path(args.manifest_dir) / LOG_FILENAME

    print(f"[INFO] manifest: {manifest_path}")
    print(f"[INFO] log     : {log_path}")

    templates = load_manifest(manifest_path)
    print(f"[OK] manifest loaded: {len(templates)} templates")

    # 解析 --only
    only_ids = None
    if args.only:
        try:
            only_ids = [int(x.strip()) for x in args.only.split(",") if x.strip()]
        except ValueError as e:
            print(f"[ERROR] --only 解析失败: {e}")
            sys.exit(1)

    # --skip-uploaded
    if args.skip_uploaded:
        uploaded = already_uploaded_ids(log_path)
        if uploaded:
            print(f"[INFO] --skip-uploaded: 跳过已 ok 的 {len(uploaded)} 个: {sorted(uploaded)}")
            templates = [t for t in templates if t["scheme_type_id"] not in uploaded]

    # 过滤
    targets = filter_by_only(templates, only_ids)
    if not targets:
        print("[ERROR] 过滤后没有目标模板")
        sys.exit(1)

    # 排序：按 scheme_type_id 升序，方便看
    targets.sort(key=lambda x: x["scheme_type_id"])

    print(f"\n[PLAN] 将要上传 {len(targets)} 个模板:")
    for t in targets:
        print(f"  - scheme_type_id={t['scheme_type_id']:>2}  {t['original_filename']}")
    print()

    if args.dry_run:
        # Dry-run：连接 MinIO 拿每个对象的当前 size，但不上传
        try:
            client = minio_connect()
        except Exception as e:
            print(f"[ERROR] MinIO 连接失败: {e}")
            sys.exit(1)
        results = []
        for t in targets:
            r = upload_one(client, t, dry_run=True)
            results.append(r)
            append_log(log_path, r)
        ok = sum(1 for r in results if r["result"] in ("dry-run", "ok"))
        fail = sum(1 for r in results if r["result"] not in ("dry-run", "ok"))
        print(f"\n[DRY-RUN DONE] {ok}/{len(results)} planned, {fail} errored (see log)")
        return

    # 正式上传：交互确认
    if not args.yes:
        print("[CONFIRM] 确认要原地覆盖上面这些 MinIO 对象吗？")
        print("  注意：原 object_key 的内容会被替换，DB 不动。")
        ans = input("  输入 yes 继续: ").strip().lower()
        if ans != "yes":
            print("[ABORT] 用户取消")
            sys.exit(0)

    try:
        client = minio_connect()
    except Exception as e:
        print(f"[ERROR] MinIO 连接失败: {e}")
        sys.exit(1)

    results = []
    for t in targets:
        r = upload_one(client, t, dry_run=False)
        results.append(r)
        append_log(log_path, r)

    # 汇总
    print("\n" + "=" * 60)
    print("[SUMMARY]")
    by_result: dict[str, list] = {}
    for r in results:
        by_result.setdefault(r["result"], []).append(r)
    for k in ("ok", "upload_fail", "local_missing", "size_mismatch",
              "skip_lock_file", "skip_non_docx", "dry-run"):
        if k in by_result:
            ids = [r["scheme_type_id"] for r in by_result[k]]
            print(f"  {k:>16}: {len(ids):>2}  {ids}")
    print()
    print(f"  log: {log_path}")

    fail_count = sum(len(v) for k, v in by_result.items()
                     if k not in ("ok", "dry-run"))
    if fail_count:
        print(f"\n[WARN] {fail_count} 个失败，详见 log")
        sys.exit(2)
    print(f"\n[OK] 全部 {len(results)} 个上传成功")


if __name__ == "__main__":
    main()