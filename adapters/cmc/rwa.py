"""CoinMarketCap-backed RWA purchase evaluator.

CMC supplies market evidence; Verigate supplies deterministic policy,
decision receipts, and execution capabilities. CMC data never gets to bypass
the hard authorization boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from core.authorization import AuthorizationService
from core.models import ActionIntent, Decision, GuardrailDecision, RuleMatch, Severity

from .models import CmcRwaQuote


@dataclass(frozen=True)
class RwaPolicy:
    allowed_asset_types: tuple[str, ...] = (
        "stock",
        "commodity",
        "currency",
        "government_security",
        "etf",
        "real_estate",
    )
    require_tokenization: bool = True
    max_purchase_usd: float = 5_000.0
    max_volume_fraction: float = 0.01
    max_market_cap_fraction: float = 0.001
    require_tracked_issuer: bool = True
    max_issuer_price_spread_fraction: float = 0.02
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def digest(self) -> str:
        payload = {
            "allowed_asset_types": self.allowed_asset_types,
            "require_tokenization": self.require_tokenization,
            "max_purchase_usd": self.max_purchase_usd,
            "max_volume_fraction": self.max_volume_fraction,
            "max_market_cap_fraction": self.max_market_cap_fraction,
            "require_tracked_issuer": self.require_tracked_issuer,
            "max_issuer_price_spread_fraction": self.max_issuer_price_spread_fraction,
            "raw": self.raw,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


class RwaPurchaseEvaluator:
    """Turn CMC evidence and a proposed purchase into Verigate artifacts."""

    def __init__(self, policy: RwaPolicy | None = None):
        self.policy = policy or RwaPolicy()

    @staticmethod
    def load_policy(path: str | Path) -> RwaPolicy:
        with open(path, "r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        return RwaPolicy(
            allowed_asset_types=tuple(raw.get("allowed_asset_types") or RwaPolicy().allowed_asset_types),
            require_tokenization=bool(raw.get("require_tokenization", True)),
            max_purchase_usd=float(raw.get("max_purchase_usd", 5000.0)),
            max_volume_fraction=float(raw.get("max_volume_fraction", 0.01)),
            max_market_cap_fraction=float(raw.get("max_market_cap_fraction", 0.001)),
            require_tracked_issuer=bool(raw.get("require_tracked_issuer", True)),
            max_issuer_price_spread_fraction=float(raw.get("max_issuer_price_spread_fraction", 0.02)),
            raw=raw,
        )

    def build_action(
        self,
        quote: CmcRwaQuote,
        purchase_usd: float,
        *,
        settlement_network: str | None = None,
        evm_transaction: dict[str, Any] | None = None,
        agent_id: str = "rwa-agent",
    ) -> ActionIntent:
        metadata: dict[str, Any] = {
            "source": "coinmarketcap.rwa.v5",
            "rwa_id": quote.rwa_id,
            "asset_type": quote.asset_type,
            "cmc_evidence": quote.as_evidence(),
        }
        if evm_transaction is not None:
            metadata["evm_transaction"] = evm_transaction

        return ActionIntent(
            agent_id=agent_id,
            action_type="rwa.purchase",
            target=quote.symbol,
            resource=f"cmc:rwa:{quote.rwa_id}",
            amount=purchase_usd,
            asset="USD",
            network=settlement_network,
            metadata=metadata,
        )
    def evaluate(
        self,
        action: ActionIntent,
        quote: CmcRwaQuote,
        purchase_usd: float,
    ) -> GuardrailDecision:
        matches: list[RuleMatch] = []

        if quote.asset_type not in {item.lower() for item in self.policy.allowed_asset_types}:
            matches.append(
                RuleMatch(
                    "rwa_asset_type_not_allowed",
                    Severity.BLOCK,
                    f"RWA asset type '{quote.asset_type}' is not allowed",
                )
            )

        if self.policy.require_tokenization and not quote.has_tokens:
            matches.append(
                RuleMatch(
                    "rwa_not_tokenized",
                    Severity.BLOCK,
                    f"RWA '{quote.symbol}' has no tracked tokenization",
                )
            )

        if self.policy.require_tracked_issuer and quote.has_tokens and not quote.issuer_provenance:
            matches.append(
                RuleMatch(
                    "rwa_issuer_provenance_missing",
                    Severity.BLOCK,
                    "CMC tracked tokens have no issuer provenance",
                )
            )

        if quote.issuer_price_spread_fraction is not None and quote.issuer_price_spread_fraction > self.policy.max_issuer_price_spread_fraction:
            matches.append(
                RuleMatch(
                    "rwa_issuer_price_dispersion_high",
                    Severity.WARN,
                    "tokenized issuer prices are dispersed beyond the configured threshold",
                )
            )

        if purchase_usd <= 0:
            matches.append(
                RuleMatch("rwa_invalid_purchase_amount", Severity.BLOCK, "purchase amount must be positive")
            )
        elif purchase_usd > self.policy.max_purchase_usd:
            matches.append(
                RuleMatch(
                    "rwa_purchase_cap_exceeded",
                    Severity.BLOCK,
                    f"purchase {purchase_usd:.2f} USD exceeds cap {self.policy.max_purchase_usd:.2f} USD",
                )
            )

        if quote.tokenized_volume_24h is None or quote.tokenized_volume_24h <= 0:
            matches.append(
                RuleMatch(
                    "rwa_missing_liquidity_evidence",
                    Severity.BLOCK,
                    "CMC returned no positive tokenized 24h volume",
                )
            )
        elif purchase_usd / quote.tokenized_volume_24h > self.policy.max_volume_fraction:
            matches.append(
                RuleMatch(
                    "rwa_volume_fraction_high",
                    Severity.WARN,
                    "purchase is large relative to CMC tokenized 24h volume",
                )
            )

        if quote.tokenized_market_cap and quote.tokenized_market_cap > 0:
            if purchase_usd / quote.tokenized_market_cap > self.policy.max_market_cap_fraction:
                matches.append(
                    RuleMatch(
                        "rwa_market_cap_fraction_high",
                        Severity.WARN,
                        "purchase is large relative to CMC tokenized market cap",
                    )
                )

        if any(item.severity == Severity.BLOCK for item in matches):
            final = Decision.BLOCK
        elif matches:
            final = Decision.WARN
        else:
            final = Decision.ALLOW

        return GuardrailDecision(
            intent_id=action.intent_id,
            agent_id=action.agent_id,
            decision=final,
            matched_rules=tuple(matches),
        )

    def authorize_purchase(
        self,
        quote: CmcRwaQuote,
        purchase_usd: float,
        private_key: Any,
        *,
        agent_id: str = "rwa-agent",
        settlement_network: str | None = None,
        evm_transaction: dict[str, Any] | None = None,
        policy_digest: str | None = None,
    ) -> dict[str, Any]:
        action = self.build_action(
            quote,
            purchase_usd,
            settlement_network=settlement_network,
            evm_transaction=evm_transaction,
            agent_id=agent_id,
        )
        decision = self.evaluate(action, quote, purchase_usd)
        artifacts = AuthorizationService().issue(
            action,
            decision,
            policy_digest or self.policy.digest,
            private_key,
            nonce=action.intent_id,
        )
        return {
            "action": action.as_dict(),
            "decision": decision.as_dict(),
            **artifacts,
        }
