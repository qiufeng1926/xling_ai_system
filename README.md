# xlink AI 系统

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.4+-brightgreen.svg)](https://vuejs.org/)

**xlink** 是一个多模块 AI 业务平台 Monorepo，通过统一的 Vue 3 门户整合多项业务能力：

| 模块 | 目录 / 入口 | 说明 |
|------|-------------|------|
| **达人信息管理** | `Information_Aggregation/` | 多平台达人采集、标签、智能匹配、MCN、审核入库 |
| **会议 AI** | `meeting_ai/` | 实时/批量转写、AI 纪要、协作会议、导出与通知 |
| **飞书** | `flybook/` | OAuth 绑定、云文档、文档库镜像、妙纪 AI |
| **企微** | 门户 `/qywechat/*` + 达人后端 API | 企微邮箱、审批与回调（管理员） |
| **平台管理** | 门户侧栏 | 用户/权限、离职交接、跨模块审批 |

用户登录一次即可访问全部模块；后端按服务独立部署，通过 **共享 JWT**、**内部密钥** 与 **反向代理** 打通。

---

## 目录

- [系统架构](#系统架构)
- [功能概览](#功能概览)
- [项目结构](#项目结构)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [端口与代理](#端口与代理)
- [统一认证](#统一认证)
- [配置说明](#配置说明)
- [部署方式](#部署方式)
- [子项目文档](#子项目文档)
- [常见问题](#常见问题)

---

## 系统架构

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         xlink 统一门户 (Vue 3)                            │
│                    开发 :5173  /  Docker :80                              │
│  达人 /influencer/* · 会议 /meeting/* · 飞书 /flybook/* · 企微 /qywechat/*  │
└───────┬───────────────────┬────────────────────┬─────────────────────────┘
        │ Vite / Nginx      │                    │
        ▼                   ▼                    ▼
┌───────────────┐   ┌───────────────┐   ┌────────────────┐
│ 达人后端       │   │ 会议 AI       │   │ 飞书后端        │
│ :8000         │   │ :8001         │   │ :8002          │
│ /api/v1/*     │◄─►│ /api/*        │   │ /api/flybook/* │
│ 通知 SSE      │   │ WS / 通知 SSE │   │ WS 妙纪        │
│ 企微 / 离职   │   │ 协作 / 导出   │   │ 云文档 / 镜像  │
└───────┬───────┘   └───────┬───────┘   └───────┬────────┘
        │                   │                    │
        ▼                   ▼                    ▼
   MySQL influencer_db   MySQL meeting_ai    飞书开放平台
   Redis（采集队列）      听悟 / FunASR / LLM   （token 存门户用户）
```

**设计要点：**

- **门户壳**：`Information_Aggregation/frontend` 承载全部前端；业务模块见 `src/modules/*`，菜单含企微与平台管理
- **多后端**：达人 / 会议 / 飞书进程与代码库独立，数据库分离；跨服务调用靠 JWT + `PORTAL_INTERNAL_KEY`
- **认证桥接**：门户签发 JWT（`iss: xling`），`meeting_ai` / `flybook` 的 `portal_auth` 解析并同步用户权限
- **实时通道**：会议实时转写 WebSocket、妙纪 WebSocket；达人与会议各自提供通知 SSE
- **会议 UI**：单人/协作录制通过 iframe 加载 `meeting_ai/static/transcribe.html`（路径 `/meeting-app/`）

---

## 功能概览

### 达人信息管理

- 多平台自动化采集（抖音星图、小红书蒲公英，Playwright）
- 多层级标签与自动打标、智能匹配、MCN 管理
- 采集审核入库、三级 RBAC
- 离职申请 / 交接 / 归档，联动会议数据交接
- 站内通知（SSE）、飞书文档访问与日终导出

### 会议 AI

- 实时转写（阿里云通义听悟 WebSocket）+ 批量上传（FunASR）
- AI 纪要：Markdown + 图文速览；LLM 可切换 **智谱 GLM / DeepSeek**（`LLM_PROVIDER`）
- 协作会议：房间、邀请、多人同步录制与合并转写
- 会议历史、浏览/下载权限申请、DOCX / 可视化导出
- 通知 SSE；离职场景内部交接接口

### 飞书

- OAuth **绑定**（须先登录 xlink，非独立登录页）
- 消息页嵌入、云文档创建/导入、文档库与镜像
- **妙纪 AI**：妙记检索、产物获取、实时转写 WebSocket

### 企微（管理员）

- 企微邮箱、审批流与事件回调（达人后端 `/api/v1/qywechat/*`）

---

## 项目结构

```
xling_ai_system/
├── README.md                          # 本文件（Monorepo 总览）
├── docker-compose.yml                 # 全栈编排（推荐）
├── docker/                            # 生产部署脚本与清单
│   ├── DEPLOY.md                      # 生产环境检查清单
│   ├── .env.example
│   ├── mysql/                         # meeting_ai 建库与授权 SQL
│   └── scripts/                       # Win / Linux 构建启动脚本
│
├── Information_Aggregation/           # 达人后端 + 统一门户前端
│   ├── backend/                       # FastAPI（:8000）
│   │   └── app/api/v1/                # 达人 / 通知 / 离职 / 企微 / 飞书文档 …
│   ├── frontend/                      # Vue 3 门户（:5173）
│   │   └── src/modules/               # influencer / meeting / flybook / qywechat
│   ├── docker-compose.yml             # 仅达人 + 门户（不含会议/飞书）
│   └── README.md
│
├── meeting_ai/                        # 会议 AI（:8001）
│   ├── api/                           # 路由、portal_auth、协作 WS
│   ├── asr/                           # 听悟实时 + FunASR 批量
│   ├── llm/                           # GLM / DeepSeek
│   ├── services/                      # 协作房间、通知中心
│   ├── static/transcribe.html
│   ├── db/
│   └── README.md
│
└── flybook/                           # 飞书后端（:8002）
    ├── api/routes/                    # auth / docs / minutes / callback
    ├── api/ws/                        # 妙纪实时转写
    ├── integrations/feishu/
    ├── services/
    └── README.md
```

---

## 环境要求

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+（会议 AI 建议 3.11+） | 三个后端 |
| Node.js | 18+ | 门户前端 |
| MySQL | 8.0+ | `influencer_db` + `meeting_ai` |
| Redis | 7+ | 达人采集任务队列 |
| Playwright Chromium | — | 达人平台采集 |
| FFmpeg | — | 会议 AI 音频处理 |

**外部 API：**

- 会议：阿里云通义听悟；智谱 GLM 和/或 DeepSeek（按 `LLM_PROVIDER`）
- 飞书：开放平台 App ID / Secret、OAuth 重定向 URL
- 企微：按业务在达人后端配置（可选）

---

## 快速开始

本地启动完整门户（达人 + 会议 + 飞书）。

### 1. 克隆仓库

```bash
git clone <repository-url>
cd xling_ai_system
```

### 2. 初始化数据库

**达人库（influencer_db）：**

```powershell
cd Information_Aggregation/scripts
.\setup_local.ps1
```

**会议库（meeting_ai）：**

```sql
CREATE DATABASE meeting_ai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

会议 AI 启动时会自动建表 / 迁移字段；也可参考 `meeting_ai/db/create_table.sql`。

### 3. 配置环境变量

```bash
cp Information_Aggregation/backend/.env.example Information_Aggregation/backend/.env
cp Information_Aggregation/frontend/.env.example Information_Aggregation/frontend/.env
cp meeting_ai/.env.example meeting_ai/.env
cp flybook/.env.example flybook/.env
```

**关键：三端 JWT / 内部密钥保持一致**

```env
# Information_Aggregation/backend/.env
SECRET_KEY=dev-local-secret-key-at-least-32-characters-long
PORTAL_INTERNAL_KEY=dev-flybook-internal-key-change-me
FLYBOOK_INTERNAL_KEY=dev-flybook-internal-key-change-me

# meeting_ai/.env
JWT_SECRET=dev-local-secret-key-at-least-32-characters-long
PORTAL_INTERNAL_KEY=dev-flybook-internal-key-change-me

# flybook/.env
JWT_SECRET=dev-local-secret-key-at-least-32-characters-long
FLYBOOK_INTERNAL_KEY=dev-flybook-internal-key-change-me
```

会议 AI 还需填写听悟密钥，以及 `GLM_API_KEY` 或 `DEEPSEEK_API_KEY`（取决于 `LLM_PROVIDER`）。飞书需填写 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 与 OAuth 回调地址。

### 4. 安装依赖

```bash
# 达人后端
cd Information_Aggregation/backend
pip install -r requirements.txt
playwright install chromium

# 门户前端
cd ../frontend
npm install

# 会议 AI
cd ../../meeting_ai
pip install -r requirements.txt
python test_system.py   # 可选

# 飞书
cd ../flybook
pip install -r requirements.txt
```

### 5. 启动服务

```bash
# 终端 1 — 达人后端 (:8000)
cd Information_Aggregation/backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 终端 2 — 会议 AI (:8001)
cd meeting_ai
uvicorn api.main:app --reload --host 0.0.0.0 --port 8001

# 终端 3 — 飞书 (:8002)
cd flybook
uvicorn api.main:app --reload --host 0.0.0.0 --port 8002

# 终端 4 — 门户前端 (:5173)
cd Information_Aggregation/frontend
npm run dev
```

**Windows 快捷方式**（仅达人前后端）：

```powershell
Information_Aggregation\scripts\start_dev.bat
```

> 使用 `start_dev.bat` 后仍需手动启动 meeting_ai（:8001）与 flybook（:8002）。

### 6. 访问系统

| 地址 | 说明 |
|------|------|
| http://localhost:5173 | xlink 统一门户 |
| http://localhost:8000/docs | 达人 API |
| http://localhost:8001/docs | 会议 AI API |
| http://localhost:8002/docs | 飞书 API |

**默认超级管理员**（达人系统首次启动自动创建，亦可由 `.env` 的 `ADMIN_*` 覆盖）：

- 用户名：`qiufengai`
- 密码：`qfai12@@`

---

## 端口与代理

### 开发环境端口

| 服务 | 端口 | 说明 |
|------|------|------|
| 门户前端 | 5173 | Vue 3 SPA |
| 达人后端 | 8000 | `/api/v1/*` |
| 会议 AI | **8001** | 门户集成模式 |
| 飞书 | **8002** | `/api/flybook/*` |
| MySQL | 3306 | 两库可同实例 |
| Redis | 6379 | 达人采集队列 |

### Vite 代理规则

配置位于 `Information_Aggregation/frontend/vite.config.ts`：

| 前端路径 | 代理目标 | 用途 |
|----------|----------|------|
| `/api/v1/*` | `:8000` | 达人 / 企微 / 通知 / 离职等 |
| `/api/flybook/*` | `:8002` | 飞书（含 WebSocket） |
| `/api/auth`, `/api/meetings`, `/api/meeting`, `/api/ws`, `/api/admin`, `/api/export`, `/api/settings`, `/api/notifications` | `:8001` | 会议 AI |
| `/meeting-app/*` | `:8001` | 会议录制 iframe |
| `/static/*` | `:8001` | 会议静态资源 |

---

## 统一认证

### 令牌格式（达人后端签发）

```json
{
  "iss": "xling",
  "sub": "username",
  "role": "super_admin | admin | user",
  "nickname": "显示名",
  "perms": {
    "view_library": true,
    "view_all_meetings": true,
    "download_meetings": false
  }
}
```

### 角色映射

| 门户角色 | 会议 AI 角色 |
|----------|-------------|
| `super_admin` | `root` |
| `admin` | `admin` |
| `user` | `user` |

### 用户同步与跨服务

- 携带门户 JWT 访问会议 API 时，`meeting_ai/api/portal_auth.py` 会同步用户与权限到本地库
- 飞书绑定 token 存在门户用户上；flybook 用 JWT 识别当前用户
- 离职交接等场景通过 `PORTAL_INTERNAL_KEY` 调用内部接口（会议 `internal_offboard`、飞书文档镜像等）

### 权限管理入口

- 门户「平台用户管理」：分配会议等权限
- 门户「平台权限管理」：达人库 + 会议等申请审批
- 门户「离职交接」：申请 / 交接任务 / 管理归档
- 会议 AI 独立部署时仍可用本地 `/api/auth/*` 注册登录

---

## 配置说明

### 达人后端

文件：`Information_Aggregation/backend/.env`

| 变量 | 说明 |
|------|------|
| `SECRET_KEY` | JWT 签名（须与 meeting_ai / flybook 一致） |
| `PORTAL_INTERNAL_KEY` / `FLYBOOK_INTERNAL_KEY` | 内部服务密钥 |
| `DATABASE_URL` / `DB_*` | MySQL |
| `REDIS_URL` | Redis |
| `COLLECTOR_MODE` | `mock` / `api` / `browser` |
| `MEETING_AI_API_URL` / `FLYBOOK_API_URL` | 跨服务地址（Docker 内为容器名） |

### 会议 AI

文件：`meeting_ai/.env`

| 变量 | 说明 |
|------|------|
| `JWT_SECRET` | 与达人 `SECRET_KEY` 一致 |
| `LLM_PROVIDER` | `glm` 或 `deepseek` |
| `GLM_API_KEY` / `DEEPSEEK_API_KEY` | 对应提供商密钥 |
| `ALIBABA_CLOUD_*` / `TINGWU_APP_KEY` | 通义听悟 |
| `PORTAL_API_URL` / `PORTAL_INTERNAL_KEY` | 门户联动 |
| `DB_*` | `meeting_ai` 库 |
| `FFMPEG_PATH` | FFmpeg 路径 |

### 飞书

文件：`flybook/.env`

| 变量 | 说明 |
|------|------|
| `JWT_SECRET` | 与达人一致 |
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | 开放平台应用 |
| `FEISHU_OAUTH_REDIRECT_URI` | 须与开放平台重定向 URL 完全一致 |
| `PORTAL_FRONTEND_URL` | 绑定完成后跳转地址 |
| `FLYBOOK_INTERNAL_KEY` | 与门户内部密钥一致 |

### 门户前端

文件：`Information_Aggregation/frontend/.env`

| 变量 | 说明 |
|------|------|
| `VITE_INFLUENCER_API_TARGET` | 默认 `http://127.0.0.1:8000` |
| `VITE_MEETING_API_TARGET` | 默认 `http://127.0.0.1:8001` |
| `VITE_FLYBOOK_API_TARGET` | 默认 `http://127.0.0.1:8002` |
| `VITE_MEETING_APP_PATH` | 默认 `/meeting-app/` |
| `VITE_FLYBOOK_URL` | 飞书消息页嵌入地址 |

---

## 部署方式

### 方式一：根目录 Docker Compose（推荐全栈）

根目录 `docker-compose.yml` 包含 MySQL、Redis、达人后端、会议 AI、飞书、门户前端。

```bash
cp docker/.env.example docker/.env
# 同时准备 Information_Aggregation/backend/.env、meeting_ai/.env、flybook/.env
docker compose --env-file docker/.env up -d --build
```

生产检查清单与 Windows/Linux 脚本见 [`docker/DEPLOY.md`](docker/DEPLOY.md)。

### 方式二：仅达人系统 Compose

`Information_Aggregation/docker-compose.yml` **不含** meeting_ai / flybook，适合单独跑达人模块。

### 方式三：本地多进程开发

见 [快速开始](#快速开始)。

### 方式四：会议 AI 独立部署

meeting_ai 可单独运行（文档默认示例端口 `:8000`），自带 `transcribe.html`。门户集成时请使用 **:8001**。详见 [`meeting_ai/README.md`](meeting_ai/README.md)。

### 生产建议

1. 使用强随机 `SECRET_KEY` / `JWT_SECRET` / `PORTAL_INTERNAL_KEY`（≥32 位）且三端一致
2. `DEBUG=false`、`APP_ENV=production`
3. 限制 `CORS_ORIGINS`；网关配置 HTTPS
4. Nginx 需开启 WebSocket 升级（会议实时转写、飞书妙纪）
5. 勿将 MySQL / Redis 端口暴露公网

---

## 子项目文档

| 文档 | 内容 |
|------|------|
| [`Information_Aggregation/README.md`](Information_Aggregation/README.md) | 达人采集、门户前端、权限、企微与离职 API |
| [`meeting_ai/README.md`](meeting_ai/README.md) | 转写、协作、LLM、导出、通知与部署 |
| [`meeting_ai/db/README.md`](meeting_ai/db/README.md) | 会议库表结构 |
| [`flybook/README.md`](flybook/README.md) | OAuth、云文档、妙纪 AI |
| [`docker/DEPLOY.md`](docker/DEPLOY.md) | 生产 Docker 部署清单 |

---

## 常见问题

### 登录后会议模块报 401

JWT 密钥不一致。确认达人 `SECRET_KEY` 与会议 / 飞书 `JWT_SECRET` 完全相同后重启服务。

### 会议 iframe 空白或 `/api/ws` 失败

1. meeting_ai 是否监听 **8001**
2. `VITE_MEETING_API_TARGET=http://127.0.0.1:8001`
3. 浏览器麦克风权限与控制台报错

### 飞书绑定失败

1. 开放平台重定向 URL 是否等于 `FEISHU_OAUTH_REDIRECT_URI`
2. `PORTAL_FRONTEND_URL` 是否为当前访问的门户地址
3. `FLYBOOK_INTERNAL_KEY` 是否与达人后端一致

### 达人采集一直 pending

1. Redis 是否正常
2. `playwright install chromium`
3. 重新保存登录态：`save_xingtu_session.py` / `save_pugongying_session.py`

### 实时转写无输出

1. 听悟 `TINGWU_APP_KEY` 与阿里云密钥
2. `python meeting_ai/scripts/test_tingwu_connect.py`（若脚本存在）
3. 麦克风权限

### Docker 中 meeting_ai 报 MySQL Access denied

```powershell
docker\scripts\win\fix-mysql-grants.cmd
```

---
