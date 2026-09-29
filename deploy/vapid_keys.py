"""Print a new VAPID key pair for web push notifications (the site and the installed app).

    python deploy/vapid_keys.py

Put both lines into the server's .env (e.g. with deploy/yc_set_env.py) and redeploy the API. Never commit them.
Changing the pair later makes every existing subscription stop working: people turn notifications on again.
Needs only the `cryptography` package (already installed with the API).
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def main() -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    print(f"VAPID_PUBLIC_KEY={b64url(public)}")
    print(f"VAPID_PRIVATE_KEY={b64url(private)}")
    print("VAPID_SUBJECT=mailto:support@konsilier.com")


if __name__ == "__main__":
    main()
