# Handoff: deploy Konsilier.AI to Yandex Cloud (Kazakhstan)

Context for the next Claude Code session. Everything below is already decided with the founder.

## State (2026-09-27)

- Code: branch `claude/zealous-volta-a3ipv6` in `gigrosscom/legal-autopilot` (public repo — consider making it private
  and adding a deploy key on the server).
- Temporary production: Railway project `konsilier` (web, api, Postgres). Railway auto-deploys this branch.
  Railway has a leftover function `debug-case-dump` — delete it.
- Domain `konsilier.com` at Spaceship; mail `info@konsilier.com` works (keep MX/TXT). Site DNS not configured yet.
- Claude works in production (`LLM_PROVIDER=anthropic`).
- Personal data of RK citizens must be stored in Kazakhstan → move to Yandex Cloud region `kz1`.

## Deployed (2026-09-27)

Production runs in Yandex Cloud `kz1-a` (folder `default`):

| Resource | Value |
|---|---|
| VM | `konsilier` (`b4eh5enmn10g32492lmh`), Ubuntu 24.04, 2 vCPU / 8 GB / 50 GB SSD, standard-v3 |
| Static IP | `94.131.93.236` (DNS at Spaceship: A @, www, api) |
| Security group | `konsilier-web`: in 80/443 + ICMP, out any |
| Database | PostgreSQL 16 on the VM (`COMPOSE_PROFILES=localdb`), daily dump → bucket `backups/` |
| Files | bucket `konsilier-files` (`storage.yandexcloud.kz`), SA `konsilier-storage` (storage.editor) + static key |
| Secrets | VM metadata key `konsilier-env` → `/opt/konsilier/.env` (see deploy/update.sh). Edit it to change config |
| Logs | serial console: lines `konsilier: deployed <sha> api=… web=… https://…=200` after each deploy |

Every push to the branch redeploys within ~2 minutes. The API is reached from Claude Code sessions via
REST (`*.api.yandexcloud.kz`); `storage.yandexcloud.net` (yc CLI installer) is not needed.
`ANTHROPIC_API_KEY` is reserved by Claude Code and is not passed into sessions — use
`KONSILIER_ANTHROPIC_API_KEY` for the production key.

## Credentials expected in the environment

| Variable | Meaning |
|---|---|
| `YC_SA_KEY_JSON` | authorized key JSON of service account `konsilier-deployer` (role admin on the folder) |
| `YC_FOLDER_ID`, `YC_CLOUD_ID` | target folder / cloud |
| `KONSILIER_ANTHROPIC_API_KEY` | Claude key for the production `.env` |

Network allowlist needed: `yandexcloud.kz`, `api.yandexcloud.kz`, `storage.yandexcloud.kz`, `storage.yandexcloud.net`.
Never print these values.

## Plan

1. Install `yc` CLI; configure with the key, cloud, folder; set the KZ API endpoint (verify in Yandex docs for kz1).
2. Check which services exist in kz1 (Compute, Managed PostgreSQL, Object Storage).
3. Create: VPC network + subnet in `kz1-a`, static public IP, security group (22 only if needed, 80, 443).
4. Create VM: Ubuntu 24.04, 4 vCPU / 8 GB / 80 GB SSD, user data = `deploy/cloud-init.yaml`.
5. Managed PostgreSQL 16 (smallest class, daily backups, same network) — or `COMPOSE_PROFILES=localdb`.
6. Object Storage bucket `konsilier-files` + static access key for it.
7. Write `/opt/konsilier/.env` from `deploy/env.example` (generate new ADMIN_TOKEN, BOT_API_SECRET), chmod 600,
   run `deploy/update.sh --force`. Delivery of `.env`: VM metadata / serial console / ssh — choose the safest available.
8. Give the founder DNS records for Spaceship: `A @`, `A www`, `A api` → static IP (keep mail records).
9. After certificates are issued: smoke test web + api + a test case with Claude; then decommission Railway.
10. Reduce the service account's role (or delete the key) once done.
