#!/usr/bin/env python3
"""Verigate CLI — check a payment intent against policy, sign the decision,
verify a signed decision independently, inspect agent history.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.sign import sign_decision
from attest.verify import verify_attestation
from core.engine import GuardrailEngine
from core.models import PaymentIntent
from core.policy import Policy
from core.storage import Storage
from core.offline_verifier import verify_proof
from core.proof_package import parse_proof_package, verify_proof_package

DEFAULT_POLICY = "policies/default.yaml"
DEFAULT_DB = "data/verigate.db"
DEFAULT_PRIV_KEY = "keys/issuer.key"
DEFAULT_PUB_KEY = "keys/issuer.pub"


def render_proof_report(result: dict) -> str:
    """Render a stable, human-readable proof report for developers and judges."""
    labels = {
        "package_integrity": "PACKAGE INTEGRITY",
        "manifest_integrity": "MANIFEST INTEGRITY",
        "trust_anchor": "TRUST ANCHOR",
        "issuer_signature": "ISSUER SIGNATURE",
        "graph_integrity": "GRAPH INTEGRITY",
        "authority_protocol": "AUTHORITY PROTOCOL",
        "execution_authorization": "AUTHORIZATION",
        "execution_receipt": "EXECUTION",
        "historical_authority": "HISTORICAL AUTHORITY",
        "outcome": "OUTCOME",
        "learning": "LEARNING",
        "post_learning_authority": "POST-LEARNING AUTHORITY",
        "authority_transition": "LEARNING / POST-AUTHORITY",
        "manifest": "CRYPTOGRAPHIC MANIFEST",
    }
    lines = [
        "VERIGATE AUTHORITY PROOF",
        f"Protocol: {result.get('proof_protocol', result.get('protocol', 'evidence-manifest'))}",
        "",
    ]
    if "package_valid" in result:
        lines.append(f"{'PACKAGE INTEGRITY':<28} {'PASS' if result['package_valid'] else 'FAIL'}")
    checks = result.get("checks", {})
    for key, check in checks.items():
        status = "PASS" if check.get("valid") else "FAIL"
        lines.append(f"{labels.get(key, key.upper()):<28} {status}")
    lines.extend([
        "",
        f"RESULT: {'VALID' if result.get('valid') else 'INVALID'}",
    ])
    if result.get("reason") and not result.get("valid"):
        lines.append(f"Reason: {result['reason']}")
    if result.get("root_digest"):
        lines.append(f"Root: {result['root_digest']}")
    return "\n".join(lines)


def cmd_keygen(args: argparse.Namespace) -> int:
    generate_keypair(args.private_key, args.public_key)
    print(f"Wrote {args.private_key} and {args.public_key}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    policy = Policy.load(args.policy)
    storage = Storage(args.db)
    engine = GuardrailEngine(policy, storage)

    intent = PaymentIntent(
        agent_id=args.agent,
        payee=args.payee,
        asset=args.asset,
        network=args.network,
        amount=args.amount,
        resource=args.resource or "",
    )
    decision = engine.evaluate(intent)

    signature_b64 = None
    output = decision.as_dict()
    if args.sign:
        priv = load_private_key(args.private_key)
        attestation = sign_decision(decision, priv)
        signature_b64 = attestation.signature_b64
        output = attestation.as_dict()
    if signature_b64 is not None:
        storage.update_signature(intent.intent_id, signature_b64)
    print(json.dumps(output, indent=2))
    storage.close()
    return {"ALLOW": 0, "WARN": 1, "BLOCK": 2}[decision.decision.value]


def cmd_verify(args: argparse.Namespace) -> int:
    raw_document = Path(args.attestation_file).read_bytes()
    try:
        document = json.loads(raw_document.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "reason": f"invalid JSON proof: {exc}"}, indent=2))
        return 1
    trusted = None
    if args.public_key and Path(args.public_key).exists():
        import base64
        from cryptography.hazmat.primitives import serialization
        trusted_key = load_public_key(args.public_key)
        trusted = base64.b64encode(
            trusted_key.public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        ).decode("ascii")

    if isinstance(document, dict) and "package" in document and "package_sha256" in document:
        result = verify_proof_package(raw_document, trusted_public_key_b64=trusted)
        print(render_proof_report(result) if args.format == "text" else json.dumps(result, indent=2))
        return 0 if result["valid"] else 1
    if isinstance(document, dict) and "payload" in document and "issuer_public_key_b64" in document:
        result = verify_proof(document, trusted_public_key_b64=trusted)
        print(render_proof_report(result) if args.format == "text" else json.dumps(result, indent=2))
        return 0 if result["valid"] else 1
    pub = load_public_key(args.public_key)
    ok, reason = verify_attestation(document, pub)
    print(json.dumps({"valid": ok, "reason": reason}, indent=2))
    return 0 if ok else 1


def cmd_history(args: argparse.Namespace) -> int:
    storage = Storage(args.db)
    rows = storage.history(args.agent, limit=args.limit)
    print(json.dumps(rows, indent=2))
    storage.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="verigate")
    sub = p.add_subparsers(dest="command", required=True)

    kg = sub.add_parser("keygen", help="generate an Ed25519 issuer keypair")
    kg.add_argument("--private-key", default=DEFAULT_PRIV_KEY)
    kg.add_argument("--public-key", default=DEFAULT_PUB_KEY)
    kg.set_defaults(func=cmd_keygen)

    ck = sub.add_parser("check", help="evaluate a payment intent against policy")
    ck.add_argument("--agent", required=True)
    ck.add_argument("--payee", required=True)
    ck.add_argument("--asset", required=True)
    ck.add_argument("--network", required=True)
    ck.add_argument("--amount", type=float, required=True)
    ck.add_argument("--resource", default="")
    ck.add_argument("--policy", default=DEFAULT_POLICY)
    ck.add_argument("--db", default=DEFAULT_DB)
    ck.add_argument("--sign", action="store_true", help="sign the decision (Ed25519)")
    ck.add_argument("--private-key", default=DEFAULT_PRIV_KEY)
    ck.set_defaults(func=cmd_check)

    vf = sub.add_parser("verify", help="independently verify a signed attestation or portable evidence proof")
    vf.add_argument("attestation_file", help="path to a signed attestation, evidence manifest, or self-contained proof package JSON")
    vf.add_argument("--public-key", default=DEFAULT_PUB_KEY)
    vf.add_argument("--format", choices=("json", "text"), default="json", help="verification report format")
    vf.set_defaults(func=cmd_verify)

    hi = sub.add_parser("history", help="show recent decisions for an agent")
    hi.add_argument("--agent", required=True)
    hi.add_argument("--db", default=DEFAULT_DB)
    hi.add_argument("--limit", type=int, default=20)
    hi.set_defaults(func=cmd_history)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

