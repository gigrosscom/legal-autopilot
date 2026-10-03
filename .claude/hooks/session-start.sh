#!/bin/bash
# Claude Code on the web: install what the tests and checks need (README → «Тесты»).
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# LibreOffice Writer for DOCX → PDF (same packages as apps/api/Dockerfile; the base image
# ships only libreoffice-core, which cannot open .docx).
if ! dpkg -s libreoffice-writer-nogui >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get install -y --no-install-recommends libreoffice-writer-nogui fonts-dejavu-core >/dev/null 2>&1 \
    || { apt-get update >/dev/null && apt-get install -y --no-install-recommends libreoffice-writer-nogui fonts-dejavu-core >/dev/null; }
fi

# API and Telegram bot (pytest), ruff for linting.
pip install --quiet -e "apps/api[dev]" -e "apps/bot[dev]" ruff

# Web (npm run typecheck / lint).
(cd apps/web && npm install --no-audit --no-fund --silent)
