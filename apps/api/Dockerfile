# Ubuntu 24.04 ships Python 3.12 and a current headless LibreOffice.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PATH=/opt/venv/bin:$PATH
# LibreOffice (headless Writer) for DOCX → PDF; DejaVu fonts cover Cyrillic/Kazakh.
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv postgresql-client libreoffice-writer-nogui fonts-dejavu-core ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m venv /opt/venv

WORKDIR /app/apps/api
COPY apps/api/ ./
RUN pip install --no-cache-dir ".[dev]"
COPY packs/ /app/packs/
COPY scripts/ /app/scripts/
# DOCX templates are pack data; regenerate them if the checkout has none (e.g. text-only mirrors).
RUN [ -f /app/packs/kz/templates/consumer/claim_seller.docx ] && [ -f /app/packs/kz/templates/generic/complaint.docx ] \
    || python /app/scripts/build_kz_templates.py
ENV PACKS_DIR=/app/packs
EXPOSE 8000
# `exec`: uvicorn becomes PID 1 and gets Docker's SIGTERM itself (sh never passed it on, so every restart ended in a
# SIGKILL after 10 s and cut the chat answers being streamed). On SIGTERM uvicorn stops accepting connections and lets
# the answers in flight finish for up to UVICORN_GRACE seconds (docker-compose.prod.yml: stop_grace_period is longer).
CMD ["sh", "-c", "alembic upgrade heads && exec uvicorn --factory konsilier.main:app_factory --host 0.0.0.0 --port ${PORT:-8000} --timeout-graceful-shutdown ${UVICORN_GRACE:-50}"]
