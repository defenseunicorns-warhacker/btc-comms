FROM python:3.11-slim

WORKDIR /app

# System deps for opentimestamps-client (needs git for calendar upgrades)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY web/ ./web/

ENV PYTHONUNBUFFERED=1 \
    DB_PATH=/data/ledger.db \
    STAMP_INTERVAL=30 \
    UPGRADE_INTERVAL=120 \
    DEMO_MODE=false

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/verify')"

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
