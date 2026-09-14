---
name: deploy
description: "升级/部署 SmartReview（方案审核）系统到内网演示环境（10.73.2.68, opsctl 资产 smartreview-target）或正式环境（10.73.2.21, opsctl 资产 smartreview-prod）。覆盖构建镜像、推 Harbor、远程拉取、备份、改版本、重启服务（需用户确认）、健康检查、失败自动回滚。适用于升级、部署、发布新版本、把正式环境也升级一下等场景。不适用于：其他项目的部署、纯本地 docker 操作、Harbor 配置变更。"
---

# deploy — 升级 SmartReview

将 SmartReview（方案审核）项目从当前版本升级到下一版本，部署到内网演示或正式环境。

## 拓扑（写死，不要让用户改）

| 环境 | IP | opsctl 资产 | Web 地址 |
|------|-----|-------------|----------|
| 演示 | 10.73.2.68 | smartreview-target | http://10.73.2.68/ |
| 正式 | 10.73.2.21 | smartreview-prod | http://10.73.2.21/ |

Web 登录：admin / admin1234

镜像 registry：10.72.2.15:80（Harbor，项目 review）。

两个环境的 compose 模板完全一致，所以同一套命令复用。

## 流程总览

```
Phase A：构建并推送（每次发版只做一次）
   ↓
Phase B：部署到演示环境（每个环境跑一次）
   ↓
（用户测试 OK → 用户说"把正式环境也升级一下"）
   ↓
Phase B 再跑一遍到 prod
```

## 触发判断

| 用户说法 | 动作 |
|---------|------|
| 升级 / 部署 / 发布新版本 | Phase A + Phase B on demo |
| 把正式环境也升级一下 / 升级正式环境 / prod 也升一下 | **跳过 Phase A**，只在 prod 跑 Phase B |
| 两个环境一起升级 | Phase A + Phase B on demo → 等用户确认 → Phase B on prod |

执行 Phase B on demo 后**默认停下来**等用户测试结果，绝不自动跳到 prod。

## 前置条件（少一个会卡住）

### 1. OpsKat 资产（已注册到 opsctl）

- `smartreview-target` → 10.73.2.68:22 root + 密码
- `smartreview-prod` → 10.73.2.21:22 root + 密码
- OpsKat 桌面 app 必须在运行

### 2. opsctl policy 预授权

policy 必须在交互式 PowerShell 里加（非 TTY 加不上）。让用户在普通 PowerShell 终端跑：

```powershell
$cmds = @("docker *","mysqldump *","cat *","tee *","cp *","mv *","sed -i *","mkdir *","grep *","head *","tail *","date *","find *","ls *","curl *","cd *","chmod *")
foreach ($c in $cmds) {
  opsctl policy allow smartreview-target -- $c
  opsctl policy allow smartreview-prod   -- $c
}
```

### 3. Clash Verge 代理

- 构建前后端镜像时：**开**（默认 127.0.0.1:7897）
- push 镜像时：**必须关**（开着 manifest push 报 authentication required，是已知坑）
- 远程 opsctl 操作：本地代理不影响
- 每步前用 `Test-NetConnection -Port 7897` 推断代理状态，需要时提醒用户开关

## Phase A：构建并推送

### Step 0：准备
- 在 `C:\Users\Administrator\Desktop\SmartReview`
- 提醒用户开 clash verge 代理

### Step 1：拉演示环境当前版本号

```bash
opsctl exec smartreview-target -- "docker ps --format 'table {{.Names}}\t{{.Image}}' | grep -E '(backend|frontend)'"
```

- 当前版本 = image tag 中数字（如 `1.0.13`）
- **新版本 = patch 号 +1**（如 `1.0.14`）

### Step 2：构建前后端（一次完成，不要分两次）

```bash
$env:http_proxy='http://127.0.0.1:7897'
$env:https_proxy='http://127.0.0.1:7897'

cd backend
docker build --no-cache -t 10.72.2.15:80/review/smartreview-backend:{NEW} .

cd ../frontend
docker build --no-cache -t 10.72.2.15:80/review/smartreview-frontend:{NEW} .
```

### Step 3：推送镜像
- 提醒用户关代理
- 代理关后：

```bash
docker push 10.72.2.15:80/review/smartreview-frontend:{NEW}
docker push 10.72.2.15:80/review/smartreview-backend:{NEW}
```

## Phase B：部署到指定环境

> 设 `$ENV` = `smartreview-target`（演示）或 `smartreview-prod`（正式）

### Step 4：远程 pull 新版本

远程 pull 用 `10.72.2.15` **不带** `:80`：

```bash
opsctl exec $ENV -- "docker pull 10.72.2.15/review/smartreview-frontend:{NEW}"
opsctl exec $ENV -- "docker pull 10.72.2.15/review/smartreview-backend:{NEW}"
```

### Step 5：备份 SQL

```bash
opsctl exec $ENV -- 'cd /opt/SmartReview-main && docker exec smartreview-main-mysql-1 mysqldump -uroot -p"changeme-strong-mysql" --single-transaction --routines --triggers review > "review_backup_$(date +%Y%m%d_%H%M%S).sql"'
```

### Step 6：备份 compose 文件

```bash
opsctl exec $ENV -- 'cd /opt/SmartReview-main && cp -a docker-compose.yml "docker-compose.yml.bak.$(date +%Y%m%d_%H%M%S)"'
```

### Step 7：改 compose 中 image 版本

执行前向用户展示当前 vs 改动后的版本号：

```bash
opsctl exec $ENV -- 'cd /opt/SmartReview-main && sed -i "s/:1\.0\.[0-9]\+/:{NEW}/g" docker-compose.yml && grep image docker-compose.yml'
```

确认输出三个 service 都是 `{NEW}` 后才能进入 Step 8。

### Step 8：重启服务（必须用户确认）

⚠️ **执行前向用户打印完整命令，等用户说 "go" 才执行**：

```bash
opsctl exec $ENV -- 'cd /opt/SmartReview-main && docker compose up -d --force-recreate backend frontend worker'
```

预期输出：`Recreated` / `Started` / `Healthy`。

### Step 9：健康检查

```bash
# 前端 HTTP 200
opsctl exec $ENV -- "curl -s -o /dev/null -w '%{http_code}' http://localhost/"

# 后端：从前端容器访问后端 openapi.json
opsctl exec $ENV -- "docker exec smartreview-main-frontend-1 wget -q -O - --timeout=5 http://smartreview-main-backend-1:8000/openapi.json"

# worker 日志
opsctl exec $ENV -- "docker logs smartreview-main-worker-1 --tail 5"
```

判定：
- 三个 ✅ → 提示 "Phase B on demo 完成，请测试后告诉我是否升级正式环境"
- 任一 ❌ → 跳到 Step 10 自动回滚

### Step 10：失败自动回滚

如果健康检查失败：
1. 告知用户服务异常，问是否回滚
2. 如果回滚（用户说 "go"）：

```bash
# 找最新的 compose 备份
BACKUP=$(opsctl exec $ENV -- 'ls -t /opt/SmartReview-main/docker-compose.yml.bak.* | head -1' | tr -d '\r')

# 恢复
opsctl exec $ENV -- "cd /opt/SmartReview-main && cp $BACKUP docker-compose.yml"

# 用旧镜像重建
opsctl exec $ENV -- "cd /opt/SmartReview-main && docker compose up -d --force-recreate backend frontend worker"
```

## 安全护栏（硬规则）

1. **Step 8 重启前必须用户确认**，完整命令先打印后执行
2. **Step 5/6 备份必须在 Step 7/8 之前**，防止不可逆
3. **Phase B on demo 后默认停下**，绝不自动跳 prod，等用户明确指令
4. **代理开/关在每步前显式检查**，错了立即停
5. **每个 opsctl exec 失败的命令立即停**，不自动继续

## 已知问题 / 踩过的坑

1. **proxy 必须关才能 push**。开着 layer 上传能通，manifest push 报 `authentication required` 误导成 registry 问题，实际是代理
2. **同一 shell 的 cd 不传给子 shell**。每次 exec_command 必须 cd 或设 workdir
3. **PowerShell `$()` 会吃 `$(date +...)`**。含 `$(...)` 的命令必须用单引号包整段
4. **backend 容器没有 curl / ss / netstat**（Python slim 镜像）。健康检查从 host 或 frontend 容器发
5. **opsctl policy 必须在交互式 shell 加**。非 TTY 加不上，policy allow 会卡住
6. **远程 pull 用 `10.72.2.15` 不带 `:80`**；本地 build / push 才带 `:80`
7. **Harbor `/api/repositories` 列表可能过滤掉一些 repo**，但 `/v2/.../manifests/` 能正常 GET，不影响 push
8. **重启后短时间 backend 端口 host 上 curl 返 000**（容器还没完全就绪），容器内互访正常即可判健康

## 不做什么

- 不修改 docker-compose.yml 的非 image 字段（端口、卷、环境变量等不在 skill 范围）
- 不动 MySQL / MinIO / OnlyOffice 的版本和配置
- 不创建 / 删除 opsctl 资产（前置条件里用户自己加）
- 不处理 Harbor 项目配置变更
- 不对其他项目生效
