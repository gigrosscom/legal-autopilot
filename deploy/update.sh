#!/usr/bin/env bash
# Pull the deploy branch and rebuild the stack when it changed. Run by the konsilier-update timer.
set -euo pipefail
cd /opt/konsilier
BRANCH="${DEPLOY_BRANCH:-claude/zealous-volta-a3ipv6}"
git fetch --quiet origin "$BRANCH"
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")
if [ "$LOCAL" != "$REMOTE" ] || [ "${1:-}" = "--force" ]; then
  git reset --quiet --hard "origin/$BRANCH"
  echo "$(date -Is) deploying $REMOTE"
  docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --build --remove-orphans
  docker image prune -f >/dev/null
fi
