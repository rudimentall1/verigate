"""Explicit registry for proof-profile semantic validators."""
from __future__ import annotations

from typing import Any, Callable

Validator = Callable[[dict[str, Any], str], tuple[bool, str]]


class ProfileValidatorRegistry:
    """Maps portable proof-profile names to independent semantic validators."""

    def __init__(self) -> None:
        self._validators: dict[str, Validator] = {}

    def register(self, profile: str, validator: Validator) -> None:
        if not profile:
            raise ValueError("proof profile name must not be empty")
        if profile in self._validators:
            raise ValueError(f"proof profile validator already registered: {profile}")
        self._validators[profile] = validator

    def get(self, profile: str) -> Validator | None:
        return self._validators.get(profile)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._validators))


PROFILE_VALIDATORS = ProfileValidatorRegistry()
