# xlink_agent — 办公智能体后端，默认 :8003
ARG PYTHON_BASE_IMAGE=python:3.11-slim
FROM ${PYTHON_BASE_IMAGE}

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    # Playwright Chromium 依赖
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpango-1.0-0 libcairo2 \
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
    fi \
    && playwright install chromium

COPY . .

RUN mkdir -p logs data/workspaces

EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8003/health >/dev/null || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8003"]
