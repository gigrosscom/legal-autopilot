# court-browser: a real Chromium for konsilier/zann/court.py (deploy/court-browser/server.py). Internal only.
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN pip install --no-cache-dir playwright==1.63.0 \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*
RUN useradd -m browser
USER browser
WORKDIR /app
COPY server.py .
EXPOSE 8090
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=8).status == 200 else 1)"
CMD ["python", "server.py"]
