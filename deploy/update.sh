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

  # Self-heal: Docker marks a hung container "unhealthy" but never restarts it. NCANode (ЭЦП checks) hung that way
  # after ~2 days (30.09). Checked on every run of this timer (every couple of minutes), costs one docker inspect.
  for svc in ncanode; do
    CID=$(docker compose -f deploy/docker-compose.prod.yml --env-file .env ps -q "$svc" 2>/dev/null | head -1 || true)
    if [ -n "$CID" ] && [ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$CID" 2>/dev/null || true)" = "unhealthy" ]; then
      log "$svc unhealthy: restarting"
      timeout 60 docker restart "$CID" >/dev/null 2>&1 || log "$svc restart failed"
    fi
  done

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
print({'anthropic': s.llm_model + ',' + s.llm_fast_model, 'gemini': 'gemini:' + s.gemini_model}.get(s.llm_provider, s.llm_provider) + ':configured' + (';scans=on' if s.extract_images_with_llm else ';scans=off'))" 2>&1 | tail -1)
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
      # Chat model: only free models are called (one short request each); a paid model is never called here.
      # CHAT_PROVIDER=free: every provider of the chain separately, e.g. cerebras:ok,gemini:503,groq:ok
      CHAT=$(docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T api python -c "
from konsilier.config import get_settings
from konsilier.container import free_chat_clients
from konsilier.gemini import GeminiClient
s = get_settings()
if s.chat_provider == 'free':
    clients = free_chat_clients(s)
elif s.chat_provider == 'gemini' and s.gemini_api_key:
    clients = [GeminiClient(s.gemini_api_key)]
else:
    print(s.chat_provider + ':not-called'); raise SystemExit
out = []
for c in clients:
    try:
        with c.messages.stream(model=s.gemini_model, max_tokens=5, system='Reply: ok', tools=[],
                               messages=[{'role': 'user', 'content': 'ok?'}]) as st:
            st.get_final_message()
        out.append(c.name + ':ok')
    except Exception as e:
        out.append(c.name + ':' + str(e)[:60].replace(' ', '_'))
print(s.chat_provider + '[' + ','.join(out) + ']' if clients else s.chat_provider + ':no-keys')" 2>&1 | tail -1)
      # Read only what we need: .env holds values bash must not execute (e.g. "Name <a@b>").
      SITE_DOMAIN=$(grep -E '^SITE_DOMAIN=' .env | tail -1 | cut -d= -f2- | tr -d '"'"'"'')
      API_DOMAIN=$(grep -E '^API_DOMAIN=' .env | tail -1 | cut -d= -f2- | tr -d '"'"'"'')
      HTTPS=$(for u in "https://$SITE_DOMAIN/" "https://www.$SITE_DOMAIN/" "https://$API_DOMAIN/health"; do
        printf '%s=%s ' "$u" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$u")"; done)
      CACHE=$(curl -sI --max-time 20 "https://$SITE_DOMAIN/" | tr -d '\r' | grep -i '^cache-control:' | cut -d' ' -f2-)
      # Telegram bot: container state and the HTTP code of getMe (200 = token works; 401 = Telegram reached, token
      # is a placeholder or revoked). Only the code or an exception class is printed, never the token.
      BOT_STATE=$(timeout 20 docker compose -f deploy/docker-compose.prod.yml --env-file .env ps --format '{{.State}}' bot \
        2>/dev/null | head -1) || true
      BOT_TG=$(timeout 40 docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T bot python -c "
import os, urllib.error, urllib.request
tok = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
if not tok:
    print('no-token'); raise SystemExit
try:
    print(urllib.request.urlopen('https://api.telegram.org/bot' + tok + '/getMe', timeout=20).status)
except urllib.error.HTTPError as e:
    print(e.code)
except Exception as e:
    print(e.__class__.__name__)" </dev/null 2>/dev/null | tail -1 | cut -c1-40) || true
      # «Написать нам»: the API route answers 401 without sign-in (route alive), the page on the site answers 200.
      SUP_API=$(timeout 25 curl -s -o /dev/null -w '%{http_code}' --max-time 20 "https://$API_DOMAIN/v1/support") || true
      SUP_WEB=$(timeout 25 curl -s -o /dev/null -w '%{http_code}' --max-time 20 "https://$SITE_DOMAIN/support") || true
      # ЭЦП checks (NCANode) not answering: say why on the console — container state, memory, its last log lines —
      # restart it once and check again after it has loaded the certificate lists (Java, ~1–2 min).
      case "$AUTH" in *ncanode=200*|*ncanode=400*|*ncanode=off*) ;; *)
        DC="docker compose -f deploy/docker-compose.prod.yml --env-file .env"
        NCA_PS=$($DC ps -a --format '{{.State}}/{{.Status}}' ncanode 2>&1 | tail -1 || true)
        MEM=$(free -m 2>/dev/null | awk '/Mem:/{print $3"/"$2"MB"}' || true)
        NCA_LOG=$($DC logs --tail 4 --no-log-prefix ncanode 2>&1 | tr '\n' ' ' | tr -s ' ' | cut -c1-280 || true)
        log "ncanode diag: ps=$NCA_PS mem=$MEM log=$NCA_LOG"
        timeout 60 $DC restart ncanode >/dev/null 2>&1 || true
        sleep 120
        NCA2=$(timeout 60 $DC exec -T api python -c "
import httpx
from konsilier.config import get_settings
s = get_settings()
try: print(httpx.post(s.ncanode_url.rstrip('/') + '/cms/verify', json={'cms': 'AA=='}, timeout=30).status_code)
except Exception as e: print(e.__class__.__name__)" 2>&1 | tail -1 || true)
        log "ncanode after restart: $NCA2 ps=$($DC ps -a --format '{{.State}}/{{.Status}}' ncanode 2>&1 | tail -1 || true)"
        ;;
      esac
      # how busy the VM is: load average, memory in use, and free disk — slow checks above often mean a busy VM
      HOST="load=$(cut -d' ' -f1-3 /proc/loadavg 2>/dev/null | tr ' ' '/' || true) mem=$(free -m 2>/dev/null | awk '/Mem:/{print $3"/"$2"MB"}' || true) disk=$(df -h / 2>/dev/null | awk 'NR==2{print $4}' || true)"
      log "host $HOST"
      log "deployed ${REMOTE:0:7} api=$API web=$WEB llm=$LLM auth=$AUTH laws=$LAWS acts=$ACTS chat=$CHAT bot=${BOT_STATE:-none}:getMe=${BOT_TG:-none} support=api:${SUP_API:-none},page:${SUP_WEB:-none} $HTTPS cache=[$CACHE]"
      log "$(docker compose -f deploy/docker-compose.prod.yml --env-file .env ps --format '{{.Service}}:{{.State}}' | tr '\n' ' ')"
      # KPI (owner 01.10): question → document in 3 minutes. After a deploy, at most every 3 hours, the real path is
      # timed for three cases as a marked test user (deploy/smoke.py --path3): «path3 refund=…s taps=…» lines.
      P3=/run/konsilier-path3.stamp
      SMOKE=$(grep -E '^SMOKE_TOKEN=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"')
      if [ -n "$SMOKE" ] && [ -z "$(find "$P3" -mmin -180 2>/dev/null)" ]; then
        touch "$P3"
        ( SMOKE_TOKEN="$SMOKE" timeout 900 python3 deploy/smoke.py --path3 2>&1 | grep -E '^path3' | while read -r l; do log "$l"; done ) &
      fi
    else
      log "deploy of ${REMOTE:0:7} FAILED"
    fi
  fi

  # Once an hour: product metrics on the serial console, for the team's reports (counts only, no personal data).
  STAMP=/run/konsilier-metrics.stamp
  if [ -z "$(find "$STAMP" -mmin -55 2>/dev/null)" ]; then
    touch "$STAMP"
    METRICS=$(timeout 60 docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T api python -c "
import json, os, urllib.request
r = urllib.request.Request('http://localhost:8000/v1/admin/metrics', headers={'X-Admin-Token': os.environ.get('ADMIN_TOKEN', '')})
m = json.load(urllib.request.urlopen(r, timeout=30))
t, f = m['totals'], m.get('referral') or {}
src = ','.join(f'{k}:{v}' for k, v in sorted((f.get('sources') or {}).items(), key=lambda x: -x[1])[:8])
print(f\"users={t['users']} with_case={t['users_with_case']} cases={t['cases']} documents={t['documents']} submitted={t['submitted']} lawyer_apps={t['lawyer_applications']} referred={f.get('referred_users')} inviters={f.get('inviters')} k={f.get('k_factor')} sources=[{src}]\")
" </dev/null 2>&1 | tail -1) || true
    log "metrics ${METRICS:-unavailable}"
    # chat speed over the last 24 h: seconds until the first words of a reply (median and 90th percentile) and in all
    SPEED=$(timeout 60 docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T api python -c "
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from konsilier.config import get_settings
from konsilier.container import build_container
from konsilier.core.models import ChatMessage
c = build_container(get_settings())
since = datetime.now(timezone.utc) - timedelta(days=1)
with c.session_factory() as s:
    metas = [m or {} for m in s.scalars(select(ChatMessage.meta).where(ChatMessage.role == 'assistant', ChatMessage.created_at > since))]
first = sorted(m['first_ms'] for m in metas if m.get('first_ms') is not None)
total = sorted(m['total_ms'] for m in metas if m.get('total_ms') is not None)
q = lambda xs, p: round(xs[min(len(xs) - 1, int(len(xs) * p))] / 1000, 1) if xs else '-'
print(f'replies={len(first)} first_s=p50:{q(first, .5)},p90:{q(first, .9)} total_s=p50:{q(total, .5)},p90:{q(total, .9)}')
" </dev/null 2>&1 | tail -1) || true
    log "chatspeed ${SPEED:-unavailable}"
  fi

  # Every 15 minutes: progress of the Zann law corpus (counts only).
  ZSTAMP=/run/konsilier-zann.stamp
  if [ -z "$(find "$ZSTAMP" -mmin -14 2>/dev/null)" ]; then
    touch "$ZSTAMP"
    ZANN=$(timeout 60 docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T api python -c "
from konsilier.config import get_settings
from konsilier.container import build_container
from konsilier.zann.corpus import corpus_metrics
c = build_container(get_settings())
with c.session_factory() as s:
    z = corpus_metrics(s)
print(f\"enabled={c.settings.zann_corpus_enabled} acts={z['acts']} done={z['acts_done']} pending={z['acts_pending']} error={z['acts_error']} files={z['files']} mb={round(z['bytes'] / 1e6, 1)} types={z['done_by_type']} last={z['last_fetched_at']}\")
" </dev/null 2>&1 | tail -1) || true
    log "zann ${ZANN:-unavailable}"
  fi
}
main "$@"
