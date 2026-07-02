# xlink 统一门户前端 — 独立镜像，通过环境变量连接各后端服务
# 构建阶段
ARG NODE_BASE_IMAGE=node:20-alpine
FROM ${NODE_BASE_IMAGE} AS builder

WORKDIR /app

COPY package.json package-lock.json ./
ARG NPM_REGISTRY=
RUN if [ -n "$NPM_REGISTRY" ]; then \
      npm ci --registry="$NPM_REGISTRY"; \
    else \
      npm ci; \
    fi

COPY . .
RUN npm run build

# 运行阶段
ARG NGINX_BASE_IMAGE=nginx:1.27-alpine
FROM ${NGINX_BASE_IMAGE}

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
