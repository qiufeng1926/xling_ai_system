# 达人信息管理后端 — 独立镜像，默认监听 8000
ARG PLAYWRIGHT_BASE_IMAGE=mcr.microsoft.com/playwright/python:v1.49.1-noble
FROM ${PLAYWRIGHT_BASE_IMAGE}

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

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

RUN mkdir -p logs cookies

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
