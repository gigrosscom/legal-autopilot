"""Read the production VM's serial console: deploy results and the hourly product metrics line.

    python deploy/yc_serial.py            # last deploy / metrics lines
    python deploy/yc_serial.py metrics    # only the metrics lines

Needs YC_SA_KEY_JSON and YC_FOLDER_ID in the environment (same as yc_set_env.py). Prints no secrets:
the metrics line holds counts only.
"""

from __future__ import annotations

import os
import sys

import requests

sys.path.insert(0, os.path.dirname(__file__))
from yc_set_env import COMPUTE, VM_NAME, iam_token  # noqa: E402


def main(args: list[str]) -> int:
    h = {"Authorization": f"Bearer {iam_token()}"}
    vms = requests.get(f"{COMPUTE}/instances", params={"folderId": os.environ["YC_FOLDER_ID"]}, headers=h, timeout=30)
    vms.raise_for_status()
    vm = next((v for v in vms.json().get("instances", []) if v["name"] == VM_NAME), None)
    if not vm:
        print(f"VM {VM_NAME} not found", file=sys.stderr)
        return 1
    out = requests.get(f"{COMPUTE}/instances/{vm['id']}:serialPortOutput", headers=h, timeout=60)
    out.raise_for_status()
    lines = [line for line in out.json().get("contents", "").splitlines() if "konsilier:" in line]
    if args[:1] == ["metrics"]:
        lines = [line for line in lines if "konsilier: metrics " in line]
    print("\n".join(lines[-15:]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
