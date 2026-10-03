#!/usr/bin/env bash
# Pull the deploy branch and rebuild the stack when it (or the .env) changed.
# Run by the konsilier-update timer.
#
# .env source: if the VM metadata has the attribute `konsilier-env` (Yandex Cloud / GCE metadata
# service), it is written to /opt/konsilier/.env — secrets are then managed from the cloud console
# or API without SSH. Otherwise the existing .env on disk is used.
set -euo pipefail

# Wrapped in a function: bash parses it fully before running, so `git reset` below
# can replace this file safely mid-run.
main() {
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
  [ -f .env ] || { log "no .env yet, waiting"; return 0; }

  git fetch --quiet origin "$BRANCH"
  LOCAL=$(git rev-parse HEAD)
  REMOTE=$(git rev-parse "origin/$BRANCH")
  if [ "$LOCAL" != "$REMOTE" ] || [ "$FORCE" = "--force" ]; then
    git reset --quiet --hard "origin/$BRANCH"
    log "deploying ${REMOTE:0:7}"
    if docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --build --remove-orphans; then
      docker image prune -f >/dev/null
      docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T caddy \
        caddy reload --config /etc/caddy/conf/Caddyfile --adapter caddyfile >/dev/null 2>&1 || log "caddy reload failed"
      sleep 20
      API=$(docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T api \
        python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/health').status)" 2>&1 | tail -1)
      WEB=$(docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T web \
        node -e "fetch('http://localhost:3000/').then(r=>console.log(r.status)).catch(e=>console.log(e.message))" 2>&1 | tail -1)
      # Which models are configured — read from settings only: no API call, nothing is spent.
      LLM=$(docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T api python -c "
from konsilier.config import get_settings
s = get_settings()
print({'anthropic': s.llm_model + ',' + s.llm_fast_model, 'gemini': 'gemini:' + s.gemini_model}.get(s.llm_provider, s.llm_provider) + ':configured')" 2>&1 | tail -1)
      # Sign-in methods that are configured, and whether NCANode (ЭЦП checks) answers at all.
      AUTH=$(docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T api python -c "
import httpx
from konsilier.config import get_settings
from konsilier.container import build_container
s = get_settings(); c = build_container(s)
m = ','.join(k for k, v in c.identity_methods().items() if v) or 'none'
nca = 'off'
if s.ncanode_url:
    try: nca = str(httpx.post(s.ncanode_url.rstrip('/') + '/cms/verify', json={'cms': 'AA=='}, timeout=20).status_code)
    except Exception as e: nca = e.__class__.__name__
print(m + ';ncanode=' + nca)" 2>&1 | tail -1)
      # The legal agent reads the official portal live: one article of the Labour Code as a smoke test.
      LAWS=$(docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T api python -c "
from konsilier.lawagent.sources import Adilet
try:
    a = Adilet().article('K1500000414', '113')
    print('ok:' + str(len(a.text)) + 'ch')
except Exception as e:
    print(e.__class__.__name__ + ':' + str(e)[:60].replace(' ', '_'))" 2>&1 | tail -1)
      # Main acts listed in the packs: each code must open on the portal (free, reads public pages).
      ACTS=$(docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T api python -c "
from konsilier.config import get_settings
from konsilier.core.packs import PackRegistry
from konsilier.lawagent.sources import Adilet
a, ok, bad = Adilet(), 0, []
for p in PackRegistry.load(get_settings().packs_dir).packs.values():
    for s in p.manifest.legal_sources:
        for k in s.key_acts:
            try:
                a.contents(k.code); ok += 1
            except Exception as e:
                bad.append(k.code)
print(str(ok) + 'ok' + ('' if not bad else ',bad:' + '/'.join(bad)))" 2>&1 | tail -1)
      # Chat model: only the free Gemini tier is called (one short request); a paid model is never called here.
      CHAT=$(docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T api python -c "
from konsilier.config import get_settings
s = get_settings()
if s.chat_provider != 'gemini' or not s.gemini_api_key:
    print(s.chat_provider + ':not-called'); raise SystemExit
from konsilier.gemini import GeminiClient
try:
    with GeminiClient(s.gemini_api_key).messages.stream(model=s.gemini_model, max_tokens=5, system='Reply: ok',
                                                        tools=[], messages=[{'role': 'user', 'content': 'ok?'}]) as st:
        st.get_final_message()
    print('gemini:' + s.gemini_model + ':ok')
except Exception as e:
    print('gemini:' + str(e)[:120].replace(' ', '_'))" 2>&1 | tail -1)
      # Read only what we need: .env holds values bash must not execute (e.g. "Name <a@b>").
      SITE_DOMAIN=$(grep -E '^SITE_DOMAIN=' .env | tail -1 | cut -d= -f2- | tr -d '"'"'"'')
      API_DOMAIN=$(grep -E '^API_DOMAIN=' .env | tail -1 | cut -d= -f2- | tr -d '"'"'"'')
      HTTPS=$(for u in "https://$SITE_DOMAIN/" "https://www.$SITE_DOMAIN/" "https://$API_DOMAIN/health"; do
        printf '%s=%s ' "$u" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$u")"; done)
      CACHE=$(curl -sI --max-time 20 "https://$SITE_DOMAIN/" | tr -d '\r' | grep -i '^cache-control:' | cut -d' ' -f2-)
      log "deployed ${REMOTE:0:7} api=$API web=$WEB llm=$LLM auth=$AUTH laws=$LAWS acts=$ACTS chat=$CHAT $HTTPS cache=[$CACHE]"
      log "$(docker compose -f deploy/docker-compose.prod.yml --env-file .env ps --format '{{.Service}}:{{.State}}' | tr '\n' ' ')"
    else
      log "deploy of ${REMOTE:0:7} FAILED"
    fi
  fi
}
main "$@"
