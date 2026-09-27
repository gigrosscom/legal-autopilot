#!/usr/bin/env bash
# Pull the deploy branch and rebuild the stack when it (or the .env) changed.
# Run by the konsilier-update timer.
#
# .env source: if the VM metadata has the attribute `konsilier-env` (Yandex Cloud / GCE metadata
# service), it is written to /opt/konsilier/.env — secrets are then managed from the cloud console
# or API without SSH. Otherwise the existing .env on disk is used.
set -euo pipefail
cd /opt/konsilier
exec 9>/run/konsilier-update.lock
flock -n 9 || exit 0  # another run is in progress
BRANCH="${DEPLOY_BRANCH:-claude/zealous-volta-a3ipv6}"
FORCE="${1:-}"

log() { echo "$(date -Is) konsilier: $*"; echo "konsilier: $*" > /dev/ttyS0 2>/dev/null || true; }

META=http://169.254.169.254/computeMetadata/v1/instance/attributes/konsilier-env
if NEW_ENV=$(curl -sf -H "Metadata-Flavor: Google" "$META"); then
  if [ -n "$NEW_ENV" ] && [ "$NEW_ENV" != "$(cat .env 2>/dev/null)" ]; then
    umask 077
    printf '%s\n' "$NEW_ENV" > .env
    log ".env updated from metadata"
    FORCE=--force
  fi
fi
[ -f .env ] || { log "no .env yet, waiting"; exit 0; }

git fetch --quiet origin "$BRANCH"
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")
if [ "$LOCAL" != "$REMOTE" ] || [ "$FORCE" = "--force" ]; then
  git reset --quiet --hard "origin/$BRANCH"
  log "deploying ${REMOTE:0:7}"
  if docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --build --remove-orphans; then
    docker image prune -f >/dev/null
    sleep 20
    API=$(docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T api \
      python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/health').status)" 2>&1 | tail -1)
    WEB=$(docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T web \
      node -e "fetch('http://localhost:3000/').then(r=>console.log(r.status)).catch(e=>console.log(e.message))" 2>&1 | tail -1)
    set -a; . ./.env; set +a
    HTTPS=$(for u in "https://$SITE_DOMAIN/" "https://www.$SITE_DOMAIN/" "https://$API_DOMAIN/health"; do
      printf '%s=%s ' "$u" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$u")"; done)
    log "deployed ${REMOTE:0:7} api=$API web=$WEB $HTTPS"
    log "$(docker compose -f deploy/docker-compose.prod.yml --env-file .env ps --format '{{.Service}}:{{.State}}' | tr '\n' ' ')"
  else
    log "deploy of ${REMOTE:0:7} FAILED"
  fi
fi
