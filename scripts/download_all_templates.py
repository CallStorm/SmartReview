# -*- coding: utf-8 -*-
"""
scripts/download_all_templates.py
下载所有 26 个 docx 模板到本地目录（用于人工修复 + 后续 F9 更新目录）

用法:
  python scripts/download_all_templates.py
  python scripts/download_all_templates.py --scheme-type-id 9   # 单个
  python scripts/download_all_templates.py --out-dir D:\\other   # 自定义输出目录

输出:
  <out-dir>/{scheme_type_id}_{NN}_{original_filename}
  <out-dir>/_manifest.json   (完整 26 个对象清单 + 下载结果)
  <out-dir>/_tpl_info.csv    (DB 原始信息，给后续 upload 脚本用)

依赖:
  pip install minio boto3
"""
import argparse
import csv
import json
import os
import sys
import base64
import subprocess
from pathlib import Path
from datetime import datetime

# MinIO 配置 (从 deploy.env 加载后传入)
import os
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "10.73.2.21:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "review")
MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() == "true"

# SSH 跳板链（用于查 DB）
SSH_CHAIN = "/mnt/c/Users/Administrator/Desktop/SmartReview/scripts/ssh_chain.sh"
SSH_BASTION_HOST = os.environ.get("SSH_BASTION_HOST", "10.73.2.80")
SSH_BASTION_USER = os.environ.get("SSH_BASTION_USER", "root")
SSH_BASTION_PASS = os.environ.get("SSH_BASTION_PASSWORD", "")
SSH_TARGET_HOST = os.environ.get("SSH_TARGET_HOST", "10.73.2.21")
SSH_TARGET_USER = os.environ.get("SSH_TARGET_USER", "root")
SSH_TARGET_PASS = os.environ.get("SSH_TARGET_PASSWORD", "")
MYSQL_USER = "root"
MYSQL_PASS = "changeme-strong-mysql"
MYSQL_DB = "review"
MYSQL_CONTAINER = "smartreview-main-mysql-1"

DEFAULT_OUT_DIR = r"C:\Users\Administrator\Desktop\一建方案审核\修复方案"
LOCAL_DOCX_GLOB = "*.docx"


def ssh_mysql_query(sql: str) -> str:
    """通过 SSH 跳板链在远端 MySQL 跑 SQL，返回 stdout 文本（UTF-8）

    关键：ssh_chain.sh 内部已经做了 base64 编码（stdin 收 plain text
    → 编码 → 传到目标 → 目标解码 → bash 执行）。我们只要把 plain text
    远程命令作为 stdin 传给 ssh_chain.sh 即可。

    之前 double-encode 出错是因为 Python 端多 base64 了一次。
    """
    remote_cmd = (
        f"docker exec -e LANG=C.UTF-8 {MYSQL_CONTAINER} mysql "
        f"--default-character-set=utf8mb4 -u{MYSQL_USER} -p'{MYSQL_PASS}' {MYSQL_DB} "
        f'-e "{sql}" 2>&1'
    )
    proc = subprocess.run(
        [
            "wsl", "bash",
            SSH_CHAIN,
            SSH_BASTION_HOST, SSH_BASTION_USER, SSH_BASTION_PASS,
            SSH_TARGET_HOST, SSH_TARGET_USER, SSH_TARGET_PASS,
        ],
        input=remote_cmd,
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return proc.stdout


def fetch_all_templates() -> list[dict]:
    # 重要：SQL 不能含 LENGTH() / IS NOT NULL 等带括号/表达式，
    # 因为 SQL 会嵌进 bash -e "..." 双引号里，括号会破坏 bash 解析。
    # 所有派生列在 Python 端算。
    sql = (
        "SELECT t.id, t.scheme_type_id, st.name, st.category, "
        "t.minio_bucket, t.object_key, t.original_filename, "
        "t.structure_match_mode, t.parsed_at "
        "FROM templates t LEFT JOIN scheme_types st ON t.scheme_type_id=st.id "
        "ORDER BY t.scheme_type_id"
    )
    out = ssh_mysql_query(sql)
    rows = []
    for ln in out.splitlines():
        if not ln.strip() or "\t" not in ln:
            continue
        # 跳过表头（id\tscheme_type_id\tname...）
        if ln.startswith("id\t"):
            continue
        parts = ln.split("\t")
        if len(parts) < 8:
            continue
        rows.append({
            "template_id": int(parts[0]),
            "scheme_type_id": int(parts[1]),
            "scheme_name": parts[2],
            "scheme_category": parts[3],
            "minio_bucket": parts[4],
            "object_key": parts[5],
            "original_filename": parts[6],
            "structure_match_mode": parts[7],
            "has_parsed": bool(parts[8]) and parts[8] not in ("", "NULL"),
            "rules_len": 0,  # 不再单独查，需要的话用 fetch_rules_len()
        })
    return rows


def fetch_rules_len(scheme_type_id: int) -> int:
    """单独查 content_review_rules 长度（仅在需要时调用）"""
    sql = f"SELECT LENGTH(content_review_rules) FROM templates WHERE scheme_type_id={scheme_type_id}"
    out = ssh_mysql_query(sql)
    for ln in out.splitlines():
        if ln.strip().isdigit():
            return int(ln.strip())
    return 0


def download_one(client, row: dict, out_dir: Path) -> dict:
    """下载单个模板到本地，返回结果 dict"""
    scheme_id = row["scheme_type_id"]
    fname = row["original_filename"]
    # 文件名加 scheme_type_id 前缀避免名字冲突
    local_name = f"{scheme_id:>02d}_{fname}"
    local_path = out_dir / local_name
    result = {
        **row,
        "local_path": str(local_path),
        "local_name": local_name,
        "downloaded": False,
        "size_bytes": 0,
        "error": None,
    }
    try:
        data = client.get_object(row["minio_bucket"], row["object_key"])
        body = data.read()
        data.close()
        data.release_conn()
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(body)
        result["downloaded"] = True
        result["size_bytes"] = len(body)
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="本地输出目录")
    parser.add_argument("--scheme-type-id", type=int, default=None, help="只下载单个（可选）")
    parser.add_argument("--skip-existing", action="store_true", help="跳过本地已存在的文件")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] MinIO: {MINIO_ENDPOINT} (bucket={MINIO_BUCKET})")
    print(f"[INFO] Out dir: {out_dir}")

    # 1. 连 MinIO
    try:
        from minio import Minio
        client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY,
                       secret_key=MINIO_SECRET_KEY, secure=MINIO_SECURE)
        buckets = [b.name for b in client.list_buckets()]
        print(f"[OK] MinIO connected. Buckets: {buckets}")
        if MINIO_BUCKET not in buckets:
            print(f"[ERROR] Bucket '{MINIO_BUCKET}' not found")
            sys.exit(1)
    except Exception as e:
        print(f"[ERROR] MinIO connect failed: {type(e).__name__}: {e}")
        sys.exit(1)

    # 2. 查 DB
    print("[INFO] Fetching template list from DB via SSH chain...")
    rows = fetch_all_templates()
    print(f"[OK] DB returned {len(rows)} templates")
    if args.scheme_type_id is not None:
        rows = [r for r in rows if r["scheme_type_id"] == args.scheme_type_id]
        print(f"[INFO] Filtered to {len(rows)} for scheme_type_id={args.scheme_type_id}")

    # 3. 下载
    results = []
    for r in rows:
        local_path = out_dir / f"{r['scheme_type_id']:>02d}_{r['original_filename']}"
        if args.skip_existing and local_path.exists():
            print(f"[SKIP] {local_path.name} (exists)")
            results.append({**r, "local_path": str(local_path),
                            "local_name": local_path.name,
                            "downloaded": True,
                            "size_bytes": local_path.stat().st_size,
                            "error": "skipped_existing"})
            continue
        print(f"[GET] scheme_type_id={r['scheme_type_id']:>2}  {r['original_filename']}  ←  {r['object_key']}")
        res = download_one(client, r, out_dir)
        status = "OK" if res["downloaded"] else "FAIL"
        print(f"  [{status}] {res['local_name']}  ({res['size_bytes']} bytes)")
        if res["error"]:
            print(f"  [ERROR] {res['error']}")
        results.append(res)

    # 4. 写 manifest
    manifest_path = out_dir / "_manifest.json"
    csv_path = out_dir / "_tpl_info.csv"
    summary = {
        "generated_at": datetime.now().isoformat(),
        "minio_endpoint": MINIO_ENDPOINT,
        "minio_bucket": MINIO_BUCKET,
        "out_dir": str(out_dir),
        "total": len(rows),
        "downloaded_ok": sum(1 for r in results if r["downloaded"]),
        "failed": sum(1 for r in results if not r["downloaded"]),
        "templates": results,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "template_id", "scheme_type_id", "scheme_name", "scheme_category",
            "minio_bucket", "object_key", "original_filename",
            "local_name", "local_path", "size_bytes", "downloaded", "error",
        ])
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k) for k in w.fieldnames})

    print(f"\n[OK] {summary['downloaded_ok']}/{summary['total']} downloaded, {summary['failed']} failed")
    print(f"[OK] Manifest: {manifest_path}")
    print(f"[OK] CSV:     {csv_path}")
    if summary["failed"] > 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
