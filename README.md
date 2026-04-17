# SmartReview（施工方案审核系统）

React + Vite 前端，FastAPI + MySQL + MinIO 后端：登录与角色、方案类型、编制依据（管理员 CRUD）、方案类型绑定的 Word 模版（MinIO 存储 + 标题树 JSON）。

## 仓库结构

- `backend/` — API（见 [backend/README.md](backend/README.md)）
- `frontend/` — 管理端 SPA

当前默认品牌图与浏览器 Tab 图标使用：`frontend/public/building.png`。

## 配置

将 [.env.example](.env.example) 复制为 `backend/.env`，按环境填写 MySQL、MinIO、`JWT_SECRET` 等。**勿将真实密码提交到 Git。** 本地开发请只用 `backend/.env`，不要用仓库根目录的 `.env`，以免与下面 Docker 配置混用。

**Docker Compose** 与本地分开：将 [.env.docker.example](.env.docker.example) 复制为仓库根目录 `.env.docker`，然后执行 `docker compose --env-file .env.docker up -d --build`。

前端开发默认通过 Vite 代理访问 API：请求发往 `/api`，由 `frontend/vite.config.ts` 转发到 `http://127.0.0.1:8000`。若需直连，可设置 `VITE_API_BASE_URL`（例如 `http://127.0.0.1:8000`）。

## 快速开始

1. MySQL 中创建数据库（与 `backend/.env` 中库名一致），在 `backend/` 执行 `alembic upgrade head`。
2. 启动 MinIO，并创建与配置一致的 bucket（或留空由上传接口自动创建）。
3. `backend/`：`uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
4. `frontend/`：`npm install && npm run dev`
5. 浏览器访问 `http://localhost:5173`。可通过 `ADMIN_BOOTSTRAP` 首次创建管理员，或自行向 `users` 表写入账号（密码为 bcrypt 哈希）。

## Docker 镜像同步（内网仓库）

仓库根目录提供脚本 [`sync_docker_images.py`](sync_docker_images.py)，用于在两台机器之间通过私有仓库中转镜像：

- 源机器（推送）：将本地镜像重打 tag 为 `10.72.2.15/review/...` 并 `push`
- 目标机器（拉取）：从 `10.72.2.15/review/...` `pull` 后，再恢复原始镜像 tag

### 1) 源机器推送镜像

```bash
python sync_docker_images.py --mode push
```

脚本流程：
1. 校验本地镜像存在
2. 执行 `docker tag SOURCE_IMAGE[:TAG] 10.72.2.15/review/IMAGE[:TAG]`
3. 执行 `docker push 10.72.2.15/review/IMAGE[:TAG]`

### 2) 目标机器拉取并恢复原始 tag

```bash
python sync_docker_images.py --mode pull
```

脚本流程：
1. 执行 `docker pull 10.72.2.15/review/IMAGE[:TAG]`
2. 执行 `docker tag 10.72.2.15/review/IMAGE[:TAG] SOURCE_IMAGE[:TAG]`（恢复原始 tag）

默认会保留仓库 tag。若不保留：

```bash
python sync_docker_images.py --mode pull --no-keep-registry-tag
```

### 3) 默认镜像列表维护

脚本内置了默认同步列表（在 `DEFAULT_IMAGES` 中维护），包括：

- `smartreview-frontend:latest`
- `smartreview-backend:latest`
- `redis:6-alpine`
- `mysql:8.0`
- `nginx:latest`
- `langgenius/dify-api:1.13.3`
- `langgenius/dify-web:1.13.3`
- `langgenius/dify-sandbox:0.2.14`
- `onlyoffice/documentserver:latest`
- `langgenius/dify-plugin-daemon:0.5.3-local`
- `ubuntu/squid:latest`
- `redis:latest`
- `minio/minio:latest`
- `busybox:latest`

也可临时覆盖内置列表（逗号分隔）：

```bash
python sync_docker_images.py --mode push --images "redis:latest,mysql:8.0"
```

### 4) 常用参数

- `--mode`：`push` 或 `pull`（必填）
- `--registry`：仓库地址，默认 `10.72.2.15`
- `--namespace`：命名空间，默认 `review`
- `--images`：可选，临时覆盖默认镜像列表
- `--keep-registry-tag` / `--no-keep-registry-tag`：`pull` 后是否保留仓库 tag（默认保留）

### 5) 注意事项

- 执行前请确保 Docker 可用，并已完成登录（如需要）：`docker login 10.72.2.15`
- 任何镜像同步失败时，脚本会返回非 0 退出码，方便 CI/CD 或批处理检测失败
- 镜像名不带 tag 时默认按 `latest` 处理

## Dify 部署手册（Docker Compose）

如果你需要自建并接入 Dify，可按官方文档进行部署：

- 官方文档（中文）：[Dify Docker Compose 快速开始](https://docs.dify.ai/zh/self-host/quick-start/docker-compose)

建议流程：

1. 安装并确认可用：`Docker`、`Docker Compose`、`Git`。
2. 按官方文档拉取 Dify 自托管仓库并进入 Docker 部署目录。
3. 复制环境变量示例文件（如 `.env.example`）为 `.env` 并按需修改配置。
4. 执行官方推荐命令启动：`docker compose up -d`。
5. 启动后通过浏览器访问 Dify Web 控制台，完成初始化。

说明：本仓库不内置 Dify 服务编排文件，上述步骤以 Dify 官方文档为准。

## 需求说明

原始功能说明见上文各模块；存储与数据库仅通过环境变量配置，不再在文档中写明口令。
