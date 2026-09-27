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
RUN [ -f /app/packs/kz/templates/consumer/claim_seller.docx ] || python /app/scripts/build_kz_templates.py
ENV PACKS_DIR=/app/packs
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn --factory konsilier.main:app_factory --host 0.0.0.0 --port ${PORT:-8000}"]
