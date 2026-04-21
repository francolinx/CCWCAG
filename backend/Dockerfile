FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps for Playwright + Pillow + lxml.
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates \
      libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libxcomposite1 \
      libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 \
      libasound2 libx11-xcb1 libjpeg62-turbo libxml2 libxslt1.1 \
      fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt \
 && python -m playwright install --with-deps chromium

COPY . /app

ENV SQLITE_PATH=/data/app.db \
    VECTOR_DB_PATH=/data/vectorstore \
    ARTIFACTS_DIR=/data/artifacts \
    WCAG_CORPUS_DIR=/app/backend/data/wcag_corpus

RUN mkdir -p /data/vectorstore /data/artifacts/screenshots /data/artifacts/annotations /data/artifacts/reports \
 && python scripts/ingest_wcag.py || true

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
