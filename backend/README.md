# SmartReview API

Python 3.11+、FastAPI、MySQL、MinIO。

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

复制仓库根目录的 `.env.example` 为 `backend/.env` 并填写连接信息（推荐仅用 `backend/.env`；若使用 Docker Compose，请用根目录 `.env.docker`，勿与本地共用一个根目录 `.env`）。

## Migrations

```bash
cd backend
alembic upgrade head
```

## Run

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

可选：首次启动前在 `backend/.env` 中设置 `ADMIN_BOOTSTRAP=true` 及 `ADMIN_USERNAME`、`ADMIN_PASSWORD`、`ADMIN_PHONE`，将自动创建一个管理员账号（若用户名尚不存在）。

### 命令行创建管理员

在 `backend` 目录执行（密码可省略，改为终端交互输入）：

```bash
python scripts/create_admin.py -u admin --phone 13800138000
```
