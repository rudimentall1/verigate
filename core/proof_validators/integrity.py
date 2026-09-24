"""Integrity proof-profile semantics."""
from __future__ import annotations

from typing import Any

from .common import validate_requirements


def validate(payload: dict[str, Any], profile: str = "integrity") -> tuple[bool, str]:
    _spec, _node_types, _edges, error = validate_requirements(payload, profile)
    if error:
        return False, error
    return True, "proof profile satisfied"
