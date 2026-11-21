#!/usr/bin/env python3
"""Continuously drain Verigate's wallet-governance outbox to the external log."""
from __future__ import annotations

import argparse
import base64
import os
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.storage import Storage
from core.wallet_governance_outbox import WalletGovernanceOutboxDispatcher
from core.wallet_governance_transparency_http import WalletGovernanceTransparencyHTTPTransport


TOKEN_ENV = "VERIGATE_WALLET_GOVERNANCE_LOG_BEARER_TOKEN"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, help="Verigate SQLite database containing the durable outbox")
    parser.add_argument("--log-url", required=True, help="HTTPS origin of the independent wallet log")
    parser.add_argument("--log-public-key", required=True, help="PEM Ed25519 public key provisioned out of band")
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between retry sweeps (default: 5)")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP request timeout in seconds (max 60)")
    parser.add_argument("--once", action="store_true", help="run one sweep and exit")
    args = parser.parse_args()

    if not Path(args.database).is_file():
        parser.error("--database must reference the existing Verigate database")
    if (
        isinstance(args.interval, bool)
        or not 0.1 <= args.interval <= 3600
    ):
        parser.error("--interval must be between 0.1 and 3600 seconds")
    if (
        isinstance(args.timeout, bool)
        or not 0 < args.timeout <= 60
    ):
        parser.error("--timeout must be greater than 0 and no more than 60 seconds (below the 120-second lease)")

    bearer_token = os.environ.get(TOKEN_ENV, "")
    if len(bearer_token) < 32:
        parser.error(f"{TOKEN_ENV} must be set to a secret of at least 32 characters")

    try:
        public_key = serialization.load_pem_public_key(
            Path(args.log_public_key).read_bytes(),
        )
    except (OSError, ValueError, TypeError) as exc:
        parser.error(f"cannot load trusted wallet log public key: {exc}")
    if not isinstance(public_key, Ed25519PublicKey):
        parser.error("--log-public-key must contain an Ed25519 public key")
    raw_public_key = public_key.public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    trusted_key_b64 = base64.b64encode(raw_public_key).decode("ascii")

    storage = Storage(args.database)
    try:
        transport = WalletGovernanceTransparencyHTTPTransport(
            args.log_url,
            bearer_token=bearer_token,
            timeout=args.timeout,
        )
        dispatcher = WalletGovernanceOutboxDispatcher(
            storage,
            transport,
            trusted_log_public_key_b64=trusted_key_b64,
        )

        print("Wallet governance outbox worker started.")
        while True:
            results = dispatcher.dispatch_pending()
            for item in results:
                if item.get("delivered"):
                    print(
                        f"DELIVERED action={item['action_id']} "
                        f"checkpoint={item.get('checkpoint_sha256')}"
                    )
                else:
                    print(
                        f"{item.get('status', 'PENDING')} action={item.get('action_id')} "
                        f"reason={item.get('reason', 'delivery not completed')}"
                    )
            pending = [item for item in results if not item.get("delivered")]
            if args.once:
                return 1 if pending else 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    finally:
        storage.close()


if __name__ == "__main__":
    raise SystemExit(main())
