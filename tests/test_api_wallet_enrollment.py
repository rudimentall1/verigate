import base64
import hashlib
import json
import tempfile
import time
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from api import main
from core.governance import GovernanceMember, GovernancePolicy, governor_id
from core.wallet_enrollment import WalletEnrollmentService, installation_principal


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _approval(action, key, tag):
    payload = {
        "governance_version": 1,
        "action_digest": hashlib.sha256(_canonical(action)).hexdigest(),
        "governor_id": governor_id(key.public_key()),
        "role": "governor",
        "approval_id": f"{tag}-{action['action_id']}",
        "issued_at": time.time(), "expires_at": time.time() + 120,
        "nonce": f"{tag}-nonce-{action['action_id']}",
    }
    return {"payload": payload, "signature": base64.b64encode(key.sign(_canonical(payload))).decode(), "algorithm": "Ed25519"}


def _configure(tmp):
    root = Path(tmp)
    main.POLICY_PATH = str(root / "policy.yaml")
    main.DB_PATH = str(root / "api.db")
    main.PRIVATE_KEY_PATH = str(root / "issuer.key")
    main.PUBLIC_KEY_PATH = str(root / "issuer.pub")
    main.GOVERNANCE_PRIVATE_KEY_PATH = str(root / "gov.key")
    main.GOVERNANCE_PUBLIC_KEY_PATH = str(root / "gov.pub")
    main.GOVERNANCE_POLICY_PATH = str(root / "governance.json")
    Path(main.POLICY_PATH).write_text("allowed_networks: [base]\nallowed_assets: [USDC]\n", encoding="utf-8")


def test_wallet_enrollment_api_requires_multi_party_governance():
    with tempfile.TemporaryDirectory() as td:
        _configure(td)
        with TestClient(main.app) as client:
            issuer = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
            issuer_b64 = base64.b64encode(issuer).decode()
            action = WalletEnrollmentService.build_action(
                action="WALLET_ENROLL", reason="verified by operator",
                governance_policy_sha256="0" * 64, issuer_public_key_b64=issuer_b64,
                chain_id=8453, network="base", wallet_address="0x" + "a" * 40,
                min_confirmations=12,
            )
            response = client.post("/v1/governance/wallet-enrollments", json={"action": action, "approvals": []})
            assert response.status_code == 503
        main._storage.close()
        main._storage = main._engine = main._policy = None
        main._governance_policy = None


def test_wallet_enrollment_api_accepts_quorum_and_lists_wallet():
    with tempfile.TemporaryDirectory() as td:
        _configure(td)
        with TestClient(main.app) as client:
            gov1, gov2 = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
            policy = GovernancePolicy(
                policy_id="api-wallet-policy", version=1, threshold=2,
                members=(GovernanceMember.from_public_key(gov1.public_key(), "governor"), GovernanceMember.from_public_key(gov2.public_key(), "governor")),
                allowed_actions=("WALLET_ENROLL", "WALLET_REVOKE"),
            )
            main._governance_policy = policy
            issuer = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
            issuer_b64 = base64.b64encode(issuer).decode()
            action = WalletEnrollmentService.build_action(
                action="WALLET_ENROLL", reason="verified wallet control",
                governance_policy_sha256=policy.digest, issuer_public_key_b64=issuer_b64,
                chain_id=8453, network="base", wallet_address="0x" + "b" * 40,
                min_confirmations=15,
            )
            response = client.post("/v1/governance/wallet-enrollments", json={
                "action": action, "approvals": [_approval(action, gov1, "one"), _approval(action, gov2, "two")],
            })
            assert response.status_code == 200, response.text
            principal = installation_principal(issuer_b64)[0]
            listed = client.get(f"/v1/governance/wallet-enrollments/{principal}")
            assert listed.status_code == 200
            assert listed.json()["enrollments"][0]["wallet_address"] == "0x" + "b" * 40
            assert listed.json()["enrollments"][0]["min_confirmations"] == 15
        main._storage.close()
        main._storage = main._engine = main._policy = None
        main._governance_policy = None
