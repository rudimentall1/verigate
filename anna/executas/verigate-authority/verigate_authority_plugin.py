import asyncio
import hashlib
import json
import math
import os
import signal
import sys
import threading
import time
import tempfile
from pathlib import Path
from decimal import Decimal, InvalidOperation
import re

from cryptography.hazmat.primitives import serialization

if getattr(sys, "frozen", False):
    _BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    _SOURCE_REPO_ROOT = _BUNDLE_ROOT
    _DEFAULT_DATA_DIR = Path(sys.executable).resolve().parent / ".data"
else:
    _SOURCE_REPO_ROOT = Path(__file__).resolve().parents[3]
    _BUNDLE_ROOT = _SOURCE_REPO_ROOT
    _DEFAULT_DATA_DIR = Path(__file__).resolve().parent / ".data"

sys.path.insert(0, str(_SOURCE_REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from executa_sdk import (PROTOCOL_VERSION_V2, SamplingClient, SamplingError, StorageClient, StorageError, bind_invoke, get_current_invoke_id, make_response_router)
from executa_sdk.sampling import _write_frame

_sampling = SamplingClient()
_storage = StorageClient()
_route_response = make_response_router(_sampling, _storage)
_loop = None

VERSION = "0.1.17"
_POLICY_PATH = _BUNDLE_ROOT / "policies" / "anna.yaml"

# Anna Executa protocol 2.0: negotiate APS support in `initialize`; keep
# `describe` filesystem-free and declare parameters as a list of parameter objects.
MANIFEST = {
    "name": "verigate-authority",
    "display_name": "Verigate Authority",
    "version": VERSION,
    "description": (
        "Checks agent payment authority and can issue a capability-bound, one-time signed "
        "Execution Authorization for an external wallet or executor. Anna does not hold wallet "
        "keys or broadcast transactions; execution must pass through a Verigate enforcement adapter."
    ),
    "author": "rudimentall1",
    "homepage": "https://github.com/rudimentall1/verigate",
    "icon": "\U0001f6e1\ufe0f",
    "category": "security",
    "license": "MIT",
    # Required declaration for reverse host LLM Sampling; user grant is separate.
    "host_capabilities": ["llm.sample"],
    "tools": [
        {
            "name": "verigate_ai_review",
            "description": (
                "Ask the Anna host LLM to interpret a payment request or explain a Verigate decision. "
                "The Executa calls Anna through protocol-v2 sampling/createMessage; no provider API key "
                "is stored here. The response is advisory and never authorizes or executes an action."
            ),
            "timeout": 60,
            "parameters": [
                {"name": "system_prompt", "type": "string", "description": "Task-specific instruction for the advisory model call.", "required": True},
                {"name": "prompt", "type": "string", "description": "Untrusted request or decision context to review.", "required": True},
                {"name": "max_tokens", "type": "integer", "description": "Maximum response tokens (1-2048).", "required": False, "default": 1000}
            ],
        },
        {
            "name": "verigate_check",
            "description": (
                "Simulate a payment-shaped action against Verigate policy and return the signed "
                "ALLOW/WARN/BLOCK decision. This checks authority only; it does not submit, "
                "broadcast, or execute a payment, and it does not record anything."
            ),
            "timeout": 30,
            "parameters": [
                {"name": "agent_id", "type": "string", "description": "User-facing agent label only. It does not control identity, spend accounting or dynamic authority; those are bound to this installation issuer key.", "required": True},
                {"name": "payee", "type": "string", "description": "Recipient of the payment or action.", "required": True},
                {"name": "asset", "type": "string", "description": "Asset being moved, e.g. USDC.", "required": True},
                {"name": "network", "type": "string", "description": "Network the action runs on, e.g. base.", "required": True},
                {"name": "amount", "type": "number", "description": "Amount of the asset.", "required": True},
                {"name": "resource", "type": "string", "description": "Optional resource the action pays for.", "required": False, "default": ""},
                {"name": "ai_flags_json", "type": "string", "description": "Optional JSON array of AI risk flags [{code, message}]. Advisory only: flags can raise ALLOW to WARN but never lower a decision.", "required": False, "default": ""},
            ],
        },
        {
            "name": "verigate_policy_summary",
            "description": "Return active policy limits and this installation accounting principal. The optional agent_id is a display label only and never selects or resets accounting state. Read-only.",
            "timeout": 15,
            "parameters": [
                {"name": "agent_id", "type": "string", "description": "Optional display label; it does not select the accounting principal.", "required": False, "default": ""},
                {"name": "payee", "type": "string", "description": "Optional recipient for first-payment context.", "required": False, "default": ""},
                {"name": "asset", "type": "string", "description": "Optional asset for rolling spend context.", "required": False, "default": ""},
            ],
        },
        {
            "name": "verigate_authorize_payment",
            "description": (
                "After the user explicitly confirms the exact payment in the Anna UI, evaluate it "
                "with persistent Verigate policy and issue a capability-bound, one-time signed "
                "Execution Authorization for ALLOW. A WARN may be converted to ALLOW only after "
                "a separate, exact, one-time App UI warning review; BLOCK can never be overridden. "
                "The fresh policy result and dynamic authority are rechecked before issuance. This does "
                "not send funds. A wallet/executor must enforce the authorization through Verigate "
                "ExecutionRouter before any side effect."
            ),
            "timeout": 30,
            "parameters": [
                {"name": "agent_id", "type": "string", "description": "User-facing agent label only. Identity and limits are bound to this installation issuer key, not to this caller-supplied string.", "required": True},
                {"name": "payee", "type": "string", "description": "Exact payment recipient.", "required": True},
                {"name": "asset", "type": "string", "description": "Payment asset, e.g. USDC.", "required": True},
                {"name": "network", "type": "string", "description": "Exact network, e.g. base.", "required": True},
                {"name": "amount", "type": "number", "description": "Exact payment amount.", "required": True},
                {"name": "resource", "type": "string", "description": "Payment purpose or invoice reference.", "required": False, "default": ""},
                {"name": "ai_flags_json", "type": "string", "description": "Advisory AI risk flags. They may only escalate ALLOW to WARN.", "required": False, "default": ""},
                {"name": "confirmation_nonce", "type": "string", "description": "One-time nonce created by the Anna App UI after explicit user confirmation. Direct chat invocation has no app-scoped approval record and fails closed.", "required": True},
                {"name": "approval_kind", "type": "string", "description": "Use payment_authorization for ALLOW or payment_warning_review for a separate explicit review of the exact WARN rules.", "required": False, "default": "payment_authorization"}
            ]
        },
        {
            "name": "verigate_verify_execution_authorization",
            "description": "Read-only Ed25519 verification of a capability-bound one-time Execution Authorization. Returns the exact authorized action and expiry. Never consumes it.",
            "timeout": 15,
            "parameters": [
                {"name": "authorization_json", "type": "string", "description": "Complete Execution Authorization JSON object.", "required": True}
            ]
        },
        {
            "name": "verigate_consume_execution_authorization",
            "description": (
                "Verify and consume a one-time EVM USDC Execution Authorization through Verigate ExecutionRouter. "
                "Requires a fresh one-time App UI confirmation for the exact wallet submission. "
                "Returns the exact signed Base/Ethereum transaction envelope for a connected wallet to review and submit. "
                "This tool never signs or broadcasts; a consumed permission cannot be reused, including after wallet rejection."
            ),
            "timeout": 30,
            "parameters": [
                {"name": "authorization_json", "type": "string", "description": "Complete signed Execution Authorization JSON object.", "required": True},
                {"name": "confirmation_nonce", "type": "string", "description": "One-time nonce created by the Anna UI after the user confirms wallet submission.", "required": True},
            ],
        },
        {
            "name": "verigate_record_wallet_submission_receipt",
            "description": (
                "After the connected EIP-1193 wallet returns a transaction hash, persist a signed "
                "SUBMITTED ExecutionReceipt for the already-consumed authorization. Requires a "
                "separate one-time Anna App-scope approval bound to the exact wallet hash and "
                "transaction. This is executor self-report only, not on-chain confirmation."
            ),
            "timeout": 30,
            "parameters": [
                {"name": "authorization_id", "type": "string", "description": "ID of the previously issued and consumed Execution Authorization.", "required": True},
                {"name": "transaction_hash", "type": "string", "description": "Exact 32-byte transaction hash returned by the connected wallet.", "required": True},
                {"name": "sender", "type": "string", "description": "Connected wallet address used for this submission.", "required": True},
                {"name": "confirmation_nonce", "type": "string", "description": "One-time App UI approval created after the wallet returned the transaction hash.", "required": True}
            ],
        },
        {
            "name": "verigate_record_wallet_outcome_receipt",
            "description": (
                "Persist an Ed25519-signed Anna self-report for an already-consumed wallet authorization. "
                "REJECTED is accepted only for EIP-1193 error 4001; ABORTED is accepted only when the wallet "
                "request was not started or a lost Router response is proven consumed in the nonce ledger; "
                "UNKNOWN records an ambiguous eth_sendTransaction result. This is not wallet-signed evidence "
                "or independent chain confirmation. Requires a fresh exact App-scope approval."
            ),
            "timeout": 30,
            "parameters": [
                {"name": "authorization_id", "type": "string", "description": "Previously issued and Router-consumed authorization ID.", "required": True},
                {"name": "outcome", "type": "string", "description": "One of REJECTED, ABORTED or UNKNOWN.", "required": True},
                {"name": "phase", "type": "string", "description": "wallet_request, pre_wallet_request or router_response_unknown.", "required": True},
                {"name": "error_code", "type": "integer", "description": "EIP-1193 provider error code, or null when unavailable.", "required": False},
                {"name": "error_message", "type": "string", "description": "Bounded wallet/runtime error description observed by Anna.", "required": True},
                {"name": "sender", "type": "string", "description": "Connected EVM sender address, or empty when account access was unavailable.", "required": False, "default": ""},
                {"name": "confirmation_nonce", "type": "string", "description": "Fresh one-time App-scope approval for this exact wallet outcome.", "required": True}
            ],
        },
        {
            "name": "verigate_verify_decision_receipt",
            "description": (
                "Cryptographically verify a Verigate Decision Receipt using this installation's "
                "trusted Ed25519 issuer public key. Returns the verification result, SHA-256 key "
                "fingerprint and PEM public key for independent verification."
            ),
            "timeout": 15,
            "parameters": [
                {"name": "receipt_json", "type": "string", "description": "Complete Decision Receipt JSON object.", "required": True},
            ],
        },
    ],
}

_CHECK_TOOL = next(tool for tool in MANIFEST["tools"] if tool["name"] == "verigate_check")
_REQUIRED_ARGS = [
    parameter["name"]
    for parameter in _CHECK_TOOL["parameters"]
    if parameter["required"]
]


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _resolve_data_dir() -> Path:
    """Resolve durable state storage, preferring Anna's persistent workspace.

    VERIGATE_ANNA_DATA_DIR is an explicit operator override. On Anna Cloud
    Agents, ANNA_WORKSPACE_DIR is the platform's durable per-user volume
    contract; user data must not be stored beside the replaceable Executa
    installation. Both paths are authoritative and fail closed when unusable.
    Local-only fallbacks are evaluated lazily so a working default does not
    depend on HOME being configured.
    """
    override = os.environ.get("VERIGATE_ANNA_DATA_DIR")
    workspace = os.environ.get("ANNA_WORKSPACE_DIR")

    if override:
        candidates = [Path(override)]
        authoritative = True
    elif workspace:
        candidates = [Path(workspace) / "verigate-authority"]
        authoritative = True
    else:
        candidates = [_DEFAULT_DATA_DIR]
        authoritative = False

    errors = []
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return candidate
        except OSError as exc:
            errors.append(f"{candidate}: {exc}")
            if authoritative:
                break

    # These fallbacks are for local development only. Never use them when
    # Anna provides its durable workspace, because that would silently move
    # issuer identity and accounting history onto an ephemeral filesystem.
    if not authoritative:
        try:
            candidates = [Path.home() / ".verigate-authority"]
        except RuntimeError:
            candidates = []
        candidates.append(Path(tempfile.gettempdir()) / "verigate-authority")
        for candidate in candidates:
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                probe = candidate / ".write-test"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink()
                return candidate
            except OSError as exc:
                errors.append(f"{candidate}: {exc}")

    detail = "; ".join(errors) or "no candidate paths configured"
    raise RuntimeError(f"no writable Verigate data directory available: {detail}")


_state = None
_state_lock = threading.Lock()


def _get_state():
    """Initialize one issuer identity and SQLite engine exactly once per process."""
    global _state
    if _state is None:
        with _state_lock:
            if _state is None:
                from attest.keys import ensure_keypair
                from core.engine import GuardrailEngine
                from core.policy import Policy
                from core.storage import Storage

                data_dir = _resolve_data_dir()
                private_path = data_dir / "issuer.key"
                public_path = data_dir / "issuer.pub"
                private_key = ensure_keypair(private_path, public_path)
                engine = GuardrailEngine(
                    Policy.load(str(_POLICY_PATH)), Storage(str(data_dir / "verigate.db"))
                )
                _state = (engine, private_key)
    return _state


def _clean(text: object, limit: int) -> str:
    return " ".join(str(text).split())[:limit]


def _parse_ai_flags(raw: object) -> list:
    """Turn the optional AI flags into advisory WARN matches (at most 5)."""
    from core.models import RuleMatch, Severity

    if raw in (None, ""):
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError as exc:
        raise ValueError("ai_flags_json must be valid JSON") from exc
    if not isinstance(data, list):
        raise ValueError("ai_flags_json must be a JSON array")
    flags = []
    for item in data[:5]:
        if isinstance(item, dict):
            code, message = _clean(item.get("code", "other"), 32), _clean(item.get("message", ""), 200)
        elif isinstance(item, str):
            code, message = "other", _clean(item, 200)
        else:
            continue
        flags.append(RuleMatch("ai_risk_flag", Severity.WARN, f"AI review ({code or 'other'}): {message}".strip()))
    return flags


async def _verigate_ai_review(args: dict) -> dict:
    """Call the Anna host LLM through Executa reverse-RPC Sampling (v2)."""
    system_prompt = args.get("system_prompt")
    prompt = args.get("prompt")
    max_tokens = args.get("max_tokens", 1000)
    if not isinstance(system_prompt, str) or not system_prompt.strip() or len(system_prompt) > 8_000:
        return {"success": False, "error": "system_prompt must be a non-empty string no longer than 8000 characters"}
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 24_000:
        return {"success": False, "error": "prompt must be a non-empty string no longer than 24000 characters"}
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 1 <= max_tokens <= 2048:
        return {"success": False, "error": "max_tokens must be an integer from 1 to 2048"}

    try:
        response = await _sampling.create_message(
            messages=[{
                "role": "user",
                "content": {"type": "text", "text": prompt},
            }],
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            temperature=0.1,
            include_context="none",
            metadata={"executa_invoke_id": get_current_invoke_id(), "tool": "verigate_ai_review"},
            timeout=45.0,
        )
    except SamplingError as exc:
        return {
            "success": False,
            "error": {"code": exc.code, "message": exc.message},
            "llm_available": False,
        }

    content = response.get("content")
    if not isinstance(content, dict) or content.get("type") != "text" or not isinstance(content.get("text"), str):
        return {
            "success": False,
            "error": "Anna AI returned an unexpected response format from Anna Sampling",
            "llm_available": False,
            "malformed_response": True,
        }
    text = content["text"].strip()
    if not text:
        return {
            "success": False,
            "error": "Anna Sampling returned an empty response",
            "llm_available": False,
            "malformed_response": True,
        }
    return {
        "success": True,
        "data": {
            "text": text,
            "model": response.get("model"),
            "stop_reason": response.get("stopReason"),
            "usage": response.get("usage"),
        },
    }


def _anna_installation_principal(private_key) -> str:
    """Return the stable, non-secret accounting principal for this issuer installation."""
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return "anna-installation:" + hashlib.sha256(public_key).hexdigest()


def _verigate_check(args: dict) -> dict:
    for name in _REQUIRED_ARGS:
        if name not in args:
            raise RpcError(-32602, f"missing required argument: {name}")
    try:
        from core.models import PaymentIntent

        for name in ("agent_id", "payee", "asset", "network"):
            if not isinstance(args[name], str) or not args[name].strip():
                raise TypeError(f"{name} must be a non-empty string")
        amount = float(args["amount"])
        if not math.isfinite(amount):
            raise ValueError("amount must be a finite number")
        agent_label = _clean(args["agent_id"], 128)
        engine, private_key = _get_state()
        principal_id = _anna_installation_principal(private_key)
        intent = PaymentIntent(
            agent_id=principal_id,
            payee=args["payee"].strip(),
            asset=args["asset"].strip(),
            network=args["network"].strip(),
            amount=amount,
            resource=_clean(args.get("resource", ""), 200),
            metadata={
                "anna_agent_label": agent_label,
                "anna_accounting_scope": "issuer_installation",
            },
        )
        advisory = _parse_ai_flags(args.get("ai_flags_json"))
        # A check is a simulation: nothing is recorded, so the same request always
        # gets the same answer and repeated tests do not consume any budget.
        attestation = engine.authorize(intent, private_key, advisory=advisory, persist=False)
    except (ValueError, TypeError) as exc:
        return {"success": False, "error": f"invalid arguments: {exc}"}
    return {"success": True, "data": attestation}


def _anna_payment_capability_id(agent_id: str, policy) -> str:
    return "anna-payment-" + hashlib.sha256(
        f"{agent_id}:{policy.digest}".encode("utf-8")
    ).hexdigest()[:24]


def _verigate_policy_summary(args: dict) -> dict:
    engine, private_key = _get_state()
    p = engine.policy
    principal_id = _anna_installation_principal(private_key)
    capability_id = _anna_payment_capability_id(principal_id, p)
    authority = engine.authority_service.snapshot(
        principal_id,
        capability_id,
        persist=False,
    )
    dynamic_limits = {
        str(name).upper(): float(
            min(
                Decimal(str(limit)),
                Decimal(str(limit)) * Decimal(str(authority.multiplier)),
            )
        )
        for name, limit in (p.per_tx_cap or {}).items()
    }
    data = {
        "allowed_networks": p.allowed_networks,
        "allowed_assets": p.allowed_assets,
        "per_tx_cap": p.per_tx_cap,
        "new_payee_cap": p.new_payee_cap,
        "daily_cap": p.daily_cap,
        "rate_limit_per_minute": p.rate_limit_per_minute,
        "confirmation_required_over": p.confirmation_required_over,
        "payee_validation": p.payee_validation,
        "require_positive_amount": p.require_positive_amount,
        "preview_non_persistent": True,
        "history_recorded_for_preview": False,
        "history_used_for_limits": True,
        "authorization_records_history": True,
        "accounting_scope": "issuer_installation",
        "accounting_principal_id": principal_id,
        "dynamic_authority": {
            "state": authority.state.value,
            "multiplier": authority.multiplier,
            "per_action_limits": dynamic_limits,
            "successes": authority.successes,
            "adverse_events": authority.adverse_events,
            "critical_events": authority.critical_events,
            "reason": authority.reason,
        },
        "calls_last_minute": engine.storage.calls_last_minute(principal_id),
    }
    asset = args.get("asset")
    payee = args.get("payee")
    if isinstance(asset, str) and asset.strip():
        data["rolling_24h_spend"] = engine.storage.spent_today(principal_id, asset.strip().upper())
    if isinstance(payee, str) and payee.strip():
        data["recipient_seen_before"] = engine.storage.payee_seen_before(
            principal_id, payee.strip(), "__anna_policy_summary__"
        )
    return {"success": True, "data": data}


_EVM_USDC_NETWORKS = {
    "ethereum": {
        "chain_id": 1,
        "contract": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    },
    "base": {
        "chain_id": 8453,
        "contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    },
}


def _build_anna_evm_transaction(network: str, asset: str, payee: str, amount: object) -> dict | None:
    """Build a canonical native-USDC ERC-20 transfer envelope for supported EVM chains."""
    config = _EVM_USDC_NETWORKS.get(network.lower())
    if config is None or asset.upper() != "USDC":
        return None
    if not isinstance(payee, str) or re.fullmatch(r"0x[0-9a-fA-F]{40}", payee) is None:
        raise ValueError("EVM USDC wallet execution requires a 20-byte recipient address")
    try:
        units = Decimal(str(amount)) * Decimal(1_000_000)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("USDC amount must be a valid decimal") from exc
    if not units.is_finite() or units <= 0 or units != units.to_integral_value():
        raise ValueError("USDC amount must be positive and use no more than 6 decimal places")
    raw_amount = int(units)
    if raw_amount >= 2**256:
        raise ValueError("USDC amount exceeds the ERC-20 uint256 range")
    # transfer(address,uint256): selector + 32-byte recipient + 32-byte amount.
    calldata = (
        "0xa9059cbb"
        + payee[2:].lower().rjust(64, "0")
        + format(raw_amount, "064x")
    )
    return {
        "chain_id": config["chain_id"],
        "to": config["contract"],
        "value_wei": 0,
        "data": calldata,
    }


def _restore_execution_authorization_numbers(authorization: dict) -> dict:
    """Restore schema-defined floats lost when JSON.stringify turns 25.0 into 25."""
    payload = authorization.get("payload")
    if not isinstance(payload, dict):
        return authorization
    action = payload.get("action")
    if isinstance(action, dict):
        for field in ("amount", "timestamp"):
            value = action.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                action[field] = float(value)
    authority_state = payload.get("authority_state")
    if isinstance(authority_state, dict):
        for field in ("evaluated_at", "history_start_at", "multiplier"):
            value = authority_state.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                authority_state[field] = float(value)
    policy = payload.get("authority_policy")
    if isinstance(policy, dict):
        for field in ("probation_multiplier", "limited_multiplier", "standard_multiplier", "elevated_multiplier"):
            value = policy.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                policy[field] = float(value)
    effective = payload.get("effective_authority")
    if isinstance(effective, dict):
        value = effective.get("authority_multiplier")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            effective["authority_multiplier"] = float(value)
        limits = effective.get("per_action_limits")
        if isinstance(limits, dict):
            for asset, value in limits.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    limits[asset] = float(value)
    signed_policy = payload.get("signed_policy_version")
    if isinstance(signed_policy, dict) and isinstance(signed_policy.get("payload"), dict):
        value = signed_policy["payload"].get("created_at")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            signed_policy["payload"]["created_at"] = float(value)
    return authorization


async def _consume_app_approval(nonce: object, expected: dict) -> dict:
    """Read and atomically consume a short-lived approval from the owning App's APS scope."""
    if not isinstance(nonce, str) or re.fullmatch(r"[0-9a-f]{48}", nonce) is None:
        raise PermissionError("a valid one-time App UI confirmation nonce is required")
    key = f"verigate/approvals/{nonce}"
    record = await _storage.get(key, scope="app", timeout=10.0)
    if record.get("exists") is not True or not isinstance(record.get("value"), dict):
        raise PermissionError("no app-scoped UI approval exists for this invocation")
    approval = record["value"]
    if approval.get("nonce") != nonce or approval.get("version") != 1:
        raise PermissionError("UI approval nonce or version is invalid")
    for field, expected_value in expected.items():
        stored_value = approval.get(field)
        if isinstance(expected_value, (int, float)) and not isinstance(expected_value, bool):
            if isinstance(stored_value, bool) or not isinstance(stored_value, (int, float)) or float(stored_value) != float(expected_value):
                raise PermissionError(f"UI approval does not match {field}")
        elif stored_value != expected_value:
            raise PermissionError(f"UI approval does not match {field}")

    now_ms = int(time.time() * 1000)
    created_at_ms = approval.get("created_at_ms")
    expires_at_ms = approval.get("expires_at_ms")
    if (isinstance(created_at_ms, bool) or not isinstance(created_at_ms, int)
            or isinstance(expires_at_ms, bool) or not isinstance(expires_at_ms, int)
            or created_at_ms > now_ms + 5_000
            or expires_at_ms <= now_ms
            or expires_at_ms - created_at_ms > 60_000
            or now_ms - created_at_ms > 60_000):
        raise PermissionError("UI approval is expired or outside its 60-second validity window")

    etag = record.get("etag")
    if not isinstance(etag, str) or not etag:
        raise PermissionError("UI approval has no storage ETag; refusing non-atomic consumption")
    deleted = await _storage.delete(key, scope="app", if_match=etag, timeout=10.0)
    if deleted.get("deleted") is not True:
        raise PermissionError("UI approval could not be consumed exactly once")
    return approval


async def _consume_app_confirmation(
    args: dict,
    normalized: dict,
    *,
    approval_kind: str = "payment_authorization",
) -> dict:
    if approval_kind not in {"payment_authorization", "payment_warning_review"}:
        raise PermissionError("unsupported App UI approval kind")
    expected = {"kind": approval_kind, **normalized}
    return await _consume_app_approval(args.get("confirmation_nonce"), expected)


async def _consume_app_wallet_submission(args: dict, authorization: dict, action: dict, transaction: dict) -> dict:
    payload = authorization.get("payload") or {}
    expected = {
        "kind": "wallet_submission",
        "authorization_id": payload.get("authorization_id"),
        "agent_id": action.get("agent_id"),
        "target": action.get("target"),
        "asset": action.get("asset"),
        "network": action.get("network"),
        "amount": action.get("amount"),
        "resource": action.get("resource") or "",
        "chain_id": transaction.get("chain_id"),
        "to": transaction.get("to"),
        "value_wei": transaction.get("value_wei"),
        "data": transaction.get("data"),
    }
    return await _consume_app_approval(args.get("confirmation_nonce"), expected)


async def _verigate_authorize_payment(args: dict) -> dict:
    required = ("agent_id", "payee", "asset", "network", "amount", "confirmation_nonce")
    for name in required:
        if name not in args:
            raise RpcError(-32602, f"missing required argument: {name}")
    try:
        from core.capabilities import CapabilityRegistry
        from core.models import Capability, PaymentIntent

        for name in ("agent_id", "payee", "asset", "network"):
            if not isinstance(args[name], str) or not args[name].strip():
                raise ValueError(f"{name} must be a non-empty string")
        amount = float(args["amount"])
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("amount must be finite and greater than zero")

        normalized = {
            "agent_id": _clean(args["agent_id"], 128),
            "payee": _clean(args["payee"], 256),
            "asset": _clean(args["asset"], 12).upper(),
            "network": _clean(args["network"], 24).lower(),
            "amount": amount,
            "resource": _clean(args.get("resource", ""), 200),
        }
        # This is the security boundary: a client boolean is not proof of
        # human approval. The app-scoped, one-time record must be present and
        # atomically consumed before any persistent authorization is issued.
        approval_kind = args.get("approval_kind", "payment_authorization")
        if not isinstance(approval_kind, str):
            raise ValueError("approval_kind must be a string")
        approval = await _consume_app_confirmation(
            args,
            normalized,
            approval_kind=approval_kind,
        )
        advisory = _parse_ai_flags(args.get("ai_flags_json"))

        agent_label = normalized["agent_id"]
        asset = normalized["asset"]
        network = normalized["network"]
        payee = normalized["payee"]
        resource = normalized["resource"]

        engine, private_key = _get_state()
        # The editable App field is a display label, never an authorization
        # principal. Bind accounting, capability and dynamic authority to the
        # persistent issuer key so rotating labels cannot reset policy history.
        agent_id = _anna_installation_principal(private_key)
        policy = engine.policy
        capability_id = _anna_payment_capability_id(agent_id, policy)
        registry = CapabilityRegistry(engine.storage)
        existing = engine.storage.capability(capability_id)
        if existing is None:
            registry.register(Capability(
                capability_id=capability_id,
                agent_id=agent_id,
                allowed_actions=("payment",),
                allowed_targets=tuple(policy.allowed_payees or ()),
                allowed_networks=tuple(policy.allowed_networks or ()),
                allowed_assets=tuple(policy.allowed_assets or ()),
                max_per_action=dict(policy.per_tx_cap or {}),
                metadata={
                    "source": "anna-verigate-authority",
                    "policy_sha256": policy.digest,
                    "scope": "payment",
                },
            ))
        else:
            if existing.agent_id != agent_id or existing.metadata.get("policy_sha256") != policy.digest:
                raise PermissionError("stored capability does not match this agent and policy")
            registry.resolve(capability_id)  # revoked/inactive authority fails closed

        intent_metadata = {
            "anna_agent_label": agent_label,
            "anna_accounting_scope": "issuer_installation",
            "anna_user_confirmation": {
                "confirmed": True,
                "source": "anna-app-scoped-one-time-approval",
                "confirmed_at": approval["created_at_ms"] / 1000.0,
                "approval_nonce_sha256": hashlib.sha256(
                    args["confirmation_nonce"].encode("ascii")
                ).hexdigest(),
            },
        }
        evm_transaction = _build_anna_evm_transaction(network, asset, payee, args["amount"])
        if evm_transaction is not None:
            intent_metadata["evm_transaction"] = evm_transaction

        intent = PaymentIntent(
            agent_id=agent_id, payee=payee, asset=asset, network=network,
            amount=amount,
            resource=resource,
            metadata=intent_metadata,
        )
        if approval_kind == "payment_warning_review":
            reviewed_rule_ids = approval.get("reviewed_rule_ids")
            if (
                not isinstance(reviewed_rule_ids, list)
                or not reviewed_rule_ids
                or any(not isinstance(rule_id, str) or not rule_id for rule_id in reviewed_rule_ids)
                or len(set(reviewed_rule_ids)) != len(reviewed_rule_ids)
            ):
                raise PermissionError("App warning review does not contain a valid reviewed_rule_ids list")
            review_evidence = {
                "source": "anna-app-scoped-one-time-warning-review",
                "reviewed_rule_ids": sorted(reviewed_rule_ids),
                "confirmed_at": approval["created_at_ms"] / 1000.0,
                "approval_nonce_sha256": hashlib.sha256(
                    args["confirmation_nonce"].encode("ascii")
                ).hexdigest(),
            }
            artifacts = engine.authorize_with_capability_after_warning_review(
                intent,
                capability_id,
                private_key,
                review_evidence=review_evidence,
                advisory=advisory,
            )
        else:
            artifacts = engine.authorize_with_capability(
                intent, capability_id, private_key, advisory=advisory
            )
        decision = artifacts["decision_receipt"]["payload"]["decision"]["decision"]
        execution = artifacts.get("execution_authorization")
        if decision != "ALLOW" or execution is None:
            return {"success": True, "data": {
                **artifacts,
                "execution_authorization": None,
                "execution_status": "NOT_ISSUED",
                "reason": "Only ALLOW can receive execution authority. WARN requires review; BLOCK is denied.",
            }}
        return {"success": True, "data": {
            **artifacts,
            "execution_status": "ISSUED",
            "execution_model": "one_time_capability_bound",
            "execution_boundary": "ExecutionRouter",
            "transaction_submitted": False,
            "wallet_key_access": False,
            "capability_id": capability_id,
            "confirmation_source": "anna-app-scoped-one-time-approval",
        }}
    except StorageError as exc:
        return {"success": False, "error": f"app-scoped UI confirmation unavailable: {exc.message}"}
    except (ValueError, TypeError, PermissionError, LookupError) as exc:
        return {"success": False, "error": f"execution authorization not issued: {exc}"}

def _verigate_verify_execution_authorization(args: dict) -> dict:
    raw = args.get("authorization_json")
    if not isinstance(raw, str) or not raw.strip():
        return {"success": False, "error": "authorization_json must be a non-empty JSON string"}
    if len(raw) > 262_144:
        return {"success": False, "error": "authorization_json exceeds the 256 KiB limit"}
    try:
        authorization = json.loads(raw)
        if not isinstance(authorization, dict):
            raise ValueError("authorization_json must contain an object")

        # JavaScript JSON.stringify removes the distinction between integral
        # floats and integers (for example 25.0 becomes 25). Restore fields
        # whose signed schema defines them as floats before Ed25519 verification.
        payload = authorization.get("payload")
        if isinstance(payload, dict):
            action = payload.get("action")
            if isinstance(action, dict):
                for field in ("amount", "timestamp"):
                    value = action.get(field)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        action[field] = float(value)
            authority_state = payload.get("authority_state")
            if isinstance(authority_state, dict):
                for field in ("evaluated_at", "history_start_at", "multiplier"):
                    value = authority_state.get(field)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        authority_state[field] = float(value)
            policy = payload.get("authority_policy")
            if isinstance(policy, dict):
                for field in ("probation_multiplier", "limited_multiplier", "standard_multiplier", "elevated_multiplier"):
                    value = policy.get(field)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        policy[field] = float(value)
            effective = payload.get("effective_authority")
            if isinstance(effective, dict):
                for field in ("authority_multiplier",):
                    value = effective.get(field)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        effective[field] = float(value)
                limits = effective.get("per_action_limits")
                if isinstance(limits, dict):
                    for asset, value in limits.items():
                        if isinstance(value, (int, float)) and not isinstance(value, bool):
                            limits[asset] = float(value)
            signed_policy = payload.get("signed_policy_version")
            if isinstance(signed_policy, dict) and isinstance(signed_policy.get("payload"), dict):
                created_at = signed_policy["payload"].get("created_at")
                if isinstance(created_at, (int, float)) and not isinstance(created_at, bool):
                    signed_policy["payload"]["created_at"] = float(created_at)

        data_dir = _resolve_data_dir()
        from attest.keys import load_public_key
        from attest.receipt import verify_execution_authorization
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        public_key = load_public_key(data_dir / "issuer.pub")
        verified, reason = verify_execution_authorization(authorization, public_key)
        payload = authorization.get("payload") if isinstance(authorization.get("payload"), dict) else {}
        public_key_raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        return {"success": True, "data": {
            "verified": bool(verified),
            "reason": reason,
            "algorithm": "Ed25519",
            "key_fingerprint_sha256": hashlib.sha256(public_key_raw).hexdigest(),
            "authorization_id": payload.get("authorization_id"),
            "expires_at": payload.get("expires_at"),
            "action": payload.get("action") if verified else None,
            "verification_scope": "local_installation_issuer_key",
            "consumed": False,
            "transaction_submitted": False,
        }}
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        return {"success": False, "error": f"execution authorization verification unavailable: {exc}"}


async def _verigate_consume_execution_authorization(args: dict) -> dict:
    """Consume a signed EVM permission only after a one-time App UI send confirmation."""
    raw = args.get("authorization_json")
    if not isinstance(raw, str) or not raw.strip():
        return {"success": False, "error": "authorization_json must be a non-empty JSON string"}
    if not isinstance(args.get("confirmation_nonce"), str):
        return {"success": False, "error": "confirmation_nonce is required for App UI wallet approval"}
    if len(raw) > 262_144:
        return {"success": False, "error": "authorization_json exceeds the 256 KiB limit"}
    try:
        authorization = json.loads(raw)
        if not isinstance(authorization, dict):
            raise ValueError("authorization_json must contain an object")
        _restore_execution_authorization_numbers(authorization)
        payload = authorization.get("payload")
        action = payload.get("action") if isinstance(payload, dict) else None
        if not isinstance(action, dict):
            raise ValueError("authorization is missing the signed action")
        metadata = action.get("metadata")
        if not isinstance(metadata, dict) or not isinstance(metadata.get("evm_transaction"), dict):
            raise ValueError("wallet submission is currently enabled only for native USDC transfers on Base and Ethereum")
        if action.get("network") not in _EVM_USDC_NETWORKS or action.get("asset") != "USDC":
            raise ValueError("wallet submission is currently enabled only for native USDC transfers on Base and Ethereum")
        confirmed = metadata.get("anna_user_confirmation")
        if not isinstance(confirmed, dict) or confirmed.get("confirmed") is not True:
            raise ValueError("signed action has no explicit Anna UI confirmation")

        from attest.keys import load_public_key
        from enforcement.evm import EVMExecutionAdapter
        from enforcement.networks import NetworkRegistry
        from enforcement.router import ExecutionRouter

        # Independently reconstruct the expected transfer from the signed
        # payment fields. Do this before consuming the nonce so malformed or
        # inconsistent artifacts do not burn a valid permission.
        transaction = EVMExecutionAdapter._transaction(action)
        expected_transaction = _build_anna_evm_transaction(
            action["network"], action["asset"], action["target"], action["amount"]
        )
        if expected_transaction is None or transaction != expected_transaction:
            raise ValueError("signed EVM transaction does not exactly match the authorized USDC payment")
        expected_chain_id = _EVM_USDC_NETWORKS[action["network"]]["chain_id"]
        if transaction["chain_id"] != expected_chain_id:
            raise ValueError("signed EVM chain does not match the selected network")

        # The model may see the authorization JSON, but it cannot create the
        # short-lived app-scope approval written by the explicit wallet button.
        await _consume_app_wallet_submission(args, authorization, action, transaction)

        engine, _ = _get_state()
        public_key = load_public_key(_resolve_data_dir() / "issuer.pub")
        router = ExecutionRouter(NetworkRegistry(), engine.storage, public_key)
        consumed, reason = router.consume(authorization)
        if not consumed:
            raise PermissionError(reason)

        # Router has verified the signature, EVM adapter and one-time nonce.
        # Return only the exact adapter-normalized transaction envelope.
        return {"success": True, "data": {
            "authorization_id": payload.get("authorization_id"),
            "consumed": True,
            "execution_status": "CONSUMED_AWAITING_WALLET",
            "network": action["network"],
            "transaction": transaction,
            "wallet_submission_required": True,
            "transaction_submitted": False,
            "message": "ExecutionRouter consumed the one-time permission. The connected wallet must still review, sign and submit this exact transaction.",
        }}
    except (OSError, ValueError, TypeError, RuntimeError, PermissionError, LookupError, StorageError) as exc:
        return {"success": False, "error": f"wallet execution was not authorized: {exc}"}


async def _verigate_record_wallet_submission_receipt(args: dict) -> dict:
    """Persist a signed executor receipt after the Anna wallet returns a tx hash."""
    authorization_id = args.get("authorization_id")
    transaction_hash = args.get("transaction_hash")
    sender = args.get("sender")
    if not isinstance(authorization_id, str) or re.fullmatch(r"[0-9a-fA-F]{64}", authorization_id) is None:
        return {"success": False, "error": "authorization_id must be a 32-byte hex identifier"}
    if not isinstance(transaction_hash, str) or re.fullmatch(r"0x[0-9a-fA-F]{64}", transaction_hash) is None:
        return {"success": False, "error": "transaction_hash must be a 32-byte EVM transaction hash"}
    if not isinstance(sender, str) or re.fullmatch(r"0x[0-9a-fA-F]{40}", sender) is None:
        return {"success": False, "error": "sender must be a 20-byte EVM wallet address"}

    authorization_id = authorization_id.lower()
    transaction_hash = transaction_hash.lower()
    sender = sender.lower()
    try:
        from attest.keys import load_public_key
        from attest.receipt import (
            sign_execution_receipt,
            verify_execution_authorization,
            verify_execution_receipt,
        )
        from enforcement.evm import EVMExecutionAdapter

        engine, private_key = _get_state()
        stored = engine.storage.authorization_by_id(authorization_id)
        if not isinstance(stored, dict) or not isinstance(stored.get("execution_authorization"), dict):
            raise LookupError("stored Execution Authorization was not found")
        authorization = stored["execution_authorization"]
        payload = authorization.get("payload")
        if not isinstance(payload, dict) or payload.get("authorization_id") != authorization_id:
            raise PermissionError("stored Execution Authorization identity mismatch")

        # Receipt creation is allowed only after the real ExecutionRouter
        # consumed this exact one-time nonce. A caller-supplied authorization
        # or tx hash is never enough to establish that boundary.
        nonce_record = engine.storage.execution_nonce_by_authorization(
            authorization_id, payload.get("nonce", "")
        )
        if nonce_record is None:
            raise PermissionError("ExecutionRouter has not consumed this authorization")
        if (
            nonce_record.get("intent_id") != payload.get("intent_id")
            or nonce_record.get("agent_id") != payload.get("agent_id")
        ):
            raise PermissionError("consumed execution nonce does not match the stored authorization")
        consumed_at = nonce_record.get("consumed_at")
        if isinstance(consumed_at, bool) or not isinstance(consumed_at, (int, float)):
            raise PermissionError("consumed execution nonce has no valid timestamp")
        verification_time = int(consumed_at)
        issued_at = payload.get("issued_at")
        expires_at = payload.get("expires_at")
        if (
            isinstance(issued_at, bool) or not isinstance(issued_at, int)
            or isinstance(expires_at, bool) or not isinstance(expires_at, int)
            or verification_time < issued_at or verification_time > expires_at
        ):
            raise PermissionError("authorization was not consumed within its signed validity window")

        public_key = load_public_key(_resolve_data_dir() / "issuer.pub")
        valid, reason = verify_execution_authorization(
            authorization, public_key, verification_time=verification_time
        )
        if not valid:
            raise PermissionError(f"stored Execution Authorization is invalid: {reason}")

        action = payload.get("action")
        if not isinstance(action, dict):
            raise ValueError("stored authorization has no action")
        network = str(action.get("network") or "").lower()
        asset = str(action.get("asset") or "").upper()
        if network not in _EVM_USDC_NETWORKS or asset != "USDC":
            raise ValueError("wallet submission receipts are supported only for native USDC on Base and Ethereum")

        transaction = EVMExecutionAdapter._transaction(action)
        expected_transaction = _build_anna_evm_transaction(
            network, asset, action.get("target"), action.get("amount")
        )
        if expected_transaction is None or transaction != expected_transaction:
            raise ValueError("stored EVM transaction does not match the authorized USDC payment")
        if transaction.get("chain_id") != _EVM_USDC_NETWORKS[network]["chain_id"]:
            raise ValueError("stored EVM chain does not match the selected network")

        submission_data = {
            "source": "anna_eip1193_wallet",
            "sender": sender,
            "chain_id": transaction["chain_id"],
            "to": str(transaction["to"]).lower(),
            "value_wei": transaction["value_wei"],
            "calldata_sha256": hashlib.sha256(
                str(transaction["data"]).lower().encode("ascii")
            ).hexdigest(),
        }

        # Every call, including an idempotent receipt lookup, must originate
        # from a fresh App-scoped approval. This keeps the receipt tool out of
        # direct chat/agent context while allowing safe UI retries.
        approval = {
            "kind": "wallet_submission_receipt",
            "authorization_id": authorization_id,
            "transaction_hash": transaction_hash,
            "sender": sender,
            "network": network,
            "chain_id": transaction["chain_id"],
            "to": str(transaction["to"]).lower(),
            "value_wei": transaction["value_wei"],
            "data": str(transaction["data"]).lower(),
        }
        await _consume_app_approval(args.get("confirmation_nonce"), approval)

        # Idempotent retries return the already-signed receipt only when every
        # wallet-submission identifier matches. A different hash cannot replace it.
        existing = engine.storage.execution_receipt_by_authorization(authorization_id)
        if existing is not None:
            existing_valid, existing_reason = verify_execution_receipt(
                existing, public_key, authorization
            )
            if not existing_valid:
                raise PermissionError(f"stored execution receipt is invalid: {existing_reason}")
            if (
                existing.get("payload", {}).get("transaction_ref") != transaction_hash
                or existing.get("payload", {}).get("submission_data") != submission_data
            ):
                raise PermissionError("a different execution receipt is already recorded for this authorization")
            return {
                "success": True,
                "data": {
                    "authorization_id": authorization_id,
                    "execution_status": existing["payload"]["status"],
                    "transaction_submitted": True,
                    "transaction_hash": transaction_hash,
                    "execution_receipt": existing,
                    "receipt_verified": True,
                    "receipt_trust_scope": "executor_self_report",
                    "independent_chain_confirmation": False,
                    "idempotent": True,
                },
            }

        receipt = sign_execution_receipt(
            authorization,
            status="SUBMITTED",
            transaction_ref=transaction_hash,
            executor="anna-eip1193-wallet",
            private_key=private_key,
            submission_data=submission_data,
        ).as_dict()
        try:
            engine.storage.record_execution_receipt(receipt)
        except ValueError:
            # Another invocation may have won the unique authorization race.
            raced = engine.storage.execution_receipt_by_authorization(authorization_id)
            if raced is None:
                raise
            raced_valid, raced_reason = verify_execution_receipt(
                raced, public_key, authorization
            )
            if (
                not raced_valid
                or raced.get("payload", {}).get("transaction_ref") != transaction_hash
                or raced.get("payload", {}).get("submission_data") != submission_data
            ):
                raise PermissionError(
                    f"conflicting execution receipt won the persistence race: {raced_reason}"
                )
            receipt = raced

        receipt_valid, receipt_reason = verify_execution_receipt(
            receipt, public_key, authorization
        )
        if not receipt_valid:
            raise PermissionError(f"new execution receipt failed verification: {receipt_reason}")
        return {
            "success": True,
            "data": {
                "authorization_id": authorization_id,
                "execution_status": "SUBMITTED",
                "transaction_submitted": True,
                "transaction_hash": transaction_hash,
                "execution_receipt": receipt,
                "receipt_verified": True,
                "receipt_trust_scope": "executor_self_report",
                "independent_chain_confirmation": False,
                "idempotent": False,
            },
        }
    except StorageError as exc:
        return {"success": False, "error": f"execution receipt storage unavailable: {exc.message}"}
    except (OSError, KeyError, TypeError, ValueError, RuntimeError, PermissionError, LookupError) as exc:
        return {"success": False, "error": f"wallet submission receipt not recorded: {exc}"}



async def _verigate_record_wallet_outcome_receipt(args: dict) -> dict:
    """Record a signed, authorization-bound EIP-1193 outcome self-report."""
    authorization_id = args.get("authorization_id")
    outcome = args.get("outcome")
    phase = args.get("phase")
    error_code = args.get("error_code")
    error_message = args.get("error_message")
    sender = args.get("sender") or None

    if not isinstance(authorization_id, str) or re.fullmatch(r"[0-9a-fA-F]{64}", authorization_id) is None:
        return {"success": False, "error": "authorization_id must be a 32-byte hex identifier"}
    if outcome not in {"REJECTED", "ABORTED", "UNKNOWN"}:
        return {"success": False, "error": "outcome must be REJECTED, ABORTED or UNKNOWN"}
    if error_code is not None and (
        isinstance(error_code, bool) or not isinstance(error_code, int)
    ):
        return {"success": False, "error": "error_code must be an integer or null"}
    if not isinstance(error_message, str) or not error_message.strip() or len(error_message) > 500:
        return {"success": False, "error": "error_message must be 1-500 characters"}
    error_message = error_message.strip()
    if sender is not None:
        if not isinstance(sender, str) or re.fullmatch(r"0x[0-9a-fA-F]{40}", sender) is None:
            return {"success": False, "error": "sender must be a 20-byte EVM address or empty"}
        sender = sender.lower()

    if outcome == "REJECTED" and (phase != "wallet_request" or error_code != 4001):
        return {"success": False, "error": "REJECTED requires EIP-1193 error 4001 during eth_sendTransaction"}
    if outcome == "ABORTED" and phase not in {"pre_wallet_request", "router_response_unknown"}:
        return {"success": False, "error": "ABORTED requires a verified pre-wallet abort phase"}
    if outcome == "UNKNOWN" and (phase != "wallet_request" or error_code == 4001):
        return {"success": False, "error": "UNKNOWN requires an ambiguous eth_sendTransaction outcome, not a user rejection"}

    authorization_id = authorization_id.lower()
    try:
        from attest.keys import load_public_key
        from attest.receipt import (
            sign_execution_receipt,
            verify_execution_authorization,
            verify_execution_receipt,
        )
        from enforcement.evm import EVMExecutionAdapter

        engine, private_key = _get_state()
        stored = engine.storage.authorization_by_id(authorization_id)
        if not isinstance(stored, dict) or not isinstance(stored.get("execution_authorization"), dict):
            raise LookupError("stored Execution Authorization was not found")
        authorization = stored["execution_authorization"]
        payload = authorization.get("payload")
        if not isinstance(payload, dict) or payload.get("authorization_id") != authorization_id:
            raise PermissionError("stored Execution Authorization identity mismatch")

        # A negative receipt is valid only after ExecutionRouter consumed the
        # exact signed nonce. A caller-provided status or authorization ID is
        # insufficient to establish that boundary.
        nonce_record = engine.storage.execution_nonce_by_authorization(
            authorization_id, payload.get("nonce", "")
        )
        if nonce_record is None:
            raise PermissionError("ExecutionRouter has not consumed this authorization")
        if (
            nonce_record.get("intent_id") != payload.get("intent_id")
            or nonce_record.get("agent_id") != payload.get("agent_id")
        ):
            raise PermissionError("consumed execution nonce does not match the stored authorization")
        consumed_at = nonce_record.get("consumed_at")
        if isinstance(consumed_at, bool) or not isinstance(consumed_at, (int, float)):
            raise PermissionError("consumed execution nonce has no valid timestamp")
        verification_time = int(consumed_at)
        issued_at = payload.get("issued_at")
        expires_at = payload.get("expires_at")
        if (
            isinstance(issued_at, bool) or not isinstance(issued_at, int)
            or isinstance(expires_at, bool) or not isinstance(expires_at, int)
            or verification_time < issued_at or verification_time > expires_at
        ):
            raise PermissionError("authorization was not consumed within its signed validity window")

        public_key = load_public_key(_resolve_data_dir() / "issuer.pub")
        valid, reason = verify_execution_authorization(
            authorization, public_key, verification_time=verification_time
        )
        if not valid:
            raise PermissionError(f"stored Execution Authorization is invalid: {reason}")

        action = payload.get("action")
        if not isinstance(action, dict):
            raise ValueError("stored authorization has no action")
        network = str(action.get("network") or "").lower()
        asset = str(action.get("asset") or "").upper()
        if network not in _EVM_USDC_NETWORKS or asset != "USDC":
            raise ValueError("wallet outcome receipts are supported only for native USDC on Base and Ethereum")

        transaction = EVMExecutionAdapter._transaction(action)
        expected_transaction = _build_anna_evm_transaction(
            network, asset, action.get("target"), action.get("amount")
        )
        if expected_transaction is None or transaction != expected_transaction:
            raise ValueError("stored EVM transaction does not match the authorized USDC payment")
        if transaction.get("chain_id") != _EVM_USDC_NETWORKS[network]["chain_id"]:
            raise ValueError("stored EVM chain does not match the authorized network")

        submission_data = {
            "source": "anna_eip1193_wallet",
            "phase": phase,
            "error_code": error_code,
            "sender": sender,
            "network": network,
            "chain_id": transaction["chain_id"],
            "to": str(transaction["to"]).lower(),
            "value_wei": transaction["value_wei"],
            "calldata_sha256": hashlib.sha256(
                str(transaction["data"]).lower().encode("ascii")
            ).hexdigest(),
        }
        approval = {
            "kind": "wallet_outcome_receipt",
            "authorization_id": authorization_id,
            "outcome": outcome,
            "phase": phase,
            "error_code": error_code,
            "error_message": error_message,
            "sender": sender,
            "network": network,
            "chain_id": transaction["chain_id"],
            "to": str(transaction["to"]).lower(),
            "value_wei": transaction["value_wei"],
            "data": str(transaction["data"]).lower(),
        }
        await _consume_app_approval(args.get("confirmation_nonce"), approval)

        existing = engine.storage.execution_receipt_by_authorization(authorization_id)
        if existing is not None:
            existing_valid, existing_reason = verify_execution_receipt(
                existing, public_key, authorization
            )
            if not existing_valid:
                raise PermissionError(f"stored execution receipt is invalid: {existing_reason}")
            if (
                existing.get("payload", {}).get("status") != outcome
                or existing.get("payload", {}).get("transaction_ref") is not None
                or existing.get("payload", {}).get("submission_data") != submission_data
                or existing.get("payload", {}).get("error") != error_message
            ):
                raise PermissionError("a different execution outcome receipt is already recorded for this authorization")
            return {
                "success": True,
                "data": {
                    "authorization_id": authorization_id,
                    "execution_status": outcome,
                    "wallet_submission_recorded": False,
                    "transaction_submitted": False,
                    "execution_receipt": existing,
                    "receipt_verified": True,
                    "receipt_trust_scope": "wallet_outcome_self_report",
                    "independent_chain_confirmation": False,
                    "idempotent": True,
                },
            }

        receipt = sign_execution_receipt(
            authorization,
            status=outcome,
            transaction_ref=None,
            executor="anna-eip1193-wallet",
            private_key=private_key,
            error=error_message,
            submission_data=submission_data,
        ).as_dict()
        try:
            engine.storage.record_execution_receipt(receipt)
        except ValueError:
            raced = engine.storage.execution_receipt_by_authorization(authorization_id)
            if raced is None:
                raise
            raced_valid, raced_reason = verify_execution_receipt(
                raced, public_key, authorization
            )
            if (
                not raced_valid
                or raced.get("payload", {}).get("status") != outcome
                or raced.get("payload", {}).get("transaction_ref") is not None
                or raced.get("payload", {}).get("submission_data") != submission_data
                or raced.get("payload", {}).get("error") != error_message
            ):
                raise PermissionError(
                    f"conflicting execution outcome receipt won the persistence race: {raced_reason}"
                )
            receipt = raced

        receipt_valid, receipt_reason = verify_execution_receipt(
            receipt, public_key, authorization
        )
        if not receipt_valid:
            raise PermissionError(f"new execution outcome receipt failed verification: {receipt_reason}")
        return {
            "success": True,
            "data": {
                "authorization_id": authorization_id,
                "execution_status": outcome,
                "wallet_submission_recorded": False,
                "transaction_submitted": False,
                "execution_receipt": receipt,
                "receipt_verified": True,
                "receipt_trust_scope": "wallet_outcome_self_report",
                "independent_chain_confirmation": False,
                "idempotent": False,
            },
        }
    except StorageError as exc:
        return {"success": False, "error": f"execution outcome receipt storage unavailable: {exc.message}"}
    except (OSError, KeyError, TypeError, ValueError, RuntimeError, PermissionError, LookupError) as exc:
        return {"success": False, "error": f"wallet outcome receipt not recorded: {exc}"}


def _verigate_verify_decision_receipt(args: dict) -> dict:
    raw = args.get("receipt_json")
    if not isinstance(raw, str) or not raw.strip():
        return {"success": False, "error": "receipt_json must be a non-empty JSON string"}
    if len(raw) > 262_144:
        return {"success": False, "error": "receipt_json exceeds the 256 KiB limit"}
    try:
        receipt = json.loads(raw)
    except (ValueError, TypeError):
        return {"success": False, "error": "receipt_json is not valid JSON"}
    if not isinstance(receipt, dict):
        return {"success": False, "error": "receipt_json must contain a receipt object"}

    # JSON transports such as JavaScript JSON.stringify normalize integral
    # floats (25.0 -> 25). Restore the schema-defined float fields before
    # checking the Python-signed canonical payload. Without this step a valid
    # receipt would appear tampered after crossing the Anna host boundary.
    payload = receipt.get("payload")
    if isinstance(payload, dict):
        intent = payload.get("intent")
        if isinstance(intent, dict):
            for field in ("amount", "timestamp"):
                value = intent.get(field)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    intent[field] = float(value)
        decision = payload.get("decision")
        if isinstance(decision, dict):
            value = decision.get("evaluated_at")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                decision["evaluated_at"] = float(value)
        signed_policy = payload.get("signed_policy_version")
        if isinstance(signed_policy, dict) and isinstance(signed_policy.get("payload"), dict):
            policy_created = signed_policy["payload"].get("created_at")
            if isinstance(policy_created, (int, float)) and not isinstance(policy_created, bool):
                signed_policy["payload"]["created_at"] = float(policy_created)

    try:
        # Verification is read-only: it loads only the public trust anchor and
        # never creates, unlocks or reads the issuer's private signing key.
        data_dir = _resolve_data_dir()
        public_path = data_dir / "issuer.pub"
        from attest.keys import load_public_key
        from attest.receipt import verify_receipt
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        import hashlib

        public_key = load_public_key(public_path)
        verified, reason = verify_receipt(receipt, public_key)
        public_key_raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        public_key_pem = public_key.public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        ).decode("ascii")
        fingerprint = hashlib.sha256(public_key_raw).hexdigest()
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        return {"success": False, "error": f"receipt verification unavailable: {exc}"}

    return {
        "success": True,
        "data": {
            "verified": bool(verified),
            "reason": reason,
            "algorithm": "Ed25519",
            "key_fingerprint_sha256": fingerprint,
            "public_key_pem": public_key_pem,
            "verification_scope": "local_installation_issuer_key",
        },
    }


def _initialize_result(params: dict | None = None) -> dict:
    """Negotiate protocol v2 and explicitly advertise reverse-RPC clients."""
    params = params if isinstance(params, dict) else {}
    offered = params.get("protocolVersion") or PROTOCOL_VERSION_V2
    protocol = offered if offered in ("1.1", PROTOCOL_VERSION_V2) else PROTOCOL_VERSION_V2
    if protocol != PROTOCOL_VERSION_V2:
        reason = "Anna host did not negotiate Executa protocol 2.0; APS and Sampling are unavailable"
        _storage.disable(reason)
        _sampling.disable(reason)
    return {
        "protocolVersion": protocol,
        "serverInfo": {"name": MANIFEST["display_name"], "version": MANIFEST["version"]},
        "client_capabilities": (
            {"storage": {}, "sampling": {}} if protocol == PROTOCOL_VERSION_V2 else {}
        ),
        "capabilities": {},
    }


def handle(request: dict):
    method = request.get("method")
    params = request.get("params") or {}
    if method == "initialize":
        return _initialize_result(params)
    if method == "describe":
        return MANIFEST
    if method == "health":
        return {"status": "ready", "message": "", "details": {}}
    if method == "invoke":
        if not isinstance(params, dict) or "tool" not in params:
            raise RpcError(-32602, "invoke requires params.tool")
        return invoke(params["tool"], params.get("arguments") or {})
    raise RpcError(-32601, f"Unknown method: {method}")


def invoke(tool: str, args: dict) -> dict:
    if tool in (
        "verigate_authorize_payment",
        "verigate_consume_execution_authorization",
        "verigate_record_wallet_submission_receipt",
        "verigate_record_wallet_outcome_receipt",
    ):
        raise RpcError(-32603, "privileged execution methods must run through the async App-context approval gate")
    if tool == "verigate_ai_review":
        raise RpcError(-32603, "Anna AI review must use the async reverse-Sampling path")
    if tool not in (
        "verigate_ai_review",
        "verigate_check",
        "verigate_verify_execution_authorization",
        "verigate_consume_execution_authorization",
        "verigate_record_wallet_submission_receipt",
        "verigate_record_wallet_outcome_receipt",
        "verigate_policy_summary",
        "verigate_verify_decision_receipt",
    ):
        raise RpcError(-32601, f"Unknown tool: {tool}")
    if not isinstance(args, dict):
        raise RpcError(-32602, "arguments must be an object")
    if tool == "verigate_check":
        return _verigate_check(args)
    if tool == "verigate_verify_execution_authorization":
        return _verigate_verify_execution_authorization(args)
    if tool == "verigate_consume_execution_authorization":
        raise RpcError(-32603, "wallet submission must run through the async App-context approval gate")
    if tool == "verigate_record_wallet_submission_receipt":
        raise RpcError(-32603, "wallet submission receipts must run through the async App-context approval gate")
    if tool == "verigate_record_wallet_outcome_receipt":
        raise RpcError(-32603, "wallet outcome receipts must run through the async App-context approval gate")
    if tool == "verigate_policy_summary":
        return _verigate_policy_summary(args)
    return _verigate_verify_decision_receipt(args)


def _write(frame: dict) -> None:
    _write_frame(frame)


def _ok(req_id, result: dict) -> None:
    _write({"jsonrpc": "2.0", "id": req_id, "result": result})


def _err(req_id, code: int, message: str, data: dict | None = None) -> None:
    error = {"code": code, "message": message}
    if data:
        error["data"] = data
    _write({"jsonrpc": "2.0", "id": req_id, "error": error})


async def _handle_invoke(req_id, params: dict) -> None:
    tool = params.get("tool")
    args = params.get("arguments") or {}
    try:
        with bind_invoke(params):
            if tool == "verigate_ai_review":
                result = await _verigate_ai_review(args)
            elif tool == "verigate_authorize_payment":
                result = await _verigate_authorize_payment(args)
            elif tool == "verigate_consume_execution_authorization":
                result = await _verigate_consume_execution_authorization(args)
            elif tool == "verigate_record_wallet_submission_receipt":
                result = await _verigate_record_wallet_submission_receipt(args)
            elif tool == "verigate_record_wallet_outcome_receipt":
                result = await _verigate_record_wallet_outcome_receipt(args)
            else:
                result = await asyncio.to_thread(invoke, tool, args)
        _ok(req_id, result)
    except StorageError as exc:
        _err(req_id, exc.code, exc.message, exc.data)
    except RpcError as exc:
        _err(req_id, exc.code, exc.message)
    except Exception as exc:  # noqa: BLE001 - keep one invocation from killing the process
        _err(req_id, -32603, f"Internal error: {exc}")


def _handle_initialize(req_id, params: dict) -> None:
    _ok(req_id, _initialize_result(params))


def _stdin_loop() -> None:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            _err(None, -32700, "Parse error")
            continue
        if not isinstance(msg, dict):
            _err(None, -32600, "Invalid request")
            continue
        # Responses to our APS reverse-RPC requests are dispatched before
        # host-initiated requests are processed.
        if "method" not in msg and _route_response(msg):
            continue
        method = msg.get("method")
        req_id = msg.get("id")
        if method == "initialize":
            _handle_initialize(req_id, msg.get("params") or {})
        elif method == "notifications/initialized":
            continue
        elif method == "describe":
            _ok(req_id, MANIFEST)
        elif method == "health":
            _ok(req_id, {"status": "ready", "message": "", "details": {}})
        elif method == "shutdown":
            _ok(req_id, {})
            return
        elif method == "invoke":
            if _loop is None:
                _err(req_id, -32603, "event loop is not ready")
            else:
                asyncio.run_coroutine_threadsafe(
                    _handle_invoke(req_id, msg.get("params") or {}), _loop
                )
        else:
            _err(req_id, -32601, f"Unknown method: {method}")


async def _main() -> None:
    global _loop
    _loop = asyncio.get_running_loop()
    reader = threading.Thread(target=_stdin_loop, daemon=True)
    reader.start()
    while reader.is_alive():
        await asyncio.sleep(0.1)


def main() -> None:
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="strict", newline=None)
        sys.stdout.reconfigure(encoding="utf-8", errors="strict", newline="\n")
    except (AttributeError, ValueError):
        pass
    try:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    except (ValueError, OSError):
        pass
    asyncio.run(_main())


if __name__ == "__main__":
    main()
