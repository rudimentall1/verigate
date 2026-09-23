"""Evidence Graph: cryptographic provenance for one consequential action."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from attest.receipt import (
    action_digest,
    verify_execution_authorization,
    verify_execution_receipt,
    verify_receipt,
)
from core.authority import AuthorityGraph
from core.authority_state import DynamicAuthorityService
from core.identity import verify_action_signature
from core.models import ActionIntent
from core.storage import Storage
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def _digest(value: Any) -> str:
    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _node(node_type: str, node_id: str, data: Any) -> dict[str, Any]:
    return {
        "type": node_type,
        "id": node_id,
        "sha256": _digest(data),
        "data": data,
    }


class EvidenceGraph:
    """Build a deterministic provenance subgraph from durable Verigate evidence."""

    def __init__(self, storage: Storage, public_key: Ed25519PublicKey):
        self.storage = storage
        self.public_key = public_key

    def build_by_intent(self, intent_id: str) -> dict[str, Any]:
        artifacts = self.storage.authorization_by_intent(intent_id)
        if artifacts is None:
            raise LookupError("authorization evidence not found")
        execution = artifacts.get("execution_authorization")
        if execution is not None:
            return self.build(execution["payload"]["authorization_id"])
        decision = artifacts["decision_receipt"]
        synthetic_id = _digest(decision)
        return self._build_artifacts(synthetic_id, artifacts)

    def build(self, authorization_id: str) -> dict[str, Any]:
        artifacts = self.storage.authorization_by_id(authorization_id)
        if artifacts is None:
            raise LookupError("authorization evidence not found")
        return self._build_artifacts(authorization_id, artifacts)

    def _build_artifacts(self, authorization_id: str, artifacts: dict) -> dict[str, Any]:
        decision = artifacts["decision_receipt"]
        execution = artifacts.get("execution_authorization")
        intent = decision["payload"]["intent"]
        agent_id = intent["agent_id"]
        intent_id = intent["intent_id"]

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        verification: dict[str, Any] = {}

        ok, reason = verify_receipt(decision, self.public_key)
        verification["decision_receipt"] = {"valid": ok, "reason": reason}
        nodes.append(_node("decision_receipt", decision["signature"], decision))

        audit = self.storage.audit_by_intent(intent_id)
        if audit is None:
            raise LookupError("intent audit evidence not found")
        nodes.append(_node("action_intent", intent_id, intent))
        nodes.append(_node("decision", intent_id, decision["payload"]["decision"]))
        edges.extend([
            {"from": f"action_intent:{intent_id}", "relation": "EVALUATED_AS", "to": f"decision:{intent_id}"},
            {"from": f"decision:{intent_id}", "relation": "PROVEN_BY", "to": f"decision_receipt:{decision['signature']}"},
        ])

        policy_sha256 = decision["payload"]["policy_sha256"]
        policy = self.storage.policy_version_by_sha(policy_sha256)
        if policy is not None:
            nodes.append(_node("policy_version", policy_sha256, policy))
            edges.append({"from": f"policy_version:{policy_sha256}", "relation": "GOVERNS", "to": f"decision:{intent_id}"})
        else:
            nodes.append(_node("policy_version", policy_sha256, {"policy_sha256": policy_sha256, "available": False}))
            edges.append({"from": f"policy_version:{policy_sha256}", "relation": "GOVERNS", "to": f"decision:{intent_id}"})

        identity_id = execution["payload"].get("identity_id") if execution else None
        capability_id = execution["payload"].get("capability_id") if execution else None
        if identity_id is not None:
            identity = self.storage.identity(identity_id)
            if identity is not None:
                agent_signature = artifacts.get("agent_signature")
                identity_data = {
                    "agent_id": identity.agent_id,
                    "identity_id": identity.key_id,
                    "identity_sha256": identity.digest,
                    "status": "ACTIVE" if self.storage.identity_is_active(identity_id) else "INACTIVE",
                }
                nodes.append(_node("identity", identity_id, identity_data))
                if isinstance(agent_signature, str) and agent_signature:
                    valid, reason = verify_action_signature(
                        ActionIntent(**intent),
                        identity_id,
                        agent_signature,
                        identity,
                    )
                    verification["agent_signature"] = {"valid": valid, "reason": reason}
                    signature_id = _digest({"identity_id": identity_id, "action": intent, "signature": agent_signature})
                    nodes.append(_node("agent_signature", signature_id, {"identity_id": identity_id, "action_sha256": action_digest(intent), "signature": agent_signature}))
                    edges.append({"from": f"agent_signature:{signature_id}", "relation": "AUTHENTICATES", "to": f"action_intent:{intent_id}"})
                edges.append({"from": f"identity:{identity_id}", "relation": "AUTHENTICATES", "to": f"action_intent:{intent_id}"})

        if capability_id is not None:
            capability = self.storage.capability(capability_id)
            if capability is not None:
                authority = AuthorityGraph(self.storage).authority_path(capability_id)
                for path_node in authority:
                    nodes.append(_node("capability", path_node["id"], path_node))
                    if path_node.get("delegated_from"):
                        edges.append({
                            "from": f"capability:{path_node['delegated_from']}",
                            "relation": "DELEGATES",
                            "to": f"capability:{path_node['id']}",
                        })
                edges.append({"from": f"capability:{capability_id}", "relation": "AUTHORIZES", "to": f"action_intent:{intent_id}"})

                dynamic = DynamicAuthorityService(self.storage).explain(
                    capability.agent_id,
                    capability.capability_id,
                )
                nodes.append(_node("authority_state", capability_id, dynamic))
                edges.append({"from": f"authority_state:{capability_id}", "relation": "CONSTRAINS", "to": f"action_intent:{intent_id}"})

        if execution is not None:
            execution_id = execution["payload"]["authorization_id"]
            ok, reason = verify_execution_authorization(execution, self.public_key)
            verification["execution_authorization"] = {"valid": ok, "reason": reason}
            nodes.append(_node("execution_authorization", execution_id, execution))
            edges.append({"from": f"decision:{intent_id}", "relation": "MINTS", "to": f"execution_authorization:{execution_id}"})

            receipt = self.storage.execution_receipt_by_authorization(execution_id)
            if receipt is not None:
                ok, reason = verify_execution_receipt(receipt, self.public_key, execution)
                verification["execution_receipt"] = {"valid": ok, "reason": reason}
                receipt_id = receipt["payload"]["receipt_id"]
                nodes.append(_node("execution_receipt", receipt_id, receipt))
                edges.append({"from": f"execution_authorization:{execution_id}", "relation": "PRODUCES", "to": f"execution_receipt:{receipt_id}"})

                if capability_id:
                    events = self.storage.authority_events(
                        agent_id=agent_id,
                        capability_id=capability_id,
                    )
                    for event in events:
                        if event["evidence_ref"] == receipt_id:
                            nodes.append(_node("authority_event", event["event_id"], event))
                            edges.append({"from": f"execution_receipt:{receipt_id}", "relation": "INFORMS", "to": f"authority_event:{event['event_id']}"})

        verification["action_digest"] = action_digest(intent)
        verification["audit_present"] = True
        verification["all_signed_artifacts_valid"] = all(item["valid"] for key, item in verification.items() if isinstance(item, dict) and "valid" in item)

        return {
            "authorization_id": authorization_id,
            "intent_id": intent_id,
            "agent_id": agent_id,
            "graph_version": 1,
            "nodes": nodes,
            "edges": edges,
            "verification": verification,
            "audit": audit,
        }
