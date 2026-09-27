#!/usr/bin/env bash
# Provision Konsilier.AI in Yandex Cloud kz1 (docs/NEXT_SESSION.md, steps 1-8). Safe to re-run:
# every resource is looked up by name first and only created when missing.
#
# Needs in the environment (never printed): YC_SA_KEY_JSON, YC_CLOUD_ID, YC_FOLDER_ID, ANTHROPIC_API_KEY.
# Optional: TELEGRAM_BOT_TOKEN, USE_MANAGED_PG=1|0 (default 1), PG_PRESET, VM_PLATFORM, YC_ENDPOINT.
#
# The server .env is delivered through a one-off VM metadata key (konsilier-env): cloud-init copies it to
# /opt/konsilier/.env (chmod 600) and starts the stack; this script then deletes the key. No SSH port is opened.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${YC_SA_KEY_JSON:?}" "${YC_CLOUD_ID:?}" "${YC_FOLDER_ID:?}" "${ANTHROPIC_API_KEY:?}"
ZONE=kz1-a
NET=konsilier-net
SUBNET=konsilier-kz1-a
SG=konsilier-sg
IP_NAME=konsilier-ip
VM=konsilier-prod
PG=konsilier-pg
BUCKET=konsilier-files
STORAGE_SA=konsilier-storage
USE_MANAGED_PG="${USE_MANAGED_PG:-1}"
PG_PRESET="${PG_PRESET:-s3-c2-m8}"
VM_PLATFORM="${VM_PLATFORM:-standard-v3}"
YC_ENDPOINT="${YC_ENDPOINT:-api.yandexcloud.kz:443}"

WORK=$(mktemp -d)
chmod 700 "$WORK"
trap 'rm -rf "$WORK"' EXIT

# 1. yc CLI ---------------------------------------------------------------------------------------
if ! command -v yc >/dev/null; then
  curl -fsSL https://storage.yandexcloud.net/yandexcloud-yc/install.sh | bash -s -- -i "$HOME/yandex-cloud" -n
fi
export PATH="$HOME/yandex-cloud/bin:$PATH"
printf '%s' "$YC_SA_KEY_JSON" > "$WORK/sa-key.json"
yc config profile get konsilier >/dev/null 2>&1 || yc config profile create konsilier >/dev/null
yc config profile activate konsilier >/dev/null
yc config set endpoint "$YC_ENDPOINT"
yc config set service-account-key "$WORK/sa-key.json"
yc config set cloud-id "$YC_CLOUD_ID"
yc config set folder-id "$YC_FOLDER_ID"

id_of() { yc "$@" --format json 2>/dev/null | jq -r '.id // empty'; }

# 2. What kz1 offers ------------------------------------------------------------------------------
yc compute zone list
if [ "$USE_MANAGED_PG" = 1 ] && ! yc managed-postgresql resource-preset list >/dev/null 2>&1; then
  echo "Managed PostgreSQL is not available here, falling back to COMPOSE_PROFILES=localdb"
  USE_MANAGED_PG=0
fi

# 3. Network, subnet, static IP, security group ----------------------------------------------------
[ -n "$(id_of vpc network get "$NET")" ] || yc vpc network create --name "$NET" >/dev/null
[ -n "$(id_of vpc subnet get "$SUBNET")" ] ||
  yc vpc subnet create --name "$SUBNET" --zone "$ZONE" --network-name "$NET" --range 10.10.0.0/24 >/dev/null
[ -n "$(id_of vpc address get "$IP_NAME")" ] ||
  yc vpc address create --name "$IP_NAME" --external-ipv4 zone="$ZONE" --deletion-protection >/dev/null
IP=$(yc vpc address get "$IP_NAME" --format json | jq -r '.external_ipv4_address.address')
if [ -z "$(id_of vpc security-group get "$SG")" ]; then
  yc vpc security-group create --name "$SG" --network-name "$NET" \
    --rule "direction=ingress,port=80,protocol=tcp,v4-cidrs=[0.0.0.0/0]" \
    --rule "direction=ingress,port=443,protocol=tcp,v4-cidrs=[0.0.0.0/0]" \
    --rule "direction=ingress,port=6432,protocol=tcp,v4-cidrs=[10.10.0.0/24]" \
    --rule "direction=egress,from-port=0,to-port=65535,protocol=any,v4-cidrs=[0.0.0.0/0]" >/dev/null
fi
SG_ID=$(id_of vpc security-group get "$SG")

# 5. Database ------------------------------------------------------------------------------------
if [ "$USE_MANAGED_PG" = 1 ]; then
  if [ -z "$(id_of managed-postgresql cluster get "$PG")" ]; then
    PG_PASSWORD=$(openssl rand -hex 24)
    yc managed-postgresql cluster create --name "$PG" --environment production --network-name "$NET" \
      --postgresql-version 16 --resource-preset "$PG_PRESET" --disk-type network-ssd --disk-size 20 \
      --host zone-id="$ZONE",subnet-name="$SUBNET" --security-group-ids "$SG_ID" \
      --backup-window-start 22:00:00 --backup-retain-period-days 7 --deletion-protection \
      --user name=konsilier,password="$PG_PASSWORD" --database name=konsilier,owner=konsilier >/dev/null
  else
    # Existing cluster: rotate the password so the new .env is guaranteed to match.
    PG_PASSWORD=$(openssl rand -hex 24)
    yc managed-postgresql user update konsilier --cluster-name "$PG" --password "$PG_PASSWORD" >/dev/null
  fi
  PG_HOST=$(yc managed-postgresql hosts list --cluster-name "$PG" --format json | jq -r '.[0].name')
  DB_LINES="DATABASE_URL=postgresql+psycopg://konsilier:${PG_PASSWORD}@${PG_HOST}:6432/konsilier?sslmode=require"
else
  PG_PASSWORD=$(openssl rand -hex 24)
  DB_LINES=$(printf 'COMPOSE_PROFILES=localdb\nLOCAL_DB_PASSWORD=%s\nDATABASE_URL=postgresql+psycopg://konsilier:%s@postgres:5432/konsilier' \
    "$PG_PASSWORD" "$PG_PASSWORD")
fi

# 6. Object Storage bucket + static access key ----------------------------------------------------
[ -n "$(id_of iam service-account get "$STORAGE_SA")" ] || yc iam service-account create --name "$STORAGE_SA" >/dev/null
STORAGE_SA_ID=$(id_of iam service-account get "$STORAGE_SA")
yc resource-manager folder add-access-binding "$YC_FOLDER_ID" --role storage.editor \
  --subject serviceAccount:"$STORAGE_SA_ID" >/dev/null 2>&1 || true
yc storage bucket get "$BUCKET" >/dev/null 2>&1 || yc storage bucket create --name "$BUCKET" >/dev/null
yc iam access-key create --service-account-id "$STORAGE_SA_ID" --description "konsilier server" --format json \
  > "$WORK/s3.json"

# 7. Server .env (goes to the VM through metadata only) -------------------------------------------
{
  echo "SITE_DOMAIN=konsilier.com"
  echo "API_DOMAIN=api.konsilier.com"
  echo "$DB_LINES"
  echo "STORAGE_BACKEND=s3"
  echo "S3_ENDPOINT_URL=https://storage.yandexcloud.kz"
  echo "S3_REGION=kz1"
  echo "S3_BUCKET=$BUCKET"
  echo "S3_ACCESS_KEY=$(jq -r '.access_key.key_id' "$WORK/s3.json")"
  echo "S3_SECRET_KEY=$(jq -r '.secret' "$WORK/s3.json")"
  echo "LLM_PROVIDER=anthropic"
  echo "LLM_MODEL=claude-opus-5"
  echo "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY"
  echo "ADMIN_TOKEN=$(openssl rand -hex 32)"
  echo "BOT_API_SECRET=$(openssl rand -hex 32)"
  echo "TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}"
  echo "TELEGRAM_BOT_USERNAME=konsilier_bot"
  echo "APPROVAL_REQUIRED_FIRST_N=50"
  echo "SCHEDULER_INTERVAL_SECONDS=60"
} > "$WORK/server.env"

# 4. VM ------------------------------------------------------------------------------------------
if [ -z "$(id_of compute instance get "$VM")" ]; then
  yc compute instance create --name "$VM" --zone "$ZONE" --platform "$VM_PLATFORM" \
    --cores 4 --memory 8 --core-fraction 100 \
    --create-boot-disk image-folder-id=standard-images,image-family=ubuntu-2404-lts,size=80,type=network-ssd \
    --network-interface subnet-name="$SUBNET",nat-ip-version=ipv4,nat-address="$IP",security-group-ids="$SG_ID" \
    --metadata-from-file user-data=deploy/cloud-init.yaml,konsilier-env="$WORK/server.env" >/dev/null
else
  echo "VM $VM already exists; not touching its .env (update it on the server if needed)."
fi

# Wait for cloud-init to pick up the .env, then remove it from metadata.
if yc compute instance get "$VM" --full --format json | jq -e '.metadata["konsilier-env"]' >/dev/null; then
  for _ in $(seq 1 60); do
    if yc compute instance get-serial-port-output "$VM" 2>/dev/null | grep -q KONSILIER_ENV_INSTALLED; then
      yc compute instance remove-metadata "$VM" --keys konsilier-env >/dev/null
      echo "Server .env installed; metadata key removed."
      break
    fi
    sleep 20
  done
fi

# 8. DNS for Spaceship ---------------------------------------------------------------------------
cat <<EOF

Static IP: $IP
Add at Spaceship (keep the existing MX/TXT mail records):
  A  @    $IP
  A  www  $IP
  A  api  $IP
Admin token: in /opt/konsilier/.env on the server (ADMIN_TOKEN); reach it via the serial console or OS Login.
EOF
