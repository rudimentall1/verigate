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
from core.authority import AuthorityGraph, verify_delegation
from core.governance import GovernancePolicy, verify_authority_reset, verify_governance_quorum
from core.authority_state import DynamicAuthorityService
from core.identity import verify_action_signature
from core.models import ActionIntent
from core.outcome import OutcomeAttestationService, digest as outcome_digest
from core.policy_version import verify_policy_version
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

    def __init__(
        self,
        storage: Storage,
        public_key: Ed25519PublicKey,
        governance_public_key: Ed25519PublicKey | None = None,
    ):
        self.storage = storage
        self.public_key = public_key
        self.governance_public_key = governance_public_key

    def _add_governance_envelope(
        self,
        envelope: dict[str, Any],
        *,
        subject_type: str,
        subject_id: str,
        relation: str,
        verification: dict[str, Any],
        nodes: list[dict[str, Any]],
        edges: list[dict[str, str]],
    ) -> None:
        action = envelope.get("governance_action") or envelope.get("action")
        approvals = envelope.get("approvals") or []
        policy_data = envelope.get("governance_policy") or envelope.get("policy")
        if not isinstance(action, dict) or not isinstance(policy_data, dict):
            verification[f"governance:{subject_id}"] = {
                "valid": False,
                "reason": "governance envelope is incomplete",
            }
            return
        try:
            policy = GovernancePolicy.from_dict(policy_data)
            ok, reason = verify_governance_quorum(action, approvals, policy)
        except (TypeError, ValueError, KeyError) as exc:
            ok, reason = False, f"invalid governance envelope: {exc}"
        verification[f"governance:{action.get('action_id', subject_id)}"] = {
            "valid": ok,
            "reason": reason,
        }
        governance_policy_id = envelope.get("governance_policy_sha256") or policy.digest
        nodes.append(_node("governance_policy", governance_policy_id, policy_data))
        action_id = action.get("action_id", subject_id)
        nodes.append(_node("governance_action", action_id, action))
        edges.append({
            "from": f"governance_action:{action_id}",
            "relation": relation,
            "to": f"{subject_type}:{subject_id}",
        })
        edges.append({
            "from": f"governance_policy:{governance_policy_id}",
            "relation": "GOVERNS",
            "to": f"governance_action:{action_id}",
        })
        for approval in approvals:
            approval_id = approval.get("payload", {}).get("approval_id") or _digest(approval)
            nodes.append(_node("governance_approval", approval_id, approval))
            edges.append({
                "from": f"governance_approval:{approval_id}",
                "relation": "APPROVES",
                "to": f"governance_action:{action_id}",
            })

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
            governed = self.storage.governed_policy_change_by_sha(policy_sha256)
            if governed is not None:
                envelope = governed
                policy_ok, policy_reason = verify_policy_version(
                    envelope["policy_version"], self.public_key
                )
                verification[f"policy:{policy_sha256}"] = {
                    "valid": policy_ok,
                    "reason": policy_reason,
                }
                self._add_governance_envelope(
                    envelope,
                    subject_type="policy_version",
                    subject_id=policy_sha256,
                    relation="PUBLISHES",
                    verification=verification,
                    nodes=nodes,
                    edges=edges,
                )
                control = self.storage.policy_control(envelope["policy_version"]["payload"]["policy_id"])
                if control is not None:
                    nodes.append(_node("policy_control", envelope["policy_version"]["payload"]["policy_id"], control))
                    edges.append({
                        "from": f"policy_control:{envelope['policy_version']['payload']['policy_id']}",
                        "relation": "CONTROLS",
                        "to": f"policy_version:{policy_sha256}",
                    })
                for control_action in self.storage.policy_control_actions(
                    envelope["policy_version"]["payload"]["policy_id"]
                ):
                    control_envelope = control_action["envelope"]
                    action = control_envelope.get("governance_action", {})
                    current_sha = action.get("current_policy_sha256")
                    target_sha = action.get("target_policy_sha256")
                    if policy_sha256 not in {current_sha, target_sha}:
                        continue
                    self._add_governance_envelope(
                        control_envelope,
                        subject_type="policy_version",
                        subject_id=policy_sha256,
                        relation=(
                            "FREEZES"
                            if action.get("action") == "POLICY_FREEZE"
                            else "ROLLS_BACK_FROM" if current_sha == policy_sha256
                            else "ROLLS_BACK_TO"
                        ),
                        verification=verification,
                        nodes=nodes,
                        edges=edges,
                    )
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
                        delegation = self.storage.delegation_by_child(path_node["id"])
                        if delegation is None:
                            verification[f"delegation:{path_node['id']}"] = {
                                "valid": False,
                                "reason": "delegation signature evidence is missing",
                            }
                        else:
                            parent = self.storage.capability(path_node["delegated_from"])
                            child = self.storage.capability(path_node["id"])
                            delegator = self.storage.identity(delegation["delegator_identity_id"])
                            valid = False
                            reason = "delegation evidence is incomplete"
                            if parent is not None and child is not None and delegator is not None:
                                valid, reason = verify_delegation(
                                    parent.capability_id,
                                    child,
                                    delegation["delegator_identity_id"],
                                    delegation["delegation_signature"],
                                    delegator,
                                )
                            verification[f"delegation:{path_node['id']}"] = {
                                "valid": valid,
                                "reason": reason,
                            }
                            delegation_id = delegation["edge_id"]
                            nodes.append(_node("delegation", delegation_id, delegation))
                            edges.append({
                                "from": f"delegation:{delegation_id}",
                                "relation": "PROVES",
                                "to": f"capability:{path_node['id']}",
                            })
                edges.append({"from": f"capability:{capability_id}", "relation": "AUTHORIZES", "to": f"action_intent:{intent_id}"})

                historical_snapshot = None
                if execution is not None:
                    candidate = execution.get("payload", {}).get("authority_state")
                    if isinstance(candidate, dict):
                        historical_snapshot = candidate
                if historical_snapshot is not None:
                    nodes.append(_node("authority_state", capability_id, historical_snapshot))
                else:
                    dynamic = DynamicAuthorityService(self.storage).explain(
                        capability.agent_id,
                        capability.capability_id,
                    )
                    nodes.append(_node("authority_state", capability_id, dynamic))
                edges.append({"from": f"authority_state:{capability_id}", "relation": "CONSTRAINS", "to": f"action_intent:{intent_id}"})

                # The authority ledger is the cryptographically linked lifecycle
                # history behind the current dynamic authority state. Include the
                # chain itself in the evidence graph so a snapshot proves not only
                # the current state but also the integrity of its transition history.
                ledger = self.storage.authority_ledger(
                    capability.agent_id,
                    capability.capability_id,
                )
                ledger_ok, ledger_reason = self.storage.verify_authority_ledger(
                    capability.agent_id,
                    capability.capability_id,
                )
                ledger_id = f"{capability.agent_id}:{capability.capability_id}"
                ledger_data = {
                    "agent_id": capability.agent_id,
                    "capability_id": capability.capability_id,
                    "entries": ledger,
                }
                nodes.append(_node("authority_ledger", ledger_id, ledger_data))
                verification["authority_ledger"] = {
                    "valid": ledger_ok,
                    "reason": ledger_reason,
                    "entry_count": len(ledger),
                }
                edges.append({
                    "from": f"authority_ledger:{ledger_id}",
                    "relation": "PROVES_HISTORY_OF",
                    "to": f"authority_state:{capability_id}",
                })
                for entry in ledger:
                    entry_id = entry["event_id"]
                    nodes.append(_node("authority_ledger_entry", entry_id, entry))
                    edges.append({
                        "from": f"authority_ledger:{ledger_id}",
                        "relation": "CONTAINS",
                        "to": f"authority_ledger_entry:{entry_id}",
                    })
                    event_node_id = f"authority_event:{entry_id}"
                    if any(node["type"] == "authority_event" and node["id"] == entry_id for node in nodes):
                        edges.append({
                            "from": f"authority_ledger_entry:{entry_id}",
                            "relation": "PROVES",
                            "to": event_node_id,
                        })
                reset = None
                if historical_snapshot is not None:
                    evaluated_at = historical_snapshot.get("evaluated_at")
                    if isinstance(evaluated_at, (int, float)) and not isinstance(evaluated_at, bool):
                        reset = self.storage.latest_authority_reset_at(
                            capability.agent_id,
                            capability.capability_id,
                            float(evaluated_at),
                        )
                if reset is None:
                    reset = self.storage.latest_authority_reset(
                        capability.agent_id,
                        capability.capability_id,
                    )
                if reset is not None:
                    reset_payload = reset.get("payload", {})
                    reset_id = reset_payload.get("action_id") or reset_payload.get("reset_id") or _digest(reset)
                    reset_valid = False
                    reset_reason = "governance reset could not be verified"
                    if reset.get("approvals") and reset.get("policy"):
                        try:
                            reset_policy = GovernancePolicy.from_dict(reset["policy"])
                            reset_valid, reset_reason = verify_governance_quorum(
                                reset_payload,
                                reset["approvals"],
                                reset_policy,
                            )
                        except (TypeError, ValueError, KeyError) as exc:
                            reset_reason = f"invalid multiparty reset envelope: {exc}"
                    elif self.governance_public_key is not None:
                        reset_valid, reset_reason = verify_authority_reset(
                            reset,
                            self.governance_public_key,
                        )
                    verification[f"authority_reset:{reset_id}"] = {
                        "valid": reset_valid,
                        "reason": reset_reason,
                    }
                    nodes.append(_node("authority_reset", reset_id, reset))
                    edges.append({
                        "from": f"authority_reset:{reset_id}",
                        "relation": "RESETS",
                        "to": f"authority_state:{capability_id}",
                    })

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

                outcome_service = OutcomeAttestationService(
                    self.storage,
                    self.public_key,
                )
                for claim in self.storage.outcome_claims_by_authorization(execution_id):
                    claim_id = claim["claim_id"]
                    claim_sha256 = outcome_digest(claim)
                    nodes.append(_node("outcome_claim", claim_id, claim))
                    edges.append({
                        "from": f"execution_receipt:{receipt_id}",
                        "relation": "OBSERVED_BY",
                        "to": f"outcome_claim:{claim_id}",
                    })
                    for attestation in self.storage.outcome_attestations_by_claim(claim_id):
                        attestation_id = attestation["payload"]["attestation_id"]
                        attestor_id = attestation["payload"]["attestor_id"]
                        try:
                            outcome_check = outcome_service.verify_existing(attestation)
                            verification[f"outcome_attestation:{attestation_id}"] = {
                                "valid": True,
                                "reason": outcome_check["reason"],
                                "claim_sha256": claim_sha256,
                                "attestation_sha256": outcome_check["attestation_sha256"],
                                "attestor_type": attestation["payload"]["attestor_type"],
                            }
                        except (KeyError, TypeError, ValueError, PermissionError, LookupError) as exc:
                            verification[f"outcome_attestation:{attestation_id}"] = {
                                "valid": False,
                                "reason": str(exc),
                            }

                        attestor = self.storage.outcome_attestor(attestor_id)
                        if attestor is None:
                            verification[f"attestor:{attestor_id}"] = {
                                "valid": False,
                                "reason": "attestor registry entry is missing",
                            }
                        else:
                            if not any(
                                node["type"] == "attestor_authority"
                                and node["id"] == attestor_id
                                for node in nodes
                            ):
                                nodes.append(_node("attestor_authority", attestor_id, attestor))
                            edges.append({
                                "from": f"attestor_authority:{attestor_id}",
                                "relation": "AUTHORIZES",
                                "to": f"outcome_attestation:{attestation_id}",
                            })
                            governance_history = self.storage.attestor_governance_actions(attestor_id)
                            if not governance_history:
                                verification[f"attestor_governance:{attestor_id}"] = {
                                    "valid": True,
                                    "governed": False,
                                    "reason": "attestor uses explicitly permitted bootstrap authority",
                                }
                            for envelope in governance_history:
                                action = envelope.get("action", {})
                                action_id = action.get("action_id")
                                if not action_id:
                                    verification[f"attestor_governance:{attestor_id}"] = {
                                        "valid": False,
                                        "reason": "attestor governance action is missing action_id",
                                    }
                                    continue
                                if any(
                                    node["type"] == "governance_action"
                                    and node["id"] == action_id
                                    for node in nodes
                                ):
                                    continue
                                self._add_governance_envelope(
                                    envelope,
                                    subject_type="attestor_authority",
                                    subject_id=attestor_id,
                                    relation="GOVERNS",
                                    verification=verification,
                                    nodes=nodes,
                                    edges=edges,
                                )
                                edges.append({
                                    "from": f"attestor_authority:{attestor_id}",
                                    "relation": "DERIVED_FROM",
                                    "to": f"governance_action:{action_id}",
                                })

                        nodes.append(_node(
                            "outcome_attestation",
                            attestation_id,
                            attestation,
                        ))
                        edges.append({
                            "from": f"outcome_attestation:{attestation_id}",
                            "relation": "ATTESTS",
                            "to": f"outcome_claim:{claim_id}",
                        })
                    if capability_id:
                        for event in self.storage.authority_events(
                            agent_id=agent_id,
                            capability_id=capability_id,
                        ):
                            if event["evidence_ref"] == claim_id:
                                nodes.append(_node(
                                    "authority_event",
                                    event["event_id"],
                                    event,
                                ))
                                edges.append({
                                    "from": f"outcome_claim:{claim_id}",
                                    "relation": "INFORMS",
                                    "to": f"authority_event:{event['event_id']}",
                                })

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
