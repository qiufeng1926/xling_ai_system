# xlink Agent — 办公智能体

## 文档

- [MVP 说明书](docs/MVP.md)

## 本地启动（开发机，无需 Docker）

```bash
cd xlink_agent/backend
cp .env.example .env   # 填入 GLM_API_KEY，JWT_SECRET 与门户一致
# .env 默认 QDRANT_MODE=local，向量库嵌入进程内，数据写到 ./data/qdrant
pip install -r requirements.txt
playwright install chromium
# MySQL 需有库 xlink_agent。本机无 Docker 时执行：
#   scripts\init-local-mysql.cmd
# （默认 root 密码 root，与门户 .env 中 MYSQL_ROOT_PASSWORD 一致）
uvicorn api.main:app --reload --port 8003
```

Qdrant **不必**用 Docker：开发默认用 `qdrant-client` 的 **local 嵌入式**模式。

## 生产部署（Docker）

根目录 `docker-compose.yml` 含 `qdrant` + `xlink-agent`：

- `QDRANT_MODE=url`
- `QDRANT_URL=http://qdrant:6333`

## 前端

门户菜单「智能体」→ `/agent`，开发代理 `/api/agent` → `:8003`。
