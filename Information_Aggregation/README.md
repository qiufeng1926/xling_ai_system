# 达人信息聚合系统 & xlink 门户前端

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.4+-brightgreen.svg)](https://vuejs.org/)

本目录包含两大部分：

1. **达人信息管理后端**（`:8000`）— 多平台采集、标签、匹配、MCN、审核、企微、离职、通知等
2. **xlink 统一门户前端**（`:5173`）— Vue 3 SPA，同时承载达人 / 会议 AI / 飞书 / 企微 / 平台管理

完整 Monorepo 说明见仓库根目录 [`README.md`](../README.md)。

---

## 核心能力

### 达人业务

- 多平台采集（抖音星图、小红书蒲公英，Playwright）
- 多层级标签、智能匹配、MCN 机构管理
- 采集审核入库、JWT + 三级 RBAC

### 门户与平台能力

- 统一登录，JWT 被会议 AI / 飞书后端复用
- 站内通知 SSE（`/api/v1/notifications/stream`）
- 离职申请 / 交接 / 管理归档
- 企微邮箱与审批（管理员，`/qywechat/*`）
- 飞书文档访问记录与日终导出（内部 API）

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI、SQLAlchemy 2、Alembic、Pydantic Settings、JWT（python-jose）、bcrypt |
| 数据 | MySQL 8（`influencer_db`）、Redis 7 |
| 采集 | Playwright |
| 前端 | Vue 3.4、TypeScript、Element Plus、Pinia、Vue Router、Axios、Vite 5 |

```
┌──────────────┐     Vite Proxy      ┌─────────────────┐
│  门户 Frontend │ ─────────────────► │ 达人 Backend    │
│  :5173 / :80 │                     │ :8000 /api/v1   │
└──────┬───────┘                     └────────┬────────┘
       │ 另代理 :8001 / :8002                 │
       ▼                                      ▼
  meeting_ai / flybook                 MySQL + Redis + Playwright
```

---

## 项目结构

```
Information_Aggregation/
├── backend/
│   ├── app/
│   │   ├── api/v1/              # REST 路由（见下方 API 表）
│   │   ├── collectors/          # 星图 / 蒲公英采集器
│   │   ├── services/
│   │   ├── models/ / schemas/
│   │   └── main.py
│   ├── alembic/
│   ├── cookies/ / logs/
│   ├── .env.example
│   └── Dockerfile
│
├── frontend/                    # xlink 统一门户
│   ├── src/
│   │   ├── modules/             # influencer / meeting / flybook / qywechat
│   │   ├── shell/moduleRegistry.ts
│   │   ├── views/               # 各模块页面
│   │   ├── api/ / stores / layouts/
│   │   └── composables/         # 如 useUserNotifications（SSE）
│   ├── vite.config.ts           # 多后端代理
│   └── .env.example
│
├── scripts/                     # setup_local、start_dev、会话保存等
├── docker-compose.yml           # 仅达人 + 门户（不含会议/飞书）
└── README.md
```

---

## 快速开始

> 若同时需要会议 AI 与飞书，请按仓库根 README 启动三个后端；本目录 Compose **不包含**它们。全栈推荐根目录 `docker-compose.yml`。

### 前置要求

Python 3.10+、Node.js 18+、MySQL 8、Redis 7、Playwright Chromium。

### Docker（仅本目录）

```bash
cd Information_Aggregation
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
docker-compose up -d
```

- 前端：http://localhost:5173（或镜像映射端口）
- API：http://localhost:8000/docs

### 本地开发

```powershell
# 1. 初始化库
cd scripts
.\setup_local.ps1

# 2. 后端
cd ..\backend
pip install -r requirements.txt
playwright install chromium
copy .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. 前端
cd ..\frontend
npm install
copy .env.example .env
npm run dev
```

Windows 一键：`scripts\start_dev.bat`（仅达人前后端）。

**默认超管**：`qiufengai` / `qfai12@@`（可用 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 覆盖）。

---

## 配置说明

### 后端 `backend/.env`

```bash
DEBUG=true
SECRET_KEY=dev-local-secret-key-at-least-32-characters-long
PORTAL_INTERNAL_KEY=dev-flybook-internal-key-change-me
FLYBOOK_INTERNAL_KEY=dev-flybook-internal-key-change-me

DB_HOST=localhost
DB_PORT=3306
DB_USER=app_user
DB_PASSWORD=app123
DB_NAME=influencer_db
REDIS_URL=redis://localhost:6379/0

COLLECTOR_MODE=browser
PLAYWRIGHT_HEADLESS=false
CORS_ORIGINS=http://localhost:5173

# 跨服务（本地默认）
MEETING_AI_API_URL=http://127.0.0.1:8001
FLYBOOK_API_URL=http://127.0.0.1:8002
```

`SECRET_KEY` 必须与 `meeting_ai` / `flybook` 的 `JWT_SECRET` 一致。

### 前端 `frontend/.env`

```bash
VITE_INFLUENCER_API_TARGET=http://127.0.0.1:8000
VITE_MEETING_API_TARGET=http://127.0.0.1:8001
VITE_FLYBOOK_API_TARGET=http://127.0.0.1:8002
VITE_MEETING_APP_PATH=/meeting-app/
VITE_FLYBOOK_URL=https://your-tenant.feishu.cn/next/messenger
```

---

## 门户模块

| 路径前缀 | 模块 | 说明 |
|----------|------|------|
| `/influencer/*` | 达人 | 库、采集、匹配、标签、机构等 |
| `/meeting/*` | 会议 AI | 历史、权限相关页；录制走 iframe `/meeting-app/` |
| `/flybook/*` | 飞书 | 消息、云文档、文档库、妙纪 AI |
| `/qywechat/*` | 企微 | 邮箱、审批（管理员） |
| 侧栏「平台管理」 | 用户 / 权限 / 离职 | 跨模块治理 |

模块注册：`frontend/src/shell/moduleRegistry.ts`（企微路由在 `modules/qywechat`，菜单在 `MainLayout`）。

---

## 达人核心功能

### 自动采集

1. 保存登录态：`python scripts/save_xingtu_session.py` / `save_pugongying_session.py`
2. 创建任务 → Worker 异步执行 → 审核入库

### 智能标签 / 匹配 / MCN

- 层级标签与自动打标
- 粉丝量、互动率、性价比、标签相似度等匹配维度
- 机构与旗下达人关联

### 权限（RBAC）

| 角色 | 范围 |
|------|------|
| 超级管理员 | 全部，含用户与平台管理 |
| 管理员 | 达人业务 + 企微等管理项 |
| 用户 | 可见范围内达人、申请权限、提交采集等 |

会议相关权限字段会写入 JWT `perms`，供会议后端同步。

### 离职交接

- 用户申请离职 → 交接人处理 → 管理员归档
- 可联动会议 AI 内部交接接口（`PORTAL_INTERNAL_KEY`）

### 通知

- SSE：`GET /api/v1/notifications/stream`
- 前端 `useUserNotifications` 刷新角标与待办

---

## API 概览

启动后：http://localhost:8000/docs

| 模块 | 路径前缀 | 说明 |
|------|---------|------|
| 认证 | `/api/v1/auth` | 登录、刷新 Token |
| 通知 | `/api/v1/notifications` | SSE 与通知相关 |
| 达人 | `/api/v1/influencers` | 列表 / 详情 / 搜索 |
| 采集 | `/api/v1/collection` | 任务与审核 |
| 匹配 | `/api/v1/match` | 匹配任务与结果 |
| 标签 | `/api/v1/tags` | 标签 CRUD |
| 机构 | `/api/v1/agencies` | MCN |
| 用户 | `/api/v1/users` | 用户管理 |
| 离职 | `/api/v1/offboarding` | 申请 / 交接 / 管理 |
| 权限 | `/api/v1/permissions` | 申请与审批 |
| 企微 | `/api/v1/qywechat/*` | 邮箱、审批、回调（兼容 `/api/v1/wecom/*`） |
| 飞书文档 | `/api/v1/...`（feishu_documents） | 文档访问与内部接口 |
| 日终导出 | `/api/v1/...`（daily_export_internal） | 内部导出 |

---

## 常用命令

```bash
# 后端
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
alembic revision --autogenerate -m "description"
alembic upgrade head

# 前端
cd frontend
npm run dev
npm run build

# 本目录 Docker
docker-compose up -d
docker-compose logs -f backend
```

---

## 安全建议

1. 生产修改 `SECRET_KEY`、管理员密码、数据库密码
2. `DEBUG=false`，收紧 `CORS_ORIGINS`
3. HTTPS 终止于 Nginx / 网关
4. 内部密钥勿提交仓库

---

## 常见问题

**数据库连不上** — 检查 MySQL 服务后执行 `scripts\setup_local.ps1`。

**Playwright 缺失** — `cd backend && playwright install chromium`。

**采集 pending** — 确认 Redis、Worker、登录 Cookie 未过期。

**CORS** — 在 `.env` 的 `CORS_ORIGINS` 加入前端来源。

**会议 / 飞书在门户不可用** — 本目录仅启动了达人服务；请另启 `:8001` / `:8002`，或使用根目录全栈 Compose。

---

更完整的端口、代理与跨服务约定见 [仓库根 README](../README.md)。
