"""Persistent Evidence Graph service.

Graph snapshots are immutable, content-addressed records of the provenance
view at a point in time. Rebuilding a graph does not mutate an older snapshot.
"""
from __future__ import annotations

import hashlib
import json
import uuid
import time
from typing import Any

from .evidence import EvidenceGraph
from .storage import Storage


def graph_sha256(graph: dict[str, Any]) -> str:
    canonical = json.dumps(graph, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class EvidenceGraphService:
    """Build, persist, retrieve and verify immutable evidence graph snapshots."""

    def __init__(self, storage: Storage, graph: EvidenceGraph):
        self.storage = storage
        self.graph = graph

    def snapshot(self, authorization_id: str) -> dict[str, Any]:
        graph = self.graph.build(authorization_id)
        # A snapshot is a point-in-time observation. Include its capture time so
        # repeated captures remain distinct immutable history entries even when
        # the underlying evidence has not changed.
        graph["snapshot_at"] = time.time()
        digest = graph_sha256(graph)
        snapshot = {
            "snapshot_id": f"egs-{uuid.uuid4().hex}",
            "authorization_id": authorization_id,
            "graph_sha256": digest,
            "graph": graph,
        }
        self.storage.record_evidence_graph_snapshot(snapshot)
        stored = self.storage.evidence_graph_snapshot(snapshot["snapshot_id"])
        if stored is None:
            raise RuntimeError("persisted evidence graph snapshot could not be reloaded")
        return stored

    @staticmethod
    def verify_snapshot(snapshot: dict[str, Any]) -> tuple[bool, str]:
        graph = snapshot.get("graph")
        expected = snapshot.get("graph_sha256")
        if not isinstance(graph, dict) or not isinstance(expected, str):
            return False, "snapshot is incomplete"
        actual = graph_sha256(graph)
        if actual != expected:
            return False, "graph digest mismatch"
        if snapshot.get("authorization_id") != graph.get("authorization_id"):
            return False, "authorization binding mismatch"
        return True, "valid"

    def latest(self, authorization_id: str) -> dict[str, Any] | None:
        rows = self.storage.evidence_graph_snapshots(authorization_id, limit=1)
        return rows[0] if rows else None

    def history(self, authorization_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return self.storage.evidence_graph_snapshots(authorization_id, limit=limit)
