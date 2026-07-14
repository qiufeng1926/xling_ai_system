# 会议 AI 系统

智能语音识别与会议纪要服务：实时转写（通义听悟）、批量 ASR（FunASR）、AI 纪要（GLM / DeepSeek）、协作会议、导出与通知。

可作为 **xlink 门户模块**（推荐端口 **:8001**）运行，也可独立访问自带的 `static/transcribe.html`。

Monorepo 总览见 [`../README.md`](../README.md)。

---

## 目录

- [功能特性](#功能特性)
- [两种运行模式](#两种运行模式)
- [快速开始](#快速开始)
- [使用说明](#使用说明)
- [用户认证与权限](#用户认证与权限)
- [API 概览](#api-概览)
- [项目结构](#项目结构)
- [技术栈](#技术栈)
- [配置说明](#配置说明)
- [数据库](#数据库)
- [日志](#日志)
- [故障排查](#故障排查)
- [部署](#部署)

---

## 功能特性

### 实时语音转写

- 浏览器麦克风推流，WebSocket 低延迟
- 默认走 **阿里云通义听悟**（说话人分离可配）
- 停止录音后自动生成 AI 纪要（Markdown + 图文速览）
- 支持自定义会议名称

### 批量音频处理

- 上传 WAV / MP3 / M4A 等（FFmpeg 转码）
- **FunASR** 识别 + LLM 纪要
- 结果落盘并入库

### 历史与协作

- 会议列表、详情、日期筛选
- **协作会议**：创建房间、邀请、多人录制、合并转写
- DOCX / 可视化导出（权限管控 + 下载审计）

### 认证、通知、离职

- JWT；门户集成时复用 xlink Token（`portal_auth`）
- 浏览 / 下载权限申请与审批
- 通知 SSE：`/api/notifications/stream`
- 内部离职交接：`/api/internal/...`（`PORTAL_INTERNAL_KEY`）

---

## 两种运行模式

| 模式 | 端口 | 说明 |
|------|------|------|
| **门户集成**（推荐） | **8001** | 与达人 `:8000`、飞书 `:8002` 并存；前端 iframe `/meeting-app/` |
| **独立部署** | 8000（示例） | 直接打开 `http://host:port/` 使用 `transcribe.html` |

门户模式下务必：

```env
JWT_SECRET=<与 Information_Aggregation SECRET_KEY 相同>
PORTAL_API_URL=http://127.0.0.1:8000
PORTAL_INTERNAL_KEY=<与门户一致>
```

---

## 快速开始

### 1. 依赖

Python 3.11+、MySQL 8、FFmpeg；以及听悟 + LLM API。

```bash
cd meeting_ai
pip install -r requirements.txt
cp .env.example .env
```

### 2. `.env` 必填项

```env
LLM_PROVIDER=glm
GLM_API_KEY=your_key
# 若 LLM_PROVIDER=deepseek，则配置 DEEPSEEK_API_KEY

ALIBABA_CLOUD_ACCESS_KEY_ID=...
ALIBABA_CLOUD_ACCESS_KEY_SECRET=...
TINGWU_APP_KEY=...

DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=...
DB_NAME=meeting_ai

JWT_SECRET=dev-local-secret-key-at-least-32-characters-long
```

可选：`FFMPEG_PATH`、ASR 模型名、图文速览分段参数等，见 `.env.example`。

### 3. 数据库

```sql
CREATE DATABASE meeting_ai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

启动时自动建表并迁移字段。

### 4. 自检与启动

```bash
python test_system.py

# 门户集成
uvicorn api.main:app --reload --host 0.0.0.0 --port 8001

# 或独立
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

- API 文档：`http://localhost:8001/docs`
- 独立 UI：`http://localhost:8000/`（独立端口时）

---

## 使用说明

### 独立 UI（transcribe.html）

三个标签：**实时转写** | **批量处理** | **历史会议**。

实时：可选填会议名 → 开始录音 → 停止后自动出纪要。  
批量：上传音频 → 处理 → 查看转写与纪要。  
历史：列表 / 详情，支持日期筛选。

文件默认目录：`output/transcripts/`、`output/summaries/`。

### 门户内使用

1. 登录 xlink → 打开「会议 AI」
2. 历史与权限相关页在 Vue 模块 `/meeting/*`
3. 录制 / 协作打开 iframe → `/meeting-app/`（代理到本服务根路径）

---

## 用户认证与权限

### 门户集成

携带门户 JWT（`iss: xling`）访问即可；`portal_auth` 同步用户与 `perms` 到本地 `users` 表。

角色映射：`super_admin`→`root`，`admin`→`admin`，`user`→`user`。

### 独立模式默认账号

设置 `SEED_DEFAULT_USERS=true`（或调用 seed 接口）后创建 root/admin；密码见 `SEED_*_PASSWORD` 或启动日志。

### 权限要点

| 能力 | 说明 |
|------|------|
| 普通用户 | 自建会议、看自己的数据 |
| 管理员 | 可见范围扩大；审批权限申请 |
| 超级管理员 | 全量能力；同级 root 互看受 `can_view_all_roots` 控制 |
| 下载 | `can_download`；可申请/审批下载权限 |

请求头：`Authorization: Bearer <token>`。

---

## API 概览

完整契约见 Swagger。路由前缀均为 `/api`：

| 模块 | 路径示例 | 说明 |
|------|----------|------|
| 认证 | `/auth/login`、`/auth/requests` | 本地登录与权限申请 |
| 会议 | `/meeting/upload`、`/meetings/list` | 批量与历史 |
| WebSocket | `/ws/transcribe` | 实时转写 |
| 协作 | `/meetings/rooms*` | 房间、邀请、开始/结束/恢复 |
| 导出 | `/export/*` | DOCX / 可视化 |
| 设置 | `/settings/*` | 如听悟说话人数等 |
| 管理 | `/admin/*` | 超管能力 |
| 浏览权限 | `/meeting` 相关 access 路由 | 单会浏览申请 |
| 通知 | `/notifications/stream` | SSE |
| 内部 | `/internal/...` offboard | 离职交接 |

### WebSocket 消息（实时转写）

客户端可先发 `{ "type": "init", "meeting_name": "..." }`，再推送音频块；服务端回 `result` / `generating_summary` / `session_end` / `error`。细节以当前 `websocket.py` 与前端实现为准。

---

## 项目结构

```
meeting_ai/
├── api/
│   ├── main.py
│   ├── portal_auth.py
│   ├── collaborative_ws.py
│   └── routes/
│       ├── auth.py / admin.py / meeting.py / websocket.py
│       ├── collaborative.py / meeting_access.py
│       ├── export.py / settings.py / notifications.py
│       └── internal_offboard.py
├── asr/
│   ├── engine.py              # FunASR 批量
│   └── tingwu_realtime.py     # 听悟实时
├── llm/
│   ├── glm_chat.py / deepseek_chat.py
│   └── prompt.py
├── services/
│   ├── collaborative_service.py / room_runtime.py
│   └── notification_hub.py / notification_emit.py
├── db/                        # 模型与迁移说明见 db/README.md
├── utils/                     # 日志、导出、执行器等
├── static/transcribe.html
├── config/config.py
├── .env.example
├── Dockerfile
└── test_system.py
```

---

## 技术栈

- FastAPI + Python 3.11+
- 实时 ASR：通义听悟 OpenAPI + WebSocket 推流
- 批量 ASR：FunASR（Paraformer 等，见 `.env` 模型名）
- LLM：智谱 GLM 或 DeepSeek（`LLM_PROVIDER`）
- MySQL + SQLAlchemy；JWT（PyJWT）
- 前端：原生 HTML/JS（`transcribe.html`）；门户侧为 Vue

---

## 配置说明

| 参数 | 说明 | 默认 / 备注 |
|------|------|-------------|
| `LLM_PROVIDER` | `glm` / `deepseek` | `glm` |
| `GLM_API_KEY` / `DEEPSEEK_API_KEY` | 对应提供商 | 按 provider 必填 |
| `GLM_MODEL` / `DEEPSEEK_MODEL` | 模型名 | 见 `.env.example` |
| `VISUAL_*` | 图文速览重试、分段、JSON 修复 | 有默认值 |
| `JWT_SECRET` | Token 密钥 | 门户集成须一致 |
| `PORTAL_API_URL` / `PORTAL_INTERNAL_KEY` | 门户联动 | 集成模式必填密钥 |
| `ALIBABA_CLOUD_*` / `TINGWU_*` | 听悟 | 实时必填 |
| `ASR_*` | 批量 ASR 模型与设备 | ModelScope 全名更稳 |
| `FFMPEG_PATH` | FFmpeg | Windows 常需配置 |
| `MAX_UPLOAD_BYTES` | 上传上限 | 默认约 500MB |
| `APP_ENV` | `development` / `production` | 生产强制校验 |
| `LOG_LEVEL` / `LOG_DIR` | 日志 | `INFO` / `logs` |

会议名会清洗非法字符、空格转下划线，建议 ≤50 字。

---

## 数据库

详见 [`db/README.md`](db/README.md)。核心表：`users`、`meetings`、协作房间与邀请、浏览/下载授权与审计。支持启动时自动补列。

---

## 日志

JSON Lines，目录 `logs/`，按大小轮转。关注字段：`request_id`、`duration_ms`、`level`。

```powershell
Select-String -Path "logs\meeting_ai_*.log" -Pattern '"level": "ERROR"'
```

---

## 故障排查

| 问题 | 处理 |
|------|------|
| WebSocket 连不上 | 服务是否在正确端口；代理是否升级 WS；防火墙 |
| 实时无文本 | 麦克风权限；听悟密钥；网络；服务端日志 |
| 无 AI 纪要 | `LLM_PROVIDER` 与对应 API Key；配额与网络 |
| 启动失败 | Python 版本、依赖、端口占用、`.env` 格式 |
| 门户 401 | `JWT_SECRET` 与门户不一致 |
| Docker Access denied | 执行 `docker/scripts/win/fix-mysql-grants.cmd` |

听悟连通性可运行仓库内相关 `scripts/test_tingwu_*.py`（若存在）。

---

## 部署

### 本地

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn api.main:app --host 0.0.0.0 --port 8001
```

### 全栈 Docker

使用仓库根目录 `docker-compose.yml` 与 [`docker/DEPLOY.md`](../docker/DEPLOY.md)。镜像暴露 **8001**。

### 独立容器

仓库内已有 `Dockerfile`，需自备 MySQL 并注入环境变量（听悟、LLM、JWT、DB）。

### Nginx 注意

- `Upgrade` / `Connection` 支持 WebSocket
- 长连接超时调大（实时会议可能很久）
- 门户路径：`/meeting-app/`、`/api/ws`、`/api/meetings` 等指到本服务

### 生产检查

- `APP_ENV=production`、强 `JWT_SECRET`
- 关闭无必要的 `SEED_DEFAULT_USERS`
- 限制 `CORS_ORIGINS`，外层 HTTPS

---

## FAQ 摘要

- **换 LLM**：改 `LLM_PROVIDER` 与对应 Key/模型。  
- **换批量 ASR 模型**：改 `ASR_MODEL_NAME`（建议 ModelScope 全路径）。  
- **备份**：`mysqldump` 库 + `upload/`、`output/`。  
- **自定义纪要提示词**：编辑 `llm/prompt.py`。  
- **并发**：每条 WS 连接独立；库内按用户隔离会议数据。
