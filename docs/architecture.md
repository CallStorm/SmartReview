# SmartReview 系统架构（Mermaid 版）

> 可视化的 HTML/SVG 版本见 [`architecture-diagram.html`](architecture-diagram.html)（浏览器直接打开）。
> 以下为可直接嵌入文档 / README 的 Mermaid 源码。

## 1. 逻辑组件视图

```mermaid
flowchart LR
  U[浏览器<br/>管理员 / 审核员]

  subgraph FE [前端层]
    SPA[React 19 SPA<br/>Nginx :80 托管 + /api 反代]
  end

  subgraph BE [后端层]
    API[后端 API<br/>FastAPI :8000<br/>认证 · 主数据 · 审核任务<br/>系统设置 · 仪表盘快照]
    WK[审核 Worker<br/>worker.py 独立进程<br/>轮询队列 · 线程池并发执行审核流水线]
  end

  subgraph DS [数据层]
    MySQL[(MySQL 8.0 :3306<br/>业务数据 · Alembic 迁移)]
    MinIO[(MinIO :9000/:9001<br/>Word 模板 · 方案文档<br/>批注/报告 · 图片资产)]
  end

  subgraph EXT [外部集成 · 可选]
    OO[OnlyOffice DS :9080<br/>在线预览/编辑 · JWT 回调]
    Dify[Dify 知识库<br/>检索增强审核]
    LLM[大模型<br/>火山引擎 / MiniMax / DeepSeek]
  end

  U -->|HTTPS :80| SPA
  SPA -->|REST /api · JWT| API
  API -->|SQLAlchemy| MySQL
  API -->|S3 读写| MinIO
  WK -->|领取任务 / 状态更新| MySQL
  WK -->|S3 读写| MinIO
  API <-->|JWT 配置 · 保存回调| OO
  SPA -.->|iframe 嵌入编辑器| OO
  API -.->|知识库检索| Dify
  WK -.->|知识库检索| Dify
  API -.->|连接测试| LLM
  WK -.->|审核调用| LLM
```

## 2. 审核流水线视图（Worker 内部）

```mermaid
flowchart TD
  P[任务创建<br/>status=pending] --> S[① 结构审核<br/>精确/模糊 LLM 匹配<br/>不一致 → fail-fast 终止]
  S -->|通过| BUS{并行执行<br/>ThreadPoolExecutor}
  BUS --> B[② 编制依据审核<br/>对照 BasisItem · 章节级]
  BUS --> C[③ 上下文一致性<br/>跨章节语义/数据 · 章节级]
  BUS --> X[④ 内容审核<br/>对照章节审核提示词 · 章节级]
  BUS --> F[⑤ 通篇审核<br/>全文上限 8 万字 · 文档级]
  B --> R[⑥ 报告生成<br/>JSON 报告 · Word 批注注入]
  C --> R
  X --> R
  F --> R
  R --> O[输出交付<br/>DOCX/PDF 导出 · 批注版 Word]
  O --> T[任务收尾<br/>status = passed / failed]
```

任务状态机：`pending → processing → passed | failed`；僵尸 `processing`（>5 分钟）自动回收；步骤顺序可配置
（`start → structure → [compilation_basis / context_consistency / content / full_document] → end`）。

## 3. Docker 部署视图（机器视角）

```mermaid
flowchart TB
  subgraph internet1 [互联网 · 用户访问]
    U[用户浏览器<br/>HTTPS :80/:443]
  end

  subgraph lan [企业内网 · 10.0.0.0/24]
    subgraph web [web · Web 服务器 10.0.0.10]
      Nginx["nginx :80/:443<br/>React SPA + /api 反代"]
    end
    subgraph app [app · 应用服务器 10.0.0.11]
      API["backend FastAPI :8000"]
      WK["worker 进程（同机）<br/>轮询队列 · 并发审核"]
    end
    subgraph db [db · 数据库服务器 10.0.0.12]
      MySQL["mysql:8.0 :3306"]
    end
    subgraph storage [storage · 存储服务器 10.0.0.13]
      MinIO["minio :9000/:9001<br/>S3 + 控制台"]
    end
    subgraph office [office · 文档服务器 10.0.0.14]
      OO["onlyoffice :9080<br/>在线预览/编辑"]
    end
    subgraph dify [dify · 知识库服务器 10.0.0.15（可选）]
      D["Dify API /v1<br/>检索增强审核"]
    end
  end

  subgraph internet2 [互联网 · 云服务（可选）]
    LLM["大模型 API<br/>火山引擎 / MiniMax / DeepSeek"]
  end

  U -->|HTTPS :80/443| Nginx
  Nginx -->|/api 反代 :8000| API
  API -->|SQL 读写 :3306| MySQL
  WK -.->|领取任务/状态更新 :3306| MySQL
  API -->|S3 读写 :9000| MinIO
  WK -.->|S3 读写 :9000| MinIO
  API <-->|JWT 配置 · 保存回调 :8000| OO
  U -.->|iframe 编辑器 :9080| OO
  API -.->|检索 API| D
  API -.->|审核调用 :443| LLM
  WK -.->|审核调用 :443| LLM
```

对外暴露：Web `:80/:443` · OnlyOffice `:9080` · MinIO 控制台 `:9001` · 其余服务仅内网互访。
启动：`docker compose --env-file .env.docker -f "docker-compose .yml" up -d --build`。

## 4. 后端模块清单（backend/app）

| 分层 | 模块 | 说明 |
| --- | --- | --- |
| 入口 | `main.py` | FastAPI 应用、CORS、启动管理员引导与仪表盘快照调度器 |
| 入口 | `worker.py` / `services/review_task_worker.py` | 独立 Worker：轮询 pending 队列（SKIP LOCKED 领取）、线程池并发执行 |
| API 路由 | `api/` | auth · users · scheme_types · basis · templates · review_tasks · settings_kb（Dify）· settings_model · settings_review · settings_upload · settings_onlyoffice · settings_dashboard · admin_dashboard · onlyoffice_callback |
| 核心 | `core/security.py` `config.py` `database.py` | JWT 与密码哈希、配置、SQLAlchemy 会话 |
| 模型 | `models/` | user · scheme_type · basis_item · scheme_template · scheme_review_task · 各运行时/系统设置表 · dashboard 快照 |
| 审核 | `services/review_pipeline.py` | 审核流水线：结构匹配 → 编制依据 / 上下文一致性 / 内容 / 通篇 → 报告生成 |
| 审核 | `services/review_report_*.py` | 报告内容组装、DOCX / PDF 导出 |
| 文档 | `services/word_parser.py` `doc_tree_utils.py` `tree_align.py` `structure_llm_matcher.py` `title_normalize.py` | DOCX 解析为标题树、模板-用户树对齐（精确/模糊）、LLM 结构匹配、标题规范化 |
| 文档 | `services/docx_comments.py` `docx_image_assets.py` | Word 批注注入、文档图片提取存储 |
| 存储 | `services/minio_storage.py` | MinIO S3 读写 |
| LLM | `services/llm/` | client · registry · resolve · chat；适配器：anthropic（MiniMax）、openai_compatible（火山引擎 / DeepSeek） |
| 集成 | `services/dify_client.py` `dify_settings.py` | Dify 知识库检索 |
| 集成 | `services/onlyoffice.py` `onlyoffice_settings.py` | OnlyOffice 编辑器配置（JWT）与回调 |
| 仪表盘 | `services/dashboard_*.py` | 统计、快照、定时调度 |

## 5. 前端页面路由（frontend/src）

| 路由 | 页面 | 权限 |
| --- | --- | --- |
| `/login` | 登录 | 公开 |
| `/dashboard` | 仪表盘（数据分析） | 管理员 |
| `/schemes` | 方案类型 | 管理员 |
| `/templates` | 模板管理（Word 模板 + 规则设置 + 工作流开关） | 管理员 |
| `/basis` | 编制依据 | 管理员 |
| `/review` | 方案审核 | 登录用户 |
| `/review/:taskId/manual` | 人工审阅（Web 结果 + OnlyOffice 预览） | 登录用户 |
| `/settings` | 系统设置（知识库 / 模型 / 审核策略 / OnlyOffice / 上传） | 管理员 |
| `/users` | 用户管理 | 管理员 |
| `/help` `/admin-manual` | 帮助与使用手册 | 登录 / 管理员 |
