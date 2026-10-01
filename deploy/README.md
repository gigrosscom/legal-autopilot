# Production deployment (single server, Kazakhstan)

Target: Yandex Cloud region `kz1` (or any Ubuntu 24.04 server in Kazakhstan).

| Resource | Yandex Cloud service | Notes |
|---|---|---|
| Server | Compute Cloud VM, `kz1-a`, Ubuntu 24.04, 4 vCPU / 8 GB / 80 GB SSD, static public IP | runs Caddy (HTTPS), web, api, bot |
| Database | Managed Service for PostgreSQL (if offered in kz1) | otherwise `COMPOSE_PROFILES=localdb` |
| Files | Object Storage bucket `konsilier-files` (`https://storage.yandexcloud.kz`) | documents, uploads, daily backups |

1. Create the VM with `deploy/cloud-init.yaml` as user data.
2. Put the filled `deploy/env.example` into the VM metadata key `konsilier-env` (Yandex Cloud: VM → Edit → Metadata).
   `update.sh` copies it to `/opt/konsilier/.env` (chmod 600) and redeploys whenever it changes — no SSH needed.
   Without metadata, write `/opt/konsilier/.env` by hand.
3. `sudo /opt/konsilier/deploy/update.sh --force` — first start; afterwards the timer redeploys on every push.
4. DNS: `A @ → <IP>`, `A www → <IP>`, `A api → <IP>`. Caddy issues certificates automatically.
5. Backups: `konsilier-backup.timer` daily at 03:30 → `backups/` in the bucket.

Restore: download a dump from the bucket, `gunzip -c dump.sql.gz | psql "$DATABASE_URL"`.

Deploys without cutting answers: the API runs as two copies, `api` and `api2` (`docker-compose.prod.yml`); Caddy
sends everything to `api` and switches to `api2` while `api` restarts. `update.sh` builds the images first, then
replaces `api2`, waits until it is healthy, then `api`. A copy being stopped refuses new connections and finishes the
chat answers it is streaming (uvicorn `--timeout-graceful-shutdown`, `UVICORN_GRACE`=50 s; Docker waits 60 s). Only
`api` runs the scheduler; the tick also takes a PostgreSQL advisory lock, so it never runs twice at once. Migrations
run in the copy that starts first while the other still runs the previous code: keep them backward compatible
(add columns/tables; drop or rename only in a later release). The page retries an answer that broke off once
by itself, with the message's idempotency key (`client_id`): the server neither stores nor counts it twice.

Push notifications (the site and the installed app): run `python deploy/vapid_keys.py` once, put the three printed
`VAPID_*` lines into the env (e.g. `python deploy/yc_set_env.py VAPID_PUBLIC_KEY=... VAPID_PRIVATE_KEY=@VAR`). Keep the
pair: a new one drops every subscription. Store apps (Google Play assetlinks: `ANDROID_CERT_SHA256`): `docs/app-stores.md`.
