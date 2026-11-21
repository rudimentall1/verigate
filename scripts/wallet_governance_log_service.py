#!/usr/bin/env python3
"""Run the independent wallet-governance log behind a local TLS reverse proxy."""
from __future__ import annotations

import argparse
import os
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.wallet_governance_transparency import WalletGovernanceTransparencyLog
from core.wallet_governance_transparency_http import make_wallet_governance_log_handler


TOKEN_ENV = "VERIGATE_WALLET_GOVERNANCE_LOG_BEARER_TOKEN"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, help="separate transparency-log SQLite path")
    parser.add_argument("--log-id", required=True, help="stable transparency log identity")
    parser.add_argument("--private-key", required=True, help="PEM Ed25519 signing private key path")
    parser.add_argument(
        "--public-key-output",
        default=None,
        help="optional path for exporting the Ed25519 public key for out-of-band distribution",
    )
    parser.add_argument("--host", default="127.0.0.1", help="loopback bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        parser.error("the reference HTTP service must bind to loopback behind a TLS reverse proxy")
    if isinstance(args.port, bool) or not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")

    bearer_token = os.environ.get(TOKEN_ENV, "")
    if len(bearer_token) < 32:
        parser.error(f"{TOKEN_ENV} must be set to a secret of at least 32 characters")

    try:
        private_key_data = Path(args.private_key).read_bytes()
        signing_key = serialization.load_pem_private_key(
            private_key_data,
            password=None,
        )
    except (OSError, ValueError, TypeError) as exc:
        parser.error(f"cannot load transparency signing key: {exc}")
    if not isinstance(signing_key, Ed25519PrivateKey):
        parser.error("--private-key must contain an Ed25519 private key")

    log = WalletGovernanceTransparencyLog(
        args.database,
        log_id=args.log_id,
        signing_key=signing_key,
    )
    if args.public_key_output:
        log.export_public_key_pem(args.public_key_output)

    handler = make_wallet_governance_log_handler(
        log,
        bearer_token=bearer_token,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    server.daemon_threads = True
    print(
        f"Wallet governance transparency log '{args.log_id}' listening on "
        f"http://{args.host}:{args.port}{'/v1/wallet-governance/append'}"
    )
    print("Expose this loopback service only through a TLS-terminating reverse proxy.")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
