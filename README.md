# xlink AI 系统

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.4+-brightgreen.svg)](https://vuejs.org/)

**xlink** 是一个多模块 AI 业务平台 Monorepo，通过统一的 Vue 3 门户整合两大业务系统：

| 模块 | 目录 | 说明 |
|------|------|------|
| **达人信息管理** | `Information_Aggregation/` | 多平台达人数据采集、标签分类、智能匹配、MCN 管理 |
| **会议 AI** | `meeting_ai/` | 实时语音转写、批量音频处理、AI 会议纪要、协作会议 |

用户在门户登录一次，即可访问全部模块；两个后端独立部署，通过 **共享 JWT** 与 **Vite 反向代理** 打通。

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
┌─────────────────────────────────────────────────────────────────┐
│                    xlink 统一门户 (Vue 3)                        │
│                    http://localhost:5173                         │
│  ┌──────────────────────┐    ┌──────────────────────────────┐ │
│  │  达人信息管理         │    │  会议 AI                      │ │
│  │  /influencer/*       │    │  /meeting/*                  │ │
│  └──────────┬───────────┘    └──────────────┬───────────────┘ │
└─────────────┼───────────────────────────────┼───────────────────┘
              │ Vite Proxy                    │ Vite Proxy
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────────┐
│  达人后端 (FastAPI)      │     │  会议 AI 后端 (FastAPI)      │
│  :8000                  │     │  :8001                      │
│  /api/v1/*              │     │  /api/auth, /api/meetings,  │
│                         │     │  /api/ws, /meeting-app      │
└──────────┬──────────────┘     └──────────────┬──────────────┘
           │                                    │
           ▼                                    ▼
┌─────────────────────┐              ┌─────────────────────┐
│  MySQL (influencer_db)│            │  MySQL (meeting_ai)  │
│  Redis               │              │  阿里云通义听悟       │
└─────────────────────┘              │  智谱 GLM / FunASR   │
                                     └─────────────────────┘
```

**设计要点：**

- **门户壳**：`Information_Aggregation/frontend` 承载全部前端，模块注册见 `src/shell/moduleRegistry.ts`
- **双后端**：达人 API 与会议 API 各自独立，无共享代码库，数据库分离
- **认证桥接**：门户签发的 JWT（`iss: xling`）由 `meeting_ai/api/portal_auth.py` 解析，自动同步用户与权限
- **会议 UI 嵌入**：单人/协作录制通过 iframe 加载 `meeting_ai/static/transcribe.html`，路径代理为 `/meeting-app/`

---

## 功能概览

### 达人信息管理

- 多平台自动化采集（抖音星图、小红书蒲公英，基于 Playwright）
- 多层级标签体系与自动打标
- 多维度智能匹配引擎（粉丝量、互动率、标签、性价比等）
- MCN 机构与旗下达人关联管理
- 采集数据审核入库工作流
- 三级 RBAC 权限（超级管理员 / 管理员 / 用户）

### 会议 AI

- 实时语音转写（阿里云通义听悟 WebSocket）
- 批量音频上传转写（FunASR Paraformer）
- AI 自动生成 Markdown 会议纪要 + 结构化图文速览
- 协作会议：创建房间、邀请成员、多人同步录制与合并转写
- 会议历史管理、日期筛选、DOCX / 可视化导出
- 三级权限与跨模块权限申请审批

---

## 项目结构

```
xling_ai_system/
├── README.md                          # 本文件（Monorepo 总览）
├── .gitignore
│
├── Information_Aggregation/           # 达人系统 + 统一门户前端
│   ├── backend/                       # FastAPI 后端（:8000）
│   │   ├── app/
│   │   │   ├── api/v1/                # REST API 路由
│   │   │   ├── collectors/            # Playwright 采集器
│   │   │   ├── services/              # 业务逻辑层
│   │   │   ├── models/                # SQLAlchemy 模型
│   │   │   └── main.py                # 应用入口
│   │   ├── alembic/                   # 数据库迁移
│   │   └── .env.example
│   ├── frontend/                      # Vue 3 门户（:5173）
│   │   ├── src/
│   │   │   ├── modules/
│   │   │   │   ├── influencer/        # 达人模块路由
│   │   │   │   └── meeting/           # 会议模块路由
│   │   │   ├── shell/moduleRegistry.ts
│   │   │   └── views/
│   │   └── vite.config.ts             # 双后端代理配置
│   ├── scripts/                       # 启动脚本、数据库初始化
│   ├── docker-compose.yml             # 达人系统容器编排（不含 meeting_ai）
│   └── README.md                      # 达人系统详细文档
│
└── meeting_ai/                        # 会议 AI 独立后端
    ├── api/
    │   ├── main.py                    # 应用入口
    │   ├── portal_auth.py             # 门户 JWT 用户解析
    │   └── routes/                    # auth / meeting / websocket / collaborative ...
    ├── asr/                           # 语音识别（听悟 + FunASR）
    ├── llm/                           # 智谱 GLM 总结生成
    ├── services/                      # 协作会议、房间运行时
    ├── static/transcribe.html         # 会议录制 Web UI（iframe 嵌入）
    ├── db/                            # 数据库模型与迁移
    └── README.md                      # 会议 AI 详细文档
```

---

## 环境要求

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+（会议 AI 建议 3.11+） | 两个后端 |
| Node.js | 18+ | 门户前端 |
| MySQL | 8.0+ | 两个独立数据库 |
| Redis | 7+ | 达人采集任务队列 |
| Playwright Chromium | — | 达人平台采集 |
| FFmpeg | — | 会议 AI 音频处理 |

**外部 API（会议 AI 必填）：**

- 智谱 AI（GLM）— 会议纪要生成
- 阿里云通义听悟 — 实时语音转写

---

## 快速开始

以下步骤在本地启动完整的 xlink 门户（达人 + 会议双模块）。

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

会议 AI 启动时会自动建表；也可参考 `meeting_ai/db/create_table.sql`。

### 3. 配置环境变量

```bash
# 达人后端
cp Information_Aggregation/backend/.env.example Information_Aggregation/backend/.env

# 门户前端
cp Information_Aggregation/frontend/.env.example Information_Aggregation/frontend/.env

# 会议 AI
cp meeting_ai/.env.example meeting_ai/.env
```

**关键：两个后端的 JWT 密钥必须一致**

```env
# Information_Aggregation/backend/.env
SECRET_KEY=dev-local-secret-key-at-least-32-characters-long

# meeting_ai/.env
JWT_SECRET=dev-local-secret-key-at-least-32-characters-long
```

会议 AI 还需填写 `GLM_API_KEY`、阿里云听悟相关密钥及 MySQL 连接信息。

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
python test_system.py   # 可选：验证各模块
```

### 5. 启动三个服务

在三个终端分别运行：

```bash
# 终端 1 — 达人后端 (:8000)
cd Information_Aggregation/backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 终端 2 — 会议 AI 后端 (:8001)
cd meeting_ai
uvicorn api.main:app --reload --host 0.0.0.0 --port 8001

# 终端 3 — 门户前端 (:5173)
cd Information_Aggregation/frontend
npm run dev
```

**Windows 快捷方式**（仅启动达人前后端）：

```powershell
Information_Aggregation\scripts\start_dev.bat
```

> 使用 `start_dev.bat` 后仍需手动启动 meeting_ai（:8001），否则会议模块不可用。

### 6. 访问系统

| 地址 | 说明 |
|------|------|
| http://localhost:5173 | xlink 统一门户 |
| http://localhost:8000/docs | 达人 API 文档 |
| http://localhost:8001/docs | 会议 AI API 文档 |

**默认超级管理员**（达人系统首次启动自动创建）：

- 用户名：`qiufengai`
- 密码：`qfai12@@`

---

## 端口与代理

### 开发环境端口

| 服务 | 端口 | 说明 |
|------|------|------|
| 门户前端 | 5173 | Vue 3 SPA |
| 达人后端 | 8000 | `/api/v1/*` |
| 会议 AI 后端 | **8001** | 门户集成模式（避免与 8000 冲突） |
| MySQL | 3306 | 两个库可共用同一实例 |
| Redis | 6379 | 达人采集队列 |

### Vite 代理规则

配置位于 `Information_Aggregation/frontend/vite.config.ts`：

| 前端路径 | 代理目标 | 用途 |
|----------|----------|------|
| `/api/v1/*` | `:8000` | 达人 API |
| `/api/auth`, `/api/meetings`, `/api/meeting`, `/api/ws`, `/api/admin`, `/api/export`, `/api/settings` | `:8001` | 会议 AI API |
| `/meeting-app/*` | `:8001` | 会议录制 iframe |
| `/static/*` | `:8001` | 会议静态资源 |

---

## 统一认证

门户与会议 AI 通过 JWT 实现单点登录，无需二次认证。

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

### 用户同步机制

用户首次携带门户 JWT 访问会议 API 时，`portal_auth.py` 会在 `meeting_ai` 数据库中自动创建对应用户记录，并同步权限字段。两个系统各自维护用户表，无数据库级外键关联。

### 权限管理入口

- 门户「平台用户管理」：直接分配会议相关权限
- 门户「平台权限管理」：统一审批达人库 + 会议权限申请
- 会议 AI 独立模式：仍保留 `/api/auth/*` 本地注册登录（`meeting_ai` 单独部署时使用）

---

## 配置说明

### 达人后端关键配置

文件：`Information_Aggregation/backend/.env`

| 变量 | 说明 |
|------|------|
| `SECRET_KEY` | JWT 签名密钥（须与 meeting_ai 一致） |
| `DATABASE_URL` / `DB_*` | MySQL 连接 |
| `REDIS_URL` | Redis 连接 |
| `COLLECTOR_MODE` | 采集模式：`mock` / `api` / `browser` |
| `XINGTU_STORAGE_STATE` | 星图 Playwright 登录态 |
| `PUGONGYING_STORAGE_STATE` | 蒲公英 Playwright 登录态 |

### 会议 AI 关键配置

文件：`meeting_ai/.env`

| 变量 | 说明 |
|------|------|
| `JWT_SECRET` | JWT 签名密钥（须与达人 SECRET_KEY 一致） |
| `GLM_API_KEY` | 智谱 AI API Key |
| `ALIBABA_CLOUD_ACCESS_KEY_ID/SECRET` | 阿里云密钥 |
| `TINGWU_APP_KEY` | 通义听悟 AppKey |
| `DB_*` | MySQL（`meeting_ai` 库） |
| `FFMPEG_PATH` | FFmpeg 可执行文件路径 |

### 门户前端关键配置

文件：`Information_Aggregation/frontend/.env`

| 变量 | 说明 |
|------|------|
| `VITE_INFLUENCER_API_TARGET` | 达人后端地址（默认 `http://127.0.0.1:8000`） |
| `VITE_MEETING_API_TARGET` | 会议后端地址（默认 `http://127.0.0.1:8001`） |
| `VITE_MEETING_APP_PATH` | iframe 路径（默认 `/meeting-app/`） |

---

## 部署方式

### 方式一：Docker Compose（达人系统）

`Information_Aggregation/docker-compose.yml` 包含 MySQL、Redis、达人后端、门户前端，**不包含 meeting_ai**。

```bash
cd Information_Aggregation
docker-compose up -d
```

生产环境需额外部署 meeting_ai，并在 Nginx / Vite 中配置相同的代理规则。

### 方式二：全栈本地开发

参见 [快速开始](#快速开始)，三个服务分别启动。

### 方式三：会议 AI 独立部署

meeting_ai 可脱离门户单独运行（`:8000`），自带 `transcribe.html` 前端。详见 [`meeting_ai/README.md`](meeting_ai/README.md) 部署章节。

### 生产环境建议

1. 修改 `SECRET_KEY` / `JWT_SECRET` 为强随机字符串（≥32 位）
2. 设置 `DEBUG=false`（达人后端）、`APP_ENV=production`（会议 AI）
3. 限制 `CORS_ORIGINS` 为实际域名
4. 使用 Nginx 反向代理，配置 WebSocket 升级（会议实时转写）
5. 启用 HTTPS

---

## 子项目文档

各模块的详细 API、数据库设计、故障排查请参阅：

| 文档 | 内容 |
|------|------|
| [`Information_Aggregation/README.md`](Information_Aggregation/README.md) | 达人采集、标签、匹配、权限、Docker 部署 |
| [`meeting_ai/README.md`](meeting_ai/README.md) | 实时转写、批量处理、协作会议、日志系统 |

---

## 常见问题

### 登录后会议模块报 401

两个后端的 JWT 密钥不一致。确认 `SECRET_KEY`（达人）与 `JWT_SECRET`（会议）完全相同，重启两个后端。

### 会议模块页面空白或 iframe 加载失败

1. 确认 meeting_ai 已在 **8001** 端口运行
2. 检查 `VITE_MEETING_API_TARGET=http://127.0.0.1:8001`
3. 浏览器控制台是否有 `/meeting-app/` 或 `/api/ws` 连接错误

### 达人采集任务一直 pending

1. 确认 Redis 服务正常
2. 检查 Playwright Chromium 是否安装：`playwright install chromium`
3. 重新保存平台登录态：
   ```bash
   python Information_Aggregation/scripts/save_xingtu_session.py
   python Information_Aggregation/scripts/save_pugongying_session.py
   ```

### 实时转写无输出

1. 检查阿里云听悟密钥与 `TINGWU_APP_KEY`
2. 运行 `python meeting_ai/scripts/test_tingwu_connect.py` 验证连通性
3. 确认浏览器已授予麦克风权限

### 数据库连接失败

```powershell
# 重新初始化达人库
cd Information_Aggregation/scripts
.\setup_local.ps1
```

---


