# Flybook — 飞书独立后端

飞书集成服务，与达人系统、会议 AI **独立部署**（默认 **:8002**），通过 xlink 门户 JWT 识别已登录用户。Token 保存在门户用户侧，本服务无自建业务库。

前端页面在 `Information_Aggregation/frontend`：`/flybook/messenger`、`/docs`、`/doc-library`、`/minutes-ai`。

---

## 职责

| 能力 | 说明 |
|------|------|
| OAuth **绑定** | 非登录入口；须先登录 xlink，再绑定飞书账号 |
| 事件回调 | 开放平台事件订阅加解密 |
| 云文档 | 根目录、文件列表、创建、导入、组件鉴权、镜像 |
| 文档内部 API | 按内部密钥导出文本、全量镜像（供门户/日终导出） |
| **妙纪 AI** | 妙记搜索、详情与产物；实时转写 WebSocket |

---

## 快速启动

```bash
cd flybook
cp .env.example .env
pip install -r requirements.txt
uvicorn api.main:app --reload --host 0.0.0.0 --port 8002
```

**必须一致：**

- `JWT_SECRET` ≡ 达人后端 `SECRET_KEY`
- `FLYBOOK_INTERNAL_KEY` ≡ 达人 `FLYBOOK_INTERNAL_KEY` / `PORTAL_INTERNAL_KEY`

---

## 飞书 OAuth 绑定

流程见[飞书网页应用 SSO](https://open.feishu.cn/document/sso/web-application-sso/login-overview)：

1. 登录 xlink → 打开「飞书」→「绑定飞书」
2. `POST /api/flybook/auth/bind/start`（Bearer 门户 JWT）→ 跳转飞书授权
3. `GET /api/flybook/auth/callback` 保存 token 并绑定当前用户
4. 重定向 `PORTAL_FRONTEND_URL/flybook?bind=success`

**开放平台配置：**

- 安全设置 → 重定向 URL = `FEISHU_OAUTH_REDIRECT_URI`（须完全一致）
- 申请 `offline_access` 等 scope（云文档 / 妙记所需权限见 `.env.example` 注释）
- 修改 scope 后用户需重新绑定

---

## 主要 API

| 路径 | 说明 |
|------|------|
| `GET /health` | 健康检查 |
| `GET /api/flybook/auth/status` | 绑定状态 |
| `POST /api/flybook/auth/bind/start` | 发起绑定 |
| `GET /api/flybook/auth/callback` | OAuth 回调 |
| `GET /api/flybook/config` | 前端所需配置（消息入口等） |
| `POST /api/flybook/callback` | 事件订阅回调 |
| `GET/POST /api/flybook/docs/*` | 云文档：文件、创建、导入、镜像、组件 auth |
| `GET/POST /api/flybook/internal/documents/*` | 内部导出 / 镜像（Header 内部密钥） |
| `GET/POST /api/flybook/minutes/*` | 妙纪 AI：搜索、会话结束、详情、产物 |
| `WS /api/flybook/ws/minutes/transcribe` | 妙纪实时转写 |

Swagger：http://localhost:8002/docs

---

## 环境变量

见 `.env.example`。常用项：

| 变量 | 说明 |
|------|------|
| `API_PORT` | 默认 8002 |
| `JWT_SECRET` | 与门户一致 |
| `PORTAL_API_URL` | 门户达人后端地址 |
| `PORTAL_FRONTEND_URL` | 绑定完成跳转 |
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | 开放平台应用 |
| `FEISHU_OAUTH_REDIRECT_URI` | OAuth 回调（开发多为 `http://localhost:5173/api/flybook/auth/callback`） |
| `FEISHU_VERIFICATION_TOKEN` / `FEISHU_ENCRYPT_KEY` | 事件订阅 |
| `FEISHU_MESSENGER_URL` | 消息页嵌入地址 |
| `FLYBOOK_INTERNAL_KEY` | 内部调门户 / 被门户调用 |

生产示例另见 `.env.production.example`。

---

## 项目结构

```
flybook/
├── api/
│   ├── main.py
│   ├── portal_auth.py
│   ├── routes/          # auth / config / callback / docs / internal_docs / minutes
│   └── ws/              # minutes_transcribe
├── integrations/feishu/ # OpenAPI 客户端、加解密
├── services/            # 绑定、文档镜像、JSSDK、门户 token
├── .env.example
├── Dockerfile
└── README.md333333333333333333333333333333333
```

---

## 部署

- 默认端口 **8002**
- Nginx / 门户将 `/api/flybook/*` 反代到本服务，并开启 **WebSocket**（妙纪）
- 全栈编排见仓库根 `docker-compose.yml` 与 [`docker/DEPLOY.md`](../docker/DEPLOY.md)
- 公网域名变更时同步：`PORTAL_FRONTEND_URL`、`FEISHU_OAUTH_REDIRECT_URI`、开放平台重定向 URL、`CORS_ORIGINS`
