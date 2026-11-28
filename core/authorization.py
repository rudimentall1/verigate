"""Dependency-inversion port for signed authorization artifact issuance.

The core engine depends on this narrow contract rather than importing the
attestation package. The concrete implementation lives in attest.authorization.
"""
from __future__ import annotations

from typing import Any, Protocol


class AuthorizationArtifactIssuer(Protocol):
    def issue(self, *args: Any, **kwargs: Any) -> dict[str, Any]: ...

    def issue_decision_receipt(self, *args: Any, **kwargs: Any) -> dict[str, Any]: ...
