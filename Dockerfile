# AFRICA RESQ command server.
#
# One process. The mission state, the websocket hub and the broadcast loop all live in
# memory, so this image must run with a single worker -- see docs/DEPLOY.md.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first: they change far less often than the code, so this layer caches.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ ./server/
COPY rover/ ./rover/
COPY dashboard/ ./dashboard/

# Nothing here needs to be root. /data exists and is owned by the app user because the
# deployment mounts a named volume there; a fresh volume inherits this ownership, so an
# app that later needs to write (mission recording, a captured frame) already can.
RUN addgroup --system resq && adduser --system --ingroup resq --no-create-home resq \
 && mkdir -p /data && chown resq:resq /data
USER resq

EXPOSE 8000

# The container is unhealthy the moment the app stops answering, not merely when the
# process dies -- a wedged event loop still has a live PID.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "server.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*", \
     "--ws-ping-interval", "20", "--ws-ping-timeout", "20"]
