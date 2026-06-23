# Flybook — 飞书独立后端

飞书集成服务，与达人系统、会议 AI **独立部署**，通过 xlink 门户 JWT 单点登录。

## 职责

- 飞书开放平台 API（tenant_access_token、消息/通讯录等扩展点）
- 飞书事件订阅回调（`/api/flybook/callback`）
- 向前端提供配置接口（消息入口 URL、Open API 是否已配置）

前端页面（`/flybook`）仍在 `Information_Aggregation/frontend` 统一管理。

## 快速启动

```bash
cd flybook
cp .env.example .env
pip install -r requirements.txt
uvicorn api.main:app --reload --host 0.0.0.0 --port 8002
```

**JWT 密钥**：`flybook/.env` 的 `JWT_SECRET` 须与达人后端 `SECRET_KEY` 一致。

## 主要 API

| 路径 | 说明 |
|------|------|
| `GET /health` | 健康检查 |
| `GET /api/flybook/config` | 飞书配置（需 Bearer Token） |
| `POST /api/flybook/callback` | 飞书事件订阅回调 |

## 环境变量

见 `.env.example`。生产环境必填：

- `JWT_SECRET` — 与门户一致
- `FEISHU_APP_ID` / `FEISHU_APP_SECRET` — 开放平台自建应用
- `FEISHU_VERIFICATION_TOKEN` / `FEISHU_ENCRYPT_KEY` — 事件订阅
- `CORS_ORIGINS` — 门户域名

## 分布式部署

- 单独容器/进程运行，默认端口 **8002**
- 门户 Vite/Nginx 将 `/api/flybook/*` 反向代理到 flybook 服务
- 飞书开放平台回调 URL 指向公网可达的 `https://your-domain/api/flybook/callback`
