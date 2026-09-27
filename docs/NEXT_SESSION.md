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

## Credentials expected in the environment

| Variable | Meaning |
|---|---|
| `YC_SA_KEY_JSON` | authorized key JSON of service account `konsilier-deployer` (role admin on the folder) |
| `YC_FOLDER_ID`, `YC_CLOUD_ID` | target folder / cloud |
| `ANTHROPIC_API_KEY` | Claude key for the production `.env` |

Network allowlist needed: `yandexcloud.kz`, `api.yandexcloud.kz`, `storage.yandexcloud.kz`, `storage.yandexcloud.net`.
Never print these values.

## Status of the 2026-09-27 attempt

Blocked: the session's network policy denied `api.yandexcloud.kz`, `storage.yandexcloud.net`, `storage.yandexcloud.kz`,
`yandexcloud.kz` (proxy 403), and `ANTHROPIC_API_KEY` was not set. Nothing was created in Yandex Cloud.
Steps 1-8 are now scripted: once the hosts are allowed and the variables are set, run `deploy/yc-provision.sh`
(idempotent; `USE_MANAGED_PG=0` for a database on the VM, `PG_PRESET=...` to change the class).

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
