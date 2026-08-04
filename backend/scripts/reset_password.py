"""Reset a user's password by username or phone. Run from repo root:
    python backend/scripts/reset_password.py -u admin
Or from backend/:
    python scripts/reset_password.py -u admin
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.security import hash_password
from app.database import SessionLocal
from app.models.user import User


def main() -> None:
    parser = argparse.ArgumentParser(description="重置 SmartReview 用户密码")
    parser.add_argument("-u", "--username", help="登录用户名（与 --phone 二选一）")
    parser.add_argument("-p", "--phone", help="手机号（与 --username 二选一）")
    args = parser.parse_args()

    if not (args.username or args.phone):
        parser.error("必须提供 -u 用户名 或 -p 手机号")

    password = getpass.getpass("输入新密码: ")
    if not password:
        print("密码不能为空", file=sys.stderr)
        sys.exit(1)
    confirm = getpass.getpass("再次输入新密码: ")
    if password != confirm:
        print("两次输入的密码不一致", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        q = db.query(User)
        user = (
            q.filter(User.username == args.username).first()
            if args.username
            else q.filter(User.phone == args.phone).first()
        )
        if user is None:
            print("未找到该用户", file=sys.stderr)
            sys.exit(1)
        user.password_hash = hash_password(password)
        db.commit()
        print(f"已重置密码: id={user.id} username={user.username} role={user.role.value}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
