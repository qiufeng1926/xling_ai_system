# xlink 统一门户前端 — 独立镜像，通过环境变量连接各后端服务
# 构建阶段
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --registry=https://registry.npmmirror.com

COPY . .
RUN npm run build

# 运行阶段
FROM nginx:1.27-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template

# Docker 网络内的服务名，可在编排文件中覆盖
ENV INFLUENCER_API_HOST=backend:8000 \
    MEETING_API_HOST=meeting-ai:8001 \
    FLYBOOK_API_HOST=flybook:8002

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
