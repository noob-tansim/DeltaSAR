"""Make a VAPID key pair for Web Push. Run once and put the two lines into .env (never into git).

  python -m jobs.make_vapid_keys
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


if __name__ == "__main__":
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    print(f"VAPID_PUBLIC_KEY={_b64(public)}")
    print(f"VAPID_PRIVATE_KEY={_b64(private)}")
    print("VAPID_SUBJECT=mailto:your-team-address@example.org")
