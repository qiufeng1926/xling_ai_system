# 会议 AI 后端 — 独立镜像，默认监听 8001（与 xlink 门户集成）
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FFMPEG_PATH=/usr/bin \
    APP_ENV=production

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# PyTorch CPU 需单独指定源
RUN pip install --no-cache-dir \
    torch==2.12.0+cpu \
    torchaudio==2.11.0+cpu \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN sed -e '/^torch/d' -e '/^torchaudio/d' requirements.txt > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

RUN mkdir -p upload output logs

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8001/health >/dev/null || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001"]
