# Flybook — 飞书独立后端

飞书集成服务，与达人系统、会议 AI **独立部署**，通过 xlink 门户 JWT 识别已登录用户。

## 职责

- 飞书 OAuth **绑定**（非登录页入口，须先登录 xlink）
- 飞书开放平台 API、事件回调
- 保存 user_access_token / refresh_token 到门户用户

前端页面（`/flybook`）仍在 `Information_Aggregation/frontend` 统一管理。

## 快速启动

```bash
cd flybook
cp .env.example .env
pip install -r requirements.txt
uvicorn api.main:app --reload --host 0.0.0.0 --port 8002
```

**JWT 密钥**：`flybook/.env` 的 `JWT_SECRET` 须与达人后端 `SECRET_KEY` 一致。

## 飞书 OAuth 绑定（非登录页入口）

用户须**先登录 xlink**，再在「飞书」页面绑定。流程见[飞书网页应用 SSO](https://open.feishu.cn/document/sso/web-application-sso/login-overview)：

1. 进入 `/flybook` → 点击「绑定飞书并打开」
2. `POST /api/flybook/auth/bind/start`（须携带门户 JWT）→ 跳转飞书授权
3. 回调 `GET /api/flybook/auth/callback` → 保存 token 并绑定到当前用户
4. 重定向回 `/flybook?bind=success`，自动打开飞书窗口

**飞书开放平台：**

- 「安全设置 → 重定向 URL」= `FEISHU_OAUTH_REDIRECT_URI`
- 申请 `offline_access` 以获取 refresh_token

## 主要 API

| 路径 | 说明 |
|------|------|
| `GET /health` | 健康检查 |
| `POST /api/flybook/auth/bind/start` | 发起飞书绑定（须 Bearer Token） |
| `GET /api/flybook/auth/callback` | 飞书 OAuth 回调 |
| `GET /api/v1/auth/feishu/status` | 门户：当前用户绑定状态 |
| `POST /api/flybook/callback` | 飞书事件订阅回调 |

## 环境变量

见 `.env.example`。`FLYBOOK_INTERNAL_KEY` 须与达人后端一致。

## 分布式部署

- 默认端口 **8002**
- Nginx 将 `/api/flybook/*` 反向代理到 flybook 服务
