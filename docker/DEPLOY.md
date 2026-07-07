# xlink 生产环境 Docker 部署清单
#
# 部署方式（三选一，勿混用 env 模型）：
#   Windows: docker\scripts\win\validate-deploy.cmd -Strict → build-all.cmd → run-all.cmd
#   Linux:   bash docker/scripts/run-all.sh（需先 distributed.env + 各服务 .env）
#   Compose: cp docker/.env.example docker/.env → docker compose --env-file docker/.env up -d --build
#
# =============================================================================
# 1. 配置文件（必须）
# =============================================================================
# docker/env/distributed.env     基础设施：MySQL/Redis/容器地址/JWT/APP_ENV
# meeting_ai/.env                GLM、听悟、业务参数
# flybook/.env                   飞书 App ID/Secret、OAuth 回调
# Information_Aggregation/backend/.env   达人业务、ADMIN 密码
#
# =============================================================================
# 2. 生产环境必改项（APP_ENV=production 时）
# =============================================================================
# [distributed.env]
#   JWT_SECRET              强随机串（≥32 字符）
#   PORTAL_INTERNAL_KEY     强随机串（三端一致）
#   MYSQL_ROOT_PASSWORD     强密码
#   MYSQL_PASSWORD          强密码
#   APP_ENV=production
#   PORTAL_FRONTEND_URL     公网地址，如 https://www.xlink-ai.cn
#   CORS_ORIGINS            同上域名
#
# [backend/.env]
#   SECRET_KEY              与 JWT_SECRET 相同
#   FLYBOOK_INTERNAL_KEY    与 PORTAL_INTERNAL_KEY 相同
#   ADMIN_PASSWORD          勿用 admin123
#
# [meeting_ai/.env]
#   JWT_SECRET              与 SECRET_KEY 相同
#   GLM_API_KEY             智谱 API
#   ALIBABA_CLOUD_ACCESS_KEY_ID / TINGWU_APP_KEY  听悟
#
# [flybook/.env]
#   JWT_SECRET              与 SECRET_KEY 相同
#   FLYBOOK_INTERNAL_KEY    与 PORTAL_INTERNAL_KEY 相同
#   FEISHU_APP_ID / FEISHU_APP_SECRET
#   FEISHU_OAUTH_REDIRECT_URI=https://你的域名/api/flybook/auth/callback
#   PORTAL_FRONTEND_URL     与 distributed.env 一致
#
# 飞书开放平台 → 安全设置 → 重定向 URL 须与 FEISHU_OAUTH_REDIRECT_URI 完全一致
#
# =============================================================================
# 3. 部署步骤（Windows 推荐）
# =============================================================================
#   docker\scripts\win\validate-deploy.cmd
#   docker\scripts\win\build-all.cmd
#   docker\scripts\win\run-all.cmd
#
# cpolar 域名变更时：更新 flybook/.env 的 PORTAL_FRONTEND_URL、
# FEISHU_OAUTH_REDIRECT_URI 及三端 CORS_ORIGINS，并同步飞书开放平台重定向 URL。
#
# MySQL 权限问题（meeting_ai Access denied）：
#   docker\scripts\win\fix-mysql-grants.cmd
#
# =============================================================================
# 4. 验证
# =============================================================================
#   curl http://localhost:8000/health
#   curl http://localhost:8001/health
#   curl http://localhost:8002/health
#   浏览器打开 http://你的域名/ 登录后测试会议 AI、飞书绑定
#
# =============================================================================
# 5. 安全建议
# =============================================================================
#   - 生产在 Nginx/网关层配置 HTTPS（门户镜像仅监听 80）
#   - 不要将 MySQL 3306 / Redis 6379 暴露到公网
#   - 勿将 .env 提交到 git
