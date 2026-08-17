# -*- coding: utf-8 -*-
"""
scripts/upload_fixed_template.py
上传单个用户修好的 docx 到 MinIO + 更新 DB templates 表

用法:
  python scripts/upload_fixed_template.py --scheme-type-id 9 --local-file "C:\\..\\9_吊篮.docx"
  python scripts/upload_fixed_template.py --scheme-type-id 9 --local-file "..." --dry-run

行为:
  1. SELECT 旧 object_key / original_filename（保存到 _upload_log.csv，rollback 用）
  2. 生成新 object_key (保持旧 key 不删，rollback 路径)
  3. 上传到 MinIO（覆盖模式下，新 key 与旧 key 不同）
  4. UPDATE templates SET object_key=新, original_filename=新 WHERE id=...
  5. 写一行 CSV 日志（成功/失败都记录）
  6. 出错时：尝试 DELETE 新上传的对象（避免孤儿）

依赖:
  pip install minio
"""
import argparse
import base64
import csv
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

# MinIO 配置
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "10.73.2.21:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "review")
MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() == "true"

# SSH 跳板链
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

DEFAULT_LOG_DIR = r"C:\Users\Administrator\Desktop\一建方案审核\修复方案"


def ssh_mysql_query(sql: str, timeout: int = 60) -> tuple[int, str]:
    """通过 SSH 跳板链在远端 MySQL 跑 SQL，返回 (exit_code, stdout)

    关键：ssh_chain.sh 内部已经做了 base64 编码（stdin 收 plain text
    → 编码 → 传到目标 → 目标解码 → bash 执行）。我们只要把 plain text
    远程命令作为 stdin 传给 ssh_chain.sh 即可。
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
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout
    )
    return proc.returncode, proc.stdout


def mysql_escape(s: str) -> str:
    """escape SQL 字符串字面量"""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def fetch_template_row(scheme_type_id: int) -> dict | None:
    """SELECT 当前 templates 行。返回 dict 或 None"""
    sql = (
        f"SELECT id, scheme_type_id, minio_bucket, object_key, original_filename "
        f"FROM templates WHERE scheme_type_id={scheme_type_id}"
    )
    rc, out = ssh_mysql_query(sql)
    if rc != 0:
        print(f"[ERROR] DB SELECT failed (exit={rc}): {out}")
        return None
    for ln in out.splitlines():
        if "\t" in ln and not ln.startswith("id") and not ln.startswith("scheme_type_id"):
            parts = ln.split("\t")
            if len(parts) >= 5:
                try:
                    return {
                        "id": int(parts[0]),
                        "scheme_type_id": int(parts[1]),
                        "minio_bucket": parts[2],
                        "object_key": parts[3],
                        "original_filename": parts[4],
                    }
                except ValueError:
                    continue
    return None


def update_template_db(template_id: int, new_object_key: str, new_filename: str) -> int:
    """UPDATE templates 表，返回 mysql exit code"""
    sql = (
        f"UPDATE templates SET object_key='{mysql_escape(new_object_key)}', "
        f"original_filename='{mysql_escape(new_filename)}' "
        f"WHERE id={template_id}"
    )
    rc, out = ssh_mysql_query(sql)
    if out.strip():
        print(out.strip())
    return rc


def delete_object_safely(client, bucket: str, obj_key: str):
    """删除一个 MinIO 对象（忽略不存在）"""
    try:
        client.remove_object(bucket, obj_key)
    except Exception as e:
        print(f"  [WARN] DELETE {obj_key} failed: {e}")


def append_log(log_path: Path, row: dict, header: list):
    """追加一行 CSV（不存在则先写 header）"""
    new_file = not log_path.exists()
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        if new_file:
            w.writeheader()
        w.writerow(row)


def rollback_from_log(log_dir: Path, template_id: int, dry_run: bool = False) -> int:
    """从 _upload_log.csv 找该 template_id 最新成功条目，回滚 DB + 删新对象"""
    log_path = log_dir / "_upload_log.csv"
    if not log_path.exists():
        print(f"[ERROR] log not found: {log_path}")
        return 1
    with open(log_path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        rows = [row for row in r if row.get("template_id") == str(template_id) and row.get("result") == "ok"]
    if not rows:
        print(f"[ERROR] no ok row for template_id={template_id} in {log_path}")
        return 1
    latest = rows[-1]
    print(f"[ROLLBACK] using log row at {latest['timestamp']}")
    print(f"  old_object_key = {latest['old_object_key']}")
    print(f"  new_object_key = {latest['new_object_key']}")
    print(f"  old_original_filename = {latest['old_original_filename']}")
    if dry_run:
        print("[DRY-RUN] stop here")
        return 0
    # 1. UPDATE DB 回旧值
    rc = update_template_db(template_id, latest["old_object_key"], latest["old_original_filename"])
    if rc != 0:
        print(f"[ERROR] DB UPDATE failed exit={rc}")
        return rc
    print(f"[OK] DB reverted to old values")
    # 2. DELETE 新对象
    try:
        from minio import Minio
        client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY,
                       secret_key=MINIO_SECRET_KEY, secure=MINIO_SECURE)
        # 找该模板的 bucket（从 DB 查）
        row = fetch_template_row(None)  # 重新查（已 rollback 不重要）
        bucket = row["minio_bucket"] if row else MINIO_BUCKET
        delete_object_safely(client, bucket, latest["new_object_key"])
        print(f"[OK] Deleted new object {latest['new_object_key']}")
    except Exception as e:
        print(f"[WARN] Failed to delete new object: {e}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheme-type-id", type=int, help="模板的 scheme_type_id")
    parser.add_argument("--local-file", help="本地修好的 docx 路径")
    parser.add_argument("--log-dir", default=DEFAULT_LOG_DIR, help="日志目录")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不上传/不更新 DB")
    parser.add_argument("--rollback", action="store_true", help="从上传日志回滚到旧值（需要 --template-id）")
    parser.add_argument("--template-id", type=int, help="回滚用：指定 templates.id")
    args = parser.parse_args()

    if args.rollback:
        if not args.template_id:
            print("[ERROR] rollback 需要 --template-id")
            sys.exit(1)
        rc = rollback_from_log(Path(args.log_dir), args.template_id, args.dry_run)
        sys.exit(rc)
    if not args.scheme_type_id or not args.local_file:
        print("[ERROR] 需要 --scheme-type-id 和 --local-file")
        sys.exit(1)

    local_path = Path(args.local_file)
    if not local_path.exists():
        print(f"[ERROR] local file not found: {local_path}")
        sys.exit(1)
    new_filename = local_path.name
    # 去掉前缀 scheme_type_id_ 和后缀 .docx 标准化
    # 存到 DB 时用纯 original_filename，但本地上传路径可保留前缀
    # 策略：parsed_name = new_filename（如果带 scheme_type_id 前缀就剥掉）
    base = new_filename
    if "_" in base:
        prefix, rest = base.split("_", 1)
        if prefix.isdigit() and int(prefix) == args.scheme_type_id:
            new_filename_db = rest
        else:
            new_filename_db = base
    else:
        new_filename_db = base

    print(f"[INFO] scheme_type_id = {args.scheme_type_id}")
    print(f"[INFO] local file   = {local_path}  ({local_path.stat().st_size} bytes)")
    print(f"[INFO] new filename = {new_filename_db}")
    if args.dry_run:
        print("[DRY-RUN] stop here, no upload / DB update")

    # 1. 查 DB 旧值
    print("[STEP 1] SELECT old template row...")
    old = fetch_template_row(args.scheme_type_id)
    if not old:
        print(f"[ERROR] No template with scheme_type_id={args.scheme_type_id}")
        sys.exit(1)
    print(f"[OK] Old: id={old['id']} bucket={old['minio_bucket']} key={old['object_key']} filename={old['original_filename']}")

    # 2. 生成新 object_key
    new_object_key = f"templates/{args.scheme_type_id}/{uuid.uuid4().hex}.docx"
    print(f"[INFO] New object_key = {new_object_key}")

    # 3. 准备日志
    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "_upload_log.csv"
    log_header = [
        "timestamp", "scheme_type_id", "template_id",
        "old_object_key", "old_original_filename",
        "new_object_key", "new_original_filename",
        "local_file", "result", "error",
    ]

    log_row = {
        "timestamp": datetime.now().isoformat(),
        "scheme_type_id": args.scheme_type_id,
        "template_id": old["id"],
        "old_object_key": old["object_key"],
        "old_original_filename": old["original_filename"],
        "new_object_key": new_object_key,
        "new_original_filename": new_filename_db,
        "local_file": str(local_path),
        "result": "",
        "error": "",
    }

    if args.dry_run:
        log_row["result"] = "dry-run"
        append_log(log_path, log_row, log_header)
        print(f"[OK] Dry-run logged to {log_path}")
        return

    # 4. 上传到 MinIO
    print("[STEP 2] Uploading to MinIO...")
    try:
        from minio import Minio
        client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY,
                       secret_key=MINIO_SECRET_KEY, secure=MINIO_SECURE)
    except Exception as e:
        log_row["result"] = "minio_connect_fail"
        log_row["error"] = f"{type(e).__name__}: {e}"
        append_log(log_path, log_row, log_header)
        print(f"[ERROR] MinIO connect failed: {e}")
        sys.exit(1)

    try:
        with open(local_path, "rb") as f:
            data = f.read()
        from minio.commonconfig import ContentType
        result = client.put_object(
            old["minio_bucket"], new_object_key,
            data, length=len(data),
            content_type=ContentType.from_file_path(str(local_path)) or "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        print(f"[OK] Uploaded: {result.object_name}  etag={result.etag}  size={len(data)}")
    except Exception as e:
        log_row["result"] = "upload_fail"
        log_row["error"] = f"{type(e).__name__}: {e}"
        append_log(log_path, log_row, log_header)
        print(f"[ERROR] Upload failed: {e}")
        sys.exit(1)

    # 5. UPDATE DB
    print("[STEP 3] UPDATE templates DB row...")
    rc = update_template_db(old["id"], new_object_key, new_filename_db)
    if rc != 0:
        log_row["result"] = "db_update_fail"
        log_row["error"] = f"mysql exit={rc}"
        append_log(log_path, log_row, log_header)
        # 回滚：尝试删 MinIO 新对象
        print(f"[ROLLBACK] DELETE new MinIO object {new_object_key}")
        delete_object_safely(client, old["minio_bucket"], new_object_key)
        print(f"[ERROR] DB UPDATE failed; new object deleted. See {log_path}")
        sys.exit(1)

    # 6. 成功
    log_row["result"] = "ok"
    append_log(log_path, log_row, log_header)
    print(f"\n[OK] Upload + DB update SUCCESS")
    print(f"[INFO] Old object key (still in MinIO for rollback): {old['object_key']}")
    print(f"[INFO] New object key (active): {new_object_key}")
    print(f"[INFO] Log: {log_path}")
    print(f"\n[ROLLBACK] To revert: run")
    print(f"  python scripts/upload_fixed_template.py --rollback --template-id {old['id']}")


if __name__ == "__main__":
    main()
