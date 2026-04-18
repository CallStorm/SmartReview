# SmartReview（施工方案审核系统）

## 简介

SmartReview 面向施工方案的全流程管理与智能审核：支持账号与角色、方案类型与编制依据维护、按方案类型绑定 Word 模版（对象存储中的文件与标题树 JSON）、方案审核任务与报表，以及管理仪表盘与系统设置（知识库、审核策略、大模型、OnlyOffice 等）。后端基于 FastAPI，与独立 Worker 进程协同处理待办审核队列；可选对接自建 Dify 与火山引擎、MiniMax 等 LLM。

## 核心能力

- **身份与权限**：登录、JWT、用户与角色管理。
- **主数据**：方案类型、编制依据（管理员 CRUD）；方案类型绑定的 Word 模版与 MinIO 存储、标题树结构。
- **审核任务**：创建与跟踪方案审核任务；**API 与独立 Worker**（`worker.py`、队列轮询）并行读写 MySQL / MinIO，Docker Compose 中对应 `worker` 服务。
- **在线编辑**：**OnlyOffice** 文档服务集成（JWT、回调 URL；可在环境变量或系统「设置 → OnlyOffice」中配置，详见 [.env.example](.env.example)）。
- **可选集成**：Dify 知识库 API（`DIFY_*`）、大模型提供方（如火山引擎、MiniMax，环境变量与数据库设置并存，见 [.env.example](.env.example)）。
- **仪表盘**：统计与定时快照（API 启动时的 `dashboard_scheduler`）。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | React 19、Vite 8、TypeScript、Ant Design 6、TanStack Query、React Router |
| 后端 | Python 3.11+、FastAPI、SQLAlchemy、Alembic、MySQL、MinIO、JWT |
| 运行与编排 | Docker Compose：MySQL、MinIO、OnlyOffice Document Server、`smartreview-backend`、`smartreview-frontend`、Worker |

更细的本地安装、迁移与启动命令见 [backend/README.md](backend/README.md)。

## 架构

### 逻辑组件

```mermaid
flowchart LR
  Browser[Browser]
  Frontend[Frontend_Nginx]
  Backend[Backend_API]
  Worker[Worker]
  MySQL[(MySQL)]
  MinIO[(MinIO)]
  OnlyOffice[OnlyOffice]
  Dify[Dify_optional]
  LLM[LLM_optional]

  Browser --> Frontend
  Frontend --> Backend
  Backend --> MySQL
  Backend --> MinIO
  Worker --> MySQL
  Worker --> MinIO
  Backend <--> OnlyOffice
  Backend -.-> Dify
  Backend -.-> LLM
```

### Docker 部署视图（端口与依赖）

宿主机需配置 `HOST_IP`（浏览器可访问的本机地址，勿填 `127.0.0.1`，以便容器经宿主机访问 MinIO 等；见仓库根目录 Compose 文件头注释）。常见端口：前端 **80**，OnlyOffice **9080**，MinIO **9000**（S3 API）与 **9001**（控制台），MySQL **3306**；后端 API 在 Compose 网络内由前端反代访问，OnlyOffice 回调指向后端服务。

```mermaid
flowchart TB
  subgraph host [Docker_host]
    U[Browser]
    Fe[frontend_port_80]
    Be[backend_internal]
    Wo[worker]
    Db[(mysql_3306)]
    Obj[(minio_9000_9001)]
    Oo[onlyoffice_9080]
  end

  U --> Fe
  Fe --> Be
  Be --> Db
  Be --> Obj
  Be <--> Oo
  Wo --> Db
  Wo --> Obj
```

## 仓库结构

- `backend/` — FastAPI 应用、Alembic 迁移、`worker.py` 审核任务 Worker；说明见 [backend/README.md](backend/README.md)。
- `frontend/` — 管理端 SPA（Vite）。
- 根目录 **Docker Compose** 文件名为 `docker-compose .yml`（**文件名中含空格**），与 [.env.docker.example](.env.docker.example) 配套使用。

当前默认品牌图与浏览器 Tab 图标：`frontend/public/building.png`。

## 配置

将 [.env.example](.env.example) 复制为 `backend/.env`，按环境填写 MySQL、MinIO、`JWT_SECRET` 等。**勿将真实密码提交到 Git。** 本地开发请只用 `backend/.env`，不要用仓库根目录的 `.env`，以免与 Docker 环境变量混用。

**Docker Compose** 与本地分开：将 [.env.docker.example](.env.docker.example) 复制为仓库根目录 `.env.docker`。启动时需同时指定环境文件与 Compose 文件：使用 `docker compose`、参数 `--env-file .env.docker`、`-f` 指向 **`docker-compose .yml`**（含空格的文件名在 shell 中需加引号），再按需附加 `up -d --build` 等子命令。Compose 文件内注释说明了 `HOST_IP`、OnlyOffice JWT、各服务依赖关系。

前端开发默认通过 Vite 代理访问 API：请求发往 `/api`，由 `frontend/vite.config.ts` 转发到 `http://127.0.0.1:8000`。若需直连，可设置环境变量 `VITE_API_BASE_URL`（例如 `http://127.0.0.1:8000`）。

## 快速开始

1. 在 MySQL 中创建与 `backend/.env` 一致的数据库，在 `backend/` 执行数据库迁移（`alembic upgrade head`），具体命令见 [backend/README.md](backend/README.md)。
2. 启动 MinIO，并创建与配置一致的 bucket（或留空由上传接口自动创建）。
3. 在 `backend/` 用 `uvicorn` 启动 API；在 `frontend/` 执行 `npm install` 与 `npm run dev`。管理员可通过 `ADMIN_BOOTSTRAP` 首次创建，或使用 `backend/scripts/create_admin.py`，详见 [backend/README.md](backend/README.md)。
4. 浏览器访问开发服务器地址（默认 `http://localhost:5173`）。

## Dify 部署手册（Docker Compose）

若需自建并接入 Dify，请以官方文档为准：

- [Dify Docker Compose 快速开始（中文）](https://docs.dify.ai/zh/self-host/quick-start/docker-compose)

建议顺序：安装 Docker、Docker Compose、Git → 按文档克隆 Dify 部署仓库并进入对应目录 → 将官方示例环境文件复制为 `.env` 并修改 → 使用官方推荐的 `docker compose up -d` 一类命令启动 → 浏览器打开 Dify Web 完成初始化。

本仓库**不包含** Dify 的 Compose 编排文件；接入时在 SmartReview 的「设置」或环境变量中填写 Dify 基址与 API Key（见 [.env.example](.env.example) 中 `DIFY_*`）。

## 需求说明

功能与模块划分见上文；数据库与对象存储连接信息仅通过环境变量与系统设置配置，本文档不列举口令。
