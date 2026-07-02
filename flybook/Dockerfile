# 飞书集成后端 — 独立镜像，默认监听 8002（与 xlink 门户集成）
ARG PYTHON_BASE_IMAGE=python:3.11-slim
FROM ${PYTHON_BASE_IMAGE}

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_ENV=production

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
ARG PIP_INDEX_URL=
ARG PIP_TRUSTED_HOST=
RUN if [ -n "$PIP_INDEX_URL" ]; then \
      pip install --no-cache-dir -r requirements.txt \
        --index-url "$PIP_INDEX_URL" \
        ${PIP_TRUSTED_HOST:+--trusted-host "$PIP_TRUSTED_HOST"}; \
    else \
      pip install --no-cache-dir -r requirements.txt; \
    fi

COPY . .

RUN mkdir -p logs

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8002/health >/dev/null || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8002"]
