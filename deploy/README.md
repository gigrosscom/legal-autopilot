# Production deployment (single server, Kazakhstan)

Target: Yandex Cloud region `kz1` (or any Ubuntu 24.04 server in Kazakhstan).

| Resource | Yandex Cloud service | Notes |
|---|---|---|
| Server | Compute Cloud VM, `kz1-a`, Ubuntu 24.04, 4 vCPU / 8 GB / 80 GB SSD, static public IP | runs Caddy (HTTPS), web, api, bot |
| Database | Managed Service for PostgreSQL (if offered in kz1) | otherwise `COMPOSE_PROFILES=localdb` |
| Files | Object Storage bucket `konsilier-files` (`https://storage.yandexcloud.kz`) | documents, uploads, daily backups |

Yandex Cloud: `deploy/yc-provision.sh` does steps 1-4 (network, VM, PostgreSQL, bucket, `.env` via one-off metadata).

1. Create the VM with `deploy/cloud-init.yaml` as user data.
2. Put the filled `deploy/env.example` at `/opt/konsilier/.env` (chmod 600).
3. `sudo /opt/konsilier/deploy/update.sh --force` — first start; afterwards the timer redeploys on every push.
4. DNS: `A @ → <IP>`, `A www → <IP>`, `A api → <IP>`. Caddy issues certificates automatically.
5. Backups: `konsilier-backup.timer` daily at 03:30 → `backups/` in the bucket.

Restore: download a dump from the bucket, `gunzip -c dump.sql.gz | psql "$DATABASE_URL"`.
