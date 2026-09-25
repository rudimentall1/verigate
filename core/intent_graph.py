"""Genesis 2.0 Intent Graph.

An Intent Graph models an agent's consequential plan without turning the plan
itself into permission. Every side-effecting ActionIntent still requires its
own exact ExecutionAuthorization.

Graph:
    Goal -> Intent -> Sub-intent -> Action -> Dependency -> Consequence

The implementation is immutable and dependency-light so it can sit above the
existing ActionIntent model and execution adapters.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .models import ActionIntent


class IntentNodeType(str, Enum):
    GOAL = "GOAL"
    INTENT = "INTENT"
    SUB_INTENT = "SUB_INTENT"
    ACTION = "ACTION"
    CONSEQUENCE = "CONSEQUENCE"


class IntentRelation(str, Enum):
    CONTAINS = "CONTAINS"
    DEPENDS_ON = "DEPENDS_ON"
    PRODUCES = "PRODUCES"
    CAUSES = "CAUSES"


@dataclass(frozen=True)
class IntentNode:
    node_id: str
    node_type: IntentNodeType
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "label": self.label,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class IntentEdge:
    source_id: str
    relation: IntentRelation
    target_id: str

    def as_dict(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "relation": self.relation.value,
            "target_id": self.target_id,
        }


@dataclass(frozen=True)
class IntentGraph:
    graph_id: str
    nodes: tuple[IntentNode, ...] = ()
    edges: tuple[IntentEdge, ...] = ()
    version: int = 1

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "version": self.version,
            "nodes": [n.as_dict() for n in self.nodes],
            "edges": [e.as_dict() for e in self.edges],
        }

    def node(self, node_id: str) -> IntentNode:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        raise KeyError(f"unknown intent graph node: {node_id}")

    def actions(self) -> tuple[IntentNode, ...]:
        return tuple(n for n in self.nodes if n.node_type == IntentNodeType.ACTION)

    def dependencies_of(self, node_id: str) -> tuple[str, ...]:
        return tuple(
            e.target_id for e in self.edges
            if e.source_id == node_id and e.relation == IntentRelation.DEPENDS_ON
        )

    def validate(self) -> tuple[bool, tuple[str, ...]]:
        errors: list[str] = []
        ids = [n.node_id for n in self.nodes]
        if len(ids) != len(set(ids)):
            errors.append("intent graph contains duplicate node ids")
        node_ids = set(ids)
        for edge in self.edges:
            if edge.source_id not in node_ids or edge.target_id not in node_ids:
                errors.append("intent graph edge references unknown node")
        # Dependencies must be acyclic: a cycle would make an execution plan
        # semantically ambiguous and therefore unsafe to authorize as a graph.
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                errors.append("intent graph contains a dependency cycle")
                return
            if node_id in visited:
                return
            visiting.add(node_id)
            for dep in self.dependencies_of(node_id):
                visit(dep)
            visiting.remove(node_id)
            visited.add(node_id)

        for node in self.nodes:
            visit(node.node_id)
        return not errors, tuple(dict.fromkeys(errors))


class IntentGraphBuilder:
    """Small builder used to construct a validated immutable graph."""

    def __init__(self, graph_id: str):
        self.graph_id = graph_id
        self._nodes: dict[str, IntentNode] = {}
        self._edges: list[IntentEdge] = []

    def add_node(
        self,
        node_id: str,
        node_type: IntentNodeType,
        label: str,
        metadata: dict[str, Any] | None = None,
    ) -> "IntentGraphBuilder":
        if node_id in self._nodes:
            raise ValueError(f"duplicate intent graph node: {node_id}")
        self._nodes[node_id] = IntentNode(
            node_id=node_id,
            node_type=node_type,
            label=label,
            metadata=metadata or {},
        )
        return self

    def add_action(self, action: ActionIntent, label: str | None = None) -> "IntentGraphBuilder":
        return self.add_node(
            action.intent_id,
            IntentNodeType.ACTION,
            label or action.action_type,
            {"action_intent": action.as_dict(), "context_digest": action.context_digest},
        )

    def link(
        self,
        source_id: str,
        relation: IntentRelation,
        target_id: str,
    ) -> "IntentGraphBuilder":
        if source_id not in self._nodes or target_id not in self._nodes:
            raise KeyError("intent graph link references unknown node")
        self._edges.append(IntentEdge(source_id, relation, target_id))
        return self

    def build(self) -> IntentGraph:
        graph = IntentGraph(
            graph_id=self.graph_id,
            nodes=tuple(self._nodes.values()),
            edges=tuple(self._edges),
        )
        valid, errors = graph.validate()
        if not valid:
            raise ValueError("; ".join(errors))
        return graph
