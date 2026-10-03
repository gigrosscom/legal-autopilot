"""Set or replace variables in the production .env stored in Yandex Cloud VM metadata (`konsilier-env`).

The server picks the change up within ~2 minutes (deploy/update.sh) and redeploys. Never prints values.

    pip install pyjwt cryptography requests
    python deploy/yc_set_env.py LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=@KONSILIER_ANTHROPIC_API_KEY

`NAME=@ENVVAR` takes the value from the environment variable ENVVAR (keeps secrets out of shell history).
Needs YC_SA_KEY_JSON and YC_FOLDER_ID in the environment.
"""

from __future__ import annotations

import json
import os
import sys
import time

import jwt
import requests

IAM = "https://iam.api.yandexcloud.kz/iam/v1/tokens"
COMPUTE = "https://compute.api.yandexcloud.kz/compute/v1"
OPERATION = "https://operation.api.yandexcloud.kz/operations"
VM_NAME = os.environ.get("KONSILIER_VM_NAME", "konsilier")


def iam_token() -> str:
    key = json.loads(os.environ["YC_SA_KEY_JSON"])
    now = int(time.time())
    signed = jwt.encode({"aud": IAM, "iss": key["service_account_id"], "iat": now, "exp": now + 3600},
                        key["private_key"], algorithm="PS256", headers={"kid": key["id"]})
    r = requests.post(IAM, json={"jwt": signed}, timeout=30)
    r.raise_for_status()
    return r.json()["iamToken"]


def main(args: list[str]) -> int:
    updates: dict[str, str] = {}
    for arg in args:
        name, _, value = arg.partition("=")
        if not name or not _:
            print(f"bad argument (expected NAME=value): {name}", file=sys.stderr)
            return 2
        if value.startswith("@"):
            value = os.environ.get(value[1:], "")
            if not value:
                print(f"{name}: environment variable {arg.split('@', 1)[1]} is empty", file=sys.stderr)
                return 2
        updates[name] = value

    h = {"Authorization": f"Bearer {iam_token()}"}
    vms = requests.get(f"{COMPUTE}/instances", params={"folderId": os.environ["YC_FOLDER_ID"]}, headers=h, timeout=30)
    vms.raise_for_status()
    vm = next((v for v in vms.json().get("instances", []) if v["name"] == VM_NAME), None)
    if not vm:
        print(f"VM {VM_NAME} not found", file=sys.stderr)
        return 1
    full = requests.get(f"{COMPUTE}/instances/{vm['id']}", params={"view": "FULL"}, headers=h, timeout=30)
    full.raise_for_status()
    lines = full.json().get("metadata", {}).get("konsilier-env", "").splitlines()

    seen = set()
    for i, line in enumerate(lines):
        name = line.split("=", 1)[0]
        if name in updates:
            lines[i] = f"{name}={updates[name]}"
            seen.add(name)
    lines += [f"{n}={v}" for n, v in updates.items() if n not in seen]

    op = requests.post(f"{COMPUTE}/instances/{vm['id']}/updateMetadata",
                       json={"upsert": {"konsilier-env": "\n".join(lines) + "\n"}}, headers=h, timeout=30)
    op.raise_for_status()
    op_id = op.json()["id"]
    for _ in range(60):
        st = requests.get(f"{OPERATION}/{op_id}", headers=h, timeout=30).json()
        if st.get("done"):
            if "error" in st:
                print("update failed:", st["error"], file=sys.stderr)
                return 1
            break
        time.sleep(2)
    print("updated:", ", ".join(sorted(updates)), "— the server redeploys within ~2 minutes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
