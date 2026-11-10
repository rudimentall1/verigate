"""Compatibility facade for the proof-profile validator registry."""
from __future__ import annotations

from typing import Any

from .authority_lifecycle import validate as validate_authority_lifecycle
from .common import validate_requirements
from .integrity import validate as validate_integrity
from .mcp_execution import validate as validate_mcp_execution
from .registry import PROFILE_VALIDATORS, ProfileValidatorRegistry


def validate_profile(payload: dict[str, Any], profile: str) -> tuple[bool, str]:
    """Validate a proof using the registered profile-specific semantics."""
    validator = PROFILE_VALIDATORS.get(profile)
    if validator is None:
        _spec, _nodes, _edges, error = validate_requirements(payload, profile)
        return False, error or f"unsupported proof profile: {profile}"
    return validator(payload, profile)


PROFILE_VALIDATORS.register("integrity", validate_integrity)
PROFILE_VALIDATORS.register("mcp_execution", validate_mcp_execution)
PROFILE_VALIDATORS.register("authority_lifecycle", validate_authority_lifecycle)
