"""Genesis 2.0 lifecycle boundary over the existing Verigate runtime.

This module orchestrates existing authority, authorization, execution, outcome,
and evidence primitives. It does not create a second enforcement path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.engine import GuardrailEngine
from core.evidence import EvidenceGraph
from core.evidence_manifest import build_manifest, verify_manifest
from core.proof_engine import digest
from core.proof_package import build_proof_package
from core.outcome import OutcomeAttestationService
from core.authority_protocol import LifecycleStage
from enforcement.router import ExecutionRouter


@dataclass(frozen=True)
class GenesisLifecycleResult:
    authorization: dict[str, Any]
    execution_receipt: dict[str, Any] | None
    outcome: dict[str, Any] | None
    manifest: dict[str, Any] | None
    learning: dict[str, Any] | None
    stage: LifecycleStage

class GenesisLifecycle:
    """Single control-plane boundary for one consequential action.

    The lifecycle delegates security decisions to the proven runtime. Its job
    is to make the Genesis sequence explicit and fail closed between stages.
    """

    def __init__(
        self,
        engine: GuardrailEngine,
        router: ExecutionRouter,
        outcome_service: OutcomeAttestationService,
        evidence_graph: EvidenceGraph,
        proof_private_key: Ed25519PrivateKey,
    ):
        self.engine = engine
        self.router = router
        self.outcome_service = outcome_service
        self.evidence_graph = evidence_graph
        self.proof_private_key = proof_private_key
        self.stage = LifecycleStage.IDENTIFY
        self._authorization: dict[str, Any] | None = None
        self._receipt: dict[str, Any] | None = None
        self._outcome: dict[str, Any] | None = None
        self._manifest: dict[str, Any] | None = None
        self._learning: dict[str, Any] | None = None

    @property
    def authorization(self) -> dict[str, Any]:
        if self._authorization is None:
            raise RuntimeError("lifecycle has not reached AUTHORIZATION")
        return self._authorization

    @property
    def execution_receipt(self) -> dict[str, Any]:
        if self._receipt is None:
            raise RuntimeError("lifecycle has not reached EXECUTION")
        return self._receipt

    def authorize(
        self,
        action,
        capability_id: str,
        identity_id: str,
        agent_signature: str,
        private_key,
    ) -> dict[str, Any]:
        self.stage = LifecycleStage.PROPOSE
        artifacts = self.engine.authorize_action(
            action,
            capability_id,
            identity_id,
            agent_signature,
            private_key,
        )
        self._authorization = artifacts
        if artifacts.get("execution_authorization") is not None:
            self.stage = LifecycleStage.AUTHORIZE
        else:
            self.stage = LifecycleStage.DECIDE
        return artifacts

    def execute(
        self,
        broadcaster: Callable[[dict[str, Any]], Any],
        *,
        executor: str = "verigate",
    ) -> dict[str, Any]:
        authorization = self.authorization.get("execution_authorization")
        if authorization is None:
            raise PermissionError("lifecycle has no executable authorization")
        self.stage = LifecycleStage.ENFORCE
        receipt = self.router.execute_with_receipt(
            authorization,
            broadcaster,
            executor=executor,
        )
        self._receipt = receipt.as_dict()
        self.stage = LifecycleStage.OBSERVE
        return self._receipt

    def confirm(self, confirmation: dict[str, Any]) -> dict[str, Any]:
        updated = self.router.confirm_execution_receipt(
            self.execution_receipt,
            confirmation,
        )
        if updated is not None:
            self._receipt = updated.as_dict()
        self.stage = LifecycleStage.OBSERVE
        return self._receipt

    def observe(self, attestation: dict[str, Any]) -> dict[str, Any]:
        if self._receipt is None:
            raise RuntimeError("execution receipt is required before observation")
        self._outcome = self.outcome_service.verify_and_record(
            attestation,
            record_authority_event=False,
        )
        self.stage = LifecycleStage.PROVE
        return self._outcome

    def prove(self, *, proof_profile: str = "authority_lifecycle") -> dict[str, Any]:
        if self._outcome is None:
            raise RuntimeError("independent outcome observation is required before proof")
        if proof_profile == "authority_lifecycle" and self._learning is None:
            raise RuntimeError("authority lifecycle proof requires LEARN before PROVE")
        authorization_id = self.authorization["execution_authorization"]["payload"][
            "authorization_id"
        ]
        graph = self.evidence_graph.build(
            authorization_id,
            authority_snapshot_after=(
                self._learning.get("authority_snapshot")
                if self._learning is not None
                else None
            ),
        )
        manifest = build_manifest(
            graph,
            self.proof_private_key,
            proof_profile=proof_profile,
        )
        verification = verify_manifest(manifest)
        if not verification["valid"]:
            raise ValueError(f"Genesis proof verification failed: {verification['reason']}")
        self._manifest = manifest
        if self._learning is not None:
            self._learning["proof_manifest_sha256"] = digest(manifest)
        self.stage = LifecycleStage.PROVE
        return manifest

    def package(self) -> dict[str, Any]:
        """Export the completed lifecycle proof as one portable package."""
        if self._manifest is None:
            raise RuntimeError("proof manifest is required before packaging")
        if self._manifest["payload"].get("proof_profile") != "authority_lifecycle":
            raise RuntimeError("Genesis packaging requires an authority lifecycle proof")
        return build_proof_package(self._manifest)

    def learn(self) -> dict[str, Any]:
        """Feed only the independently verified outcome back into authority."""
        if self._outcome is None:
            raise RuntimeError("verified outcome is required before learning")
        if not self._outcome.get("valid"):
            raise PermissionError("unverified outcome cannot change authority")

        claim = self._outcome["claim"]
        attestation_type = self._outcome.get("attestation_type")
        receipt_payload = self.execution_receipt["payload"]
        capability_id = receipt_payload.get("capability_id")
        if not capability_id:
            raise ValueError("execution receipt has no capability binding")

        authority_service = self.engine.authority_service
        event = None
        if (
            claim["status"] in {"SUCCEEDED", "FAILED"}
            and attestation_type != "EXECUTOR_SELF_REPORT"
        ):
            event_type = (
                "EXECUTION_CONFIRMED"
                if claim["status"] == "SUCCEEDED"
                else "EXECUTION_FAILED"
            )
            event = authority_service.record_event(
                agent_id=claim["agent_id"],
                capability_id=capability_id,
                identity_id=receipt_payload.get("identity_id"),
                event_type=event_type,
                evidence_ref=claim["claim_id"],
                metadata={
                    "outcome_claim_id": claim["claim_id"],
                    "outcome_claim_sha256": self._outcome["claim_sha256"],
                    "outcome_attestation_id": self._outcome["attestation_id"],
                    "proof_profile": "authority_lifecycle",
                },
            )

        snapshot = authority_service.snapshot(
            claim["agent_id"], capability_id
        )
        learned_snapshot = snapshot.as_dict()
        if event is not None:
            learned_snapshot["source_event_id"] = event["event_id"]
        self._learning = {
            "valid": True,
            "authority_event": event,
            "authority_snapshot": learned_snapshot,
            "authority_snapshot_sha256": snapshot.digest,
            "proof_manifest_sha256": None,
        }
        self.stage = LifecycleStage.LEARN
        return self._learning

    def result(self) -> GenesisLifecycleResult:
        return GenesisLifecycleResult(
            authorization=self.authorization,
            execution_receipt=self._receipt,
            outcome=self._outcome,
            manifest=self._manifest,
            learning=self._learning,
            stage=self.stage,
        )
