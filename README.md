# SmartReview（施工方案审核系统）

React + Vite 前端，FastAPI + MySQL + MinIO 后端：登录与角色、方案类型、编制依据（管理员 CRUD）、方案类型绑定的 Word 模版（MinIO 存储 + 标题树 JSON）。

## 仓库结构

- `backend/` — API（见 [backend/README.md](backend/README.md)）
- `frontend/` — 管理端 SPA

侧栏与登录页使用的品牌图：`frontend/public/brand-logo.png`（陕建数科等素材）。若仓库中未包含该二进制文件，请将素材放到此路径，建议高度约 36–40px 的 PNG/SVG 导出。

登录页左侧整幅背景图：`frontend/public/home.png`（建议横向构图、`cover` 裁切，缺失时左侧为白底占位）。

## 配置

将 [.env.example](.env.example) 复制为 `backend/.env`，按环境填写 MySQL、MinIO、`JWT_SECRET` 等。**勿将真实密码提交到 Git。**

前端开发默认通过 Vite 代理访问 API：请求发往 `/api`，由 `frontend/vite.config.ts` 转发到 `http://127.0.0.1:8000`。若需直连，可设置 `VITE_API_BASE_URL`（例如 `http://127.0.0.1:8000`）。

## 快速开始

1. MySQL 中创建数据库（与 `.env` 中库名一致），在 `backend/` 执行 `alembic upgrade head`。
2. 启动 MinIO，并创建与配置一致的 bucket（或留空由上传接口自动创建）。
3. `backend/`：`uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
4. `frontend/`：`npm install && npm run dev`
5. 浏览器访问 `http://localhost:5173`。可通过 `ADMIN_BOOTSTRAP` 首次创建管理员，或自行向 `users` 表写入账号（密码为 bcrypt 哈希）。

## 需求说明

原始功能说明见上文各模块；存储与数据库仅通过环境变量配置，不再在文档中写明口令。
