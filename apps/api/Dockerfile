FROM python:3.12-slim

# LibreOffice (headless Writer) for DOCX → PDF; DejaVu fonts cover Cyrillic/Kazakh.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libreoffice-writer-nogui fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app/apps/api
COPY apps/api/ ./
RUN pip install --no-cache-dir ".[dev]"
COPY packs/ /app/packs/
ENV PACKS_DIR=/app/packs PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn --factory konsilier.main:app_factory --host 0.0.0.0 --port 8000"]
