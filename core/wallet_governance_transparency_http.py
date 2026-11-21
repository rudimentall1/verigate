"""Authenticated HTTP transport and reference endpoint for the wallet transparency log."""
from __future__ import annotations

import hmac
import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler
from typing import Any

from core.wallet_governance_transparency import WalletGovernanceTransparencyLog


WALLET_GOVERNANCE_APPEND_PATH = "/v1/wallet-governance/append"
WALLET_GOVERNANCE_BUNDLE_PATH = "/v1/wallet-governance/bundle"
WALLET_GOVERNANCE_HEALTH_PATH = "/healthz"
MAX_REQUEST_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 32 * 1_048_576


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the bearer credential to a redirect target.
        return None


class WalletGovernanceTransparencyHTTPTransport:
    """HTTP client implementing the dispatcher transport contract.

    Production URLs MUST use HTTPS. Plain HTTP is allowed only for loopback
    development/test endpoints. Redirects are disabled so Authorization is
    never forwarded to an unexpected host.
    """

    def __init__(
        self,
        base_url: str,
        *,
        bearer_token: str,
        timeout: float = 10.0,
        ssl_context: ssl.SSLContext | None = None,
    ):
        if not isinstance(base_url, str):
            raise ValueError("wallet transparency service URL is required")
        parsed = urllib.parse.urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("wallet transparency service URL must be an origin without path, query, or credentials")
        try:
            _ = parsed.port
        except ValueError:
            raise ValueError("wallet transparency service URL port is invalid") from None
        loopback_hosts = {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname.lower() in loopback_hosts
        ):
            raise ValueError("wallet transparency service requires HTTPS outside loopback")
        if (
            not isinstance(bearer_token, str)
            or len(bearer_token) < 32
            or any(ord(char) < 33 or ord(char) > 126 for char in bearer_token)
        ):
            raise ValueError(
                "wallet transparency bearer token must contain at least 32 printable ASCII characters"
            )
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not 0 < timeout <= 120
        ):
            raise ValueError("wallet transparency HTTP timeout must be between 0 and 120 seconds")

        self.url = base_url.rstrip("/") + WALLET_GOVERNANCE_APPEND_PATH
        self.bearer_token = bearer_token
        self.timeout = float(timeout)
        handlers: list[Any] = [_NoRedirect()]
        if ssl_context is not None:
            handlers.append(urllib.request.HTTPSHandler(context=ssl_context))
        self._opener = urllib.request.build_opener(*handlers)


    def fetch_bundle(self, installation_principal: str) -> dict[str, Any]:
        """Fetch the complete remote history for independent reconciliation."""
        if not isinstance(installation_principal, str) or not installation_principal:
            raise ValueError("wallet transparency installation principal is required")
        query = urllib.parse.urlencode({"installation_principal": installation_principal})
        request = urllib.request.Request(
            self.url.rsplit(WALLET_GOVERNANCE_APPEND_PATH, 1)[0]
            + WALLET_GOVERNANCE_BUNDLE_PATH + "?" + query,
            method="GET",
            headers={
                "Authorization": f"Bearer {self.bearer_token}",
                "Accept": "application/json",
            },
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise PermissionError(
                    f"wallet transparency service rejected authentication (HTTP {exc.code})"
                ) from None
            if exc.code == 404:
                raise LookupError("wallet transparency checkpoint not found") from None
            raise ConnectionError(
                f"wallet transparency service returned HTTP {exc.code}"
            ) from None
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, (socket.timeout, TimeoutError)):
                raise TimeoutError("wallet transparency service request timed out") from None
            raise ConnectionError("wallet transparency service is unavailable") from None

        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("wallet transparency service response exceeds the size limit")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ValueError("wallet transparency service returned invalid JSON") from None
        if not isinstance(result, dict):
            raise ValueError("wallet transparency service response must be a JSON object")
        return result

    def append_envelope(
        self,
        installation_principal: str,
        envelope: dict[str, Any],
    ) -> dict[str, Any]:
        body = json.dumps(
            {
                "installation_principal": installation_principal,
                "envelope": envelope,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        if len(body) > MAX_REQUEST_BYTES:
            raise ValueError("wallet transparency request exceeds the size limit")
        request = urllib.request.Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.bearer_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            try:
                error_body = exc.read(4096).decode("utf-8", errors="replace")
                error_data = json.loads(error_body) if error_body else {}
                message = error_data.get("error", "request rejected")
            except (ValueError, AttributeError):
                message = "request rejected"
            if exc.code in {401, 403}:
                raise PermissionError(
                    f"wallet transparency service rejected authentication (HTTP {exc.code})"
                ) from None
            if exc.code in {400, 409, 413, 415}:
                raise ValueError(
                    f"wallet transparency service rejected the event (HTTP {exc.code}): {message}"
                ) from None
            raise ConnectionError(
                f"wallet transparency service returned HTTP {exc.code}"
            ) from None
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, (socket.timeout, TimeoutError)):
                raise TimeoutError("wallet transparency service request timed out") from None
            raise ConnectionError("wallet transparency service is unavailable") from None

        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("wallet transparency service response exceeds the size limit")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ValueError("wallet transparency service returned invalid JSON") from None
        if not isinstance(result, dict):
            raise ValueError("wallet transparency service response must be a JSON object")
        return result


def make_wallet_governance_log_handler(
    log: WalletGovernanceTransparencyLog,
    *,
    bearer_token: str,
    previous_bearer_tokens: tuple[str, ...] = (),
) -> type[BaseHTTPRequestHandler]:
    """Create a stdlib HTTP handler for a separately run transparency-log process.

    Put this endpoint behind a TLS-terminating reverse proxy in production and
    bind the Python server to loopback. The handler serializes writes through
    one in-process lock; run one writer process per SQLite database.
    """
    if not isinstance(log, WalletGovernanceTransparencyLog):
        raise TypeError("wallet governance log writer is required")
    if not isinstance(previous_bearer_tokens, tuple):
        raise ValueError("previous wallet transparency bearer tokens must be a tuple")
    accepted_tokens = (bearer_token, *previous_bearer_tokens)
    for token in accepted_tokens:
        if (
            not isinstance(token, str)
            or len(token) < 32
            or any(ord(char) < 33 or ord(char) > 126 for char in token)
        ):
            raise ValueError(
                "wallet transparency bearer tokens must contain at least 32 printable ASCII characters"
            )
    if len(set(accepted_tokens)) != len(accepted_tokens):
        raise ValueError("wallet transparency bearer tokens must be unique")

    import threading

    writer_lock = threading.RLock()

    class WalletGovernanceLogRequestHandler(BaseHTTPRequestHandler):
        server_version = "VerigateWalletGovernanceLog/1"

        def setup(self) -> None:
            super().setup()
            # Bound slow headers and partial request bodies. The reverse proxy
            # should enforce its own stricter connection/read timeouts too.
            self.connection.settimeout(15.0)

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            data = json.dumps(
                payload, sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.path == WALLET_GOVERNANCE_HEALTH_PATH and not parsed.query:
                self._send_json(200, {"status": "ok"})
                return
            if parsed.path != WALLET_GOVERNANCE_BUNDLE_PATH:
                self._send_json(404, {"error": "not found"})
                return

            authorization = self.headers.get("Authorization", "")
            scheme, separator, supplied_token = authorization.partition(" ")
            token_matches = False
            if scheme.lower() == "bearer" and separator:
                for accepted_token in accepted_tokens:
                    token_matches |= hmac.compare_digest(supplied_token, accepted_token)
            if not token_matches:
                self._send_json(401, {"error": "unauthorized"})
                return

            try:
                query = urllib.parse.parse_qs(parsed.query, strict_parsing=True)
                principals = query.get("installation_principal", [])
                if len(principals) != 1 or len(query) != 1:
                    raise ValueError("one installation_principal query parameter is required")
                principal = principals[0]
                bundle = log.export_bundle(principal)
            except LookupError:
                self._send_json(404, {"error": "not found"})
                return
            except ValueError:
                self._send_json(400, {"error": "invalid installation_principal query"})
                return
            except Exception:
                self._send_json(503, {"error": "transparency log export failed"})
                return
            self._send_json(200, bundle)

        def do_POST(self) -> None:
            if self.path != WALLET_GOVERNANCE_APPEND_PATH:
                self._send_json(404, {"error": "not found"})
                return

            authorization = self.headers.get("Authorization", "")
            scheme, separator, supplied_token = authorization.partition(" ")
            if (
                scheme.lower() != "bearer"
                or not separator
            ):
                self._send_json(401, {"error": "unauthorized"})
                return

            # Compare every configured token; do not reveal which rotation slot
            # matched through short-circuit timing.
            token_matches = False
            for accepted_token in accepted_tokens:
                token_matches |= hmac.compare_digest(supplied_token, accepted_token)
            if not token_matches:
                self._send_json(401, {"error": "unauthorized"})
                return

            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self._send_json(415, {"error": "application/json is required"})
                return

            try:
                content_length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._send_json(411, {"error": "valid Content-Length is required"})
                return
            if content_length < 1:
                self._send_json(400, {"error": "request body is empty"})
                return
            if content_length > MAX_REQUEST_BYTES:
                self._send_json(413, {"error": "request body exceeds the size limit"})
                return

            try:
                raw = self.rfile.read(content_length)
                if len(raw) != content_length:
                    raise ValueError("request body is truncated")
                payload = json.loads(raw.decode("utf-8"))
            except socket.timeout:
                self._send_json(408, {"error": "request body timed out"})
                return
            except (UnicodeDecodeError, ValueError):
                self._send_json(400, {"error": "request body is invalid JSON"})
                return

            if (
                not isinstance(payload, dict)
                or not isinstance(payload.get("installation_principal"), str)
                or not isinstance(payload.get("envelope"), dict)
            ):
                self._send_json(400, {"error": "installation_principal and envelope are required"})
                return

            try:
                with writer_lock:
                    bundle = log.append_envelope(
                        payload["installation_principal"],
                        payload["envelope"],
                    )
            except ValueError as exc:
                self._send_json(409, {"error": str(exc)})
                return
            except Exception:
                # Do not expose database, filesystem, or signing-key internals.
                self._send_json(503, {"error": "transparency log append failed"})
                return

            self._send_json(200, bundle)

        def log_message(self, format: str, *args: Any) -> None:
            # Standard server logging contains request metadata but not headers
            # or bodies, so bearer tokens and signed envelopes are not emitted.
            super().log_message(format, *args)

    return WalletGovernanceLogRequestHandler
