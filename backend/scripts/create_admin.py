"""Create an admin user. Run from repository root: python backend/scripts/create_admin.py ...
Or: cd backend && python scripts/create_admin.py ...
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy import or_

from app.core.security import hash_password
from app.database import SessionLocal
from app.models.user import User, UserRole


def main() -> None:
    parser = argparse.ArgumentParser(description="创建 SmartReview 管理员账号")
    parser.add_argument("-u", "--username", required=True, help="登录用户名（唯一）")
    parser.add_argument("--phone", required=True, help="手机号（唯一）")
    parser.add_argument(
        "--password",
        help="密码；若不传，将在终端提示输入（推荐）",
    )
    args = parser.parse_args()
    password = args.password or getpass.getpass("输入密码: ")
    if not password:
        print("密码不能为空", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        dup = (
            db.query(User)
            .filter(or_(User.username == args.username, User.phone == args.phone))
            .first()
        )
        if dup:
            if dup.username == args.username:
                print(f"用户名已存在: {args.username}", file=sys.stderr)
            else:
                print(f"手机号已被占用: {args.phone}", file=sys.stderr)
            sys.exit(1)
        user = User(
            username=args.username,
            phone=args.phone,
            password_hash=hash_password(password),
            role=UserRole.admin,
        )
        db.add(user)
        db.commit()
        print(f"已创建管理员: id={user.id} username={user.username} role=admin")
    finally:
        db.close()


if __name__ == "__main__":
    main()
