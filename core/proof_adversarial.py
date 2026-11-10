"""Reusable adversarial mutation engine for portable Verigate proofs."""
from __future__ import annotations

import base64
import copy
from dataclasses import dataclass
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.evidence_manifest import canonical, digest, graph_root, verify_manifest


@dataclass(frozen=True)
class ProofMutation:
    mutation_id: str
    description: str
    apply: Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class MutationResult:
    mutation_id: str
    description: str
    rejected: bool
    reason: str


def _node(manifest: dict[str, Any], node_type: str) -> dict[str, Any]:
    matches = [n for n in manifest["payload"]["nodes"] if n["type"] == node_type]
    if len(matches) != 1:
        raise ValueError(f"mutation requires exactly one {node_type} node")
    return matches[0]


def _refresh_and_resign(manifest: dict[str, Any], private_key: Ed25519PrivateKey) -> None:
    payload = manifest["payload"]
    for node in payload["nodes"]:
        node["sha256"] = digest(node["data"])
    payload["root_digest"] = graph_root(payload)
    manifest["signature"] = base64.b64encode(private_key.sign(canonical(payload))).decode("ascii")


def default_mutations(profile: str) -> tuple[ProofMutation, ...]:
    """Return semantic mutations appropriate for a proof profile."""
    mutations: list[ProofMutation] = []
    if profile == "mcp_execution":
        mutations.extend([
            ProofMutation("MCP-TARGET-DRIFT", "change the authorized MCP target", lambda m: _node(m, "action_intent")["data"].update(target="tampered.tool")),
            ProofMutation("MCP-AUTH-ACTION-SWAP", "change the action inside the execution authorization", lambda m: _node(m, "execution_authorization")["data"]["payload"]["action"].update(target="tampered.tool")),
            ProofMutation("MCP-CLAIM-RECEIPT-SWAP", "replace the outcome claim's execution receipt digest", lambda m: _node(m, "outcome_claim")["data"].update(execution_receipt_sha256="0" * 64)),
            ProofMutation("MCP-SELF-REPORT", "replace independent attestation with executor self-report", lambda m: (_node(m, "outcome_attestation")["data"]["payload"].update(attestor_type="EXECUTOR_SELF_REPORT"), _node(m, "attestor_authority")["data"].update(attestor_type="EXECUTOR"))),
            ProofMutation("MCP-CONTEXT-DRIFT", "change declared execution context", lambda m: _node(m, "action_intent")["data"].setdefault("declared_context", {}).update(environment="staging")),
        ])
    elif profile == "authority_lifecycle":
        mutations.extend([
            ProofMutation("AUTH-POLICY-SWAP", "change the policy referenced by the decision receipt", lambda m: _node(m, "decision_receipt")["data"]["payload"].update(policy_sha256="f" * 64)),
            ProofMutation("AUTH-IDENTITY-SWAP", "change the identity bound to execution", lambda m: _node(m, "execution_authorization")["data"]["payload"].update(identity_id="tampered-identity")),
            ProofMutation("AUTH-CLAIM-SWAP", "change the claim referenced by the authority event", lambda m: _node(m, "authority_event")["data"].update(evidence_ref="tampered-claim")),
        ])
    else:
        mutations.append(ProofMutation("INTEGRITY-NODE-TAMPER", "modify a graph node", lambda m: m["payload"]["nodes"][0]["data"].update(_tampered=True)))
    return tuple(mutations)


def run(
    manifest: dict[str, Any],
    private_key: Ed25519PrivateKey,
    *,
    mutations: tuple[ProofMutation, ...] | None = None,
    verifier: Callable[[dict[str, Any]], dict[str, Any]] = verify_manifest,
) -> list[MutationResult]:
    profile = manifest.get("payload", {}).get("proof_profile", "integrity")
    selected = default_mutations(profile) if mutations is None else mutations
    results: list[MutationResult] = []
    for mutation in selected:
        candidate = copy.deepcopy(manifest)
        mutation.apply(candidate)
        _refresh_and_resign(candidate, private_key)
        verification = verifier(candidate)
        results.append(MutationResult(
            mutation_id=mutation.mutation_id,
            description=mutation.description,
            rejected=verification.get("valid") is False,
            reason=verification.get("reason", "unknown verification result"),
        ))
    return results


def assert_all_rejected(results: list[MutationResult]) -> None:
    failures = [r for r in results if not r.rejected]
    if failures:
        detail = "; ".join(f"{r.mutation_id}: {r.reason}" for r in failures)
        raise AssertionError("adversarial proof verification accepted mutation(s): " + detail)
