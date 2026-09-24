#!/usr/bin/env python3
"""Offline verifier for a Verigate Evidence Manifest.

No Verigate server or database is required. The optional trusted issuer key
turns cryptographic integrity into explicit issuer trust.
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from core.evidence_manifest import verify_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a Verigate Evidence Manifest offline")
    parser.add_argument("manifest", type=Path, help="path to exported manifest JSON")
    parser.add_argument("--trusted-key", help="base64 Ed25519 issuer public key")
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "reason": f"cannot read manifest: {exc}"}, indent=2))
        return 2
    result = verify_manifest(manifest, args.trusted_key)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
