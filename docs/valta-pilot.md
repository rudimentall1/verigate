# Valta × Verigate pilot

## Scope

This pilot places Verigate in front of Valta's OpenAI-compatible Chat
Completions proxy. It does not call Valta's wallet-spend endpoint, create a
wallet, move funds, deposit assets, or store an OpenAI provider key.

Valta remains responsible for its own Cap limits, freeze state, virtual-key
checks, and upstream OpenAI billing. Verigate adds an independent,
agent-identity-bound authorization for the exact request body.

The integration includes a Python execution adapter and an opt-in
Verigate API route:

`POST /v1/integrations/valta/chat/completions`

The route is disabled unless `VALTA_VIRTUAL_KEY` contains a Valta
`vk_live_...` virtual key. It is single-tenant only for this pilot and fails
closed when Verigate tenant-key mode is enabled until per-tenant Valta secret
isolation is implemented. The route and adapter run in the same trusted
process as Verigate's ExecutionRouter and SQLite storage. This is not yet a
hosted multi-tenant service.

## Request lifecycle

1. The agent creates an OpenAI Chat Completions request and a Valta run ID.
2. The action builder canonicalizes the request and hashes its exact UTF-8 JSON
   bytes into a Verigate ActionIntent.
3. The agent signs that intent with its registered Ed25519 identity.
4. The API reconstructs the same ActionIntent using the supplied intent ID
   and timestamp. The agent signature must match the exact request body.
5. GuardrailEngine.authorize_action() checks the policy, identity and
   registered capability. Only ALLOW can return an ExecutionAuthorization.
6. ExecutionRouter.execute() verifies the signed authorization, validates the
   Valta adapter binding, and consumes the one-time nonce.
7. Only after successful consumption does the adapter's private client send
   the exact request bytes covered by the authorization to Valta.

The Verigate authorization does not replace Valta's own spend policy. A
Verigate ALLOW can still be denied by Valta. Either system can stop the call.

## Security properties in this adapter

- Exact endpoint is fixed to https://valta.co/v1/chat/completions.
- Exact canonical request body is bound by SHA-256 into the signed action.
- The Valta run ID is bound into the action and sent as X-Valta-Run-Id.
- Streaming requests are rejected; this pilot supports non-streaming calls.
- The Valta virtual key is held only by the private client, not included in the
  signed action or request body.
- ExecutionRouter owns one-time nonce consumption.
- The adapter cannot consume or execute directly; callers must use
  ExecutionRouter.execute().
- The adapter owns the validated request bytes and ignores the router callback
  so a caller cannot validate one body and forward another.
- HTTP redirects are rejected so a Valta virtual key is not forwarded to a
  different origin.
- Requests are never retried automatically. A timeout after dispatch can
  leave the upstream outcome uncertain; the caller must reconcile before
  issuing another action.
- Tests use a fake Valta client. They do not call Valta or OpenAI.
- API tests cover authorized dispatch, changed-request rejection, policy
  blocking and fail-closed behavior when no virtual key is configured.

## API configuration

Set the Valta virtual key only in the process secret store or deployment
environment; never commit it:

~~~bash
export VALTA_VIRTUAL_KEY="vk_live_..."
export VALTA_PROXY_TIMEOUT_SECONDS="30"
~~~

The deployment must also follow the production API authentication, encrypted
issuer-key and signed-intent requirements in
`docs/security-configuration.md`.

The caller sends `agent_id`, `identity_id`, `capability_id`,
`agent_signature`, `intent_id`, `timestamp`, `run_id` and the
OpenAI-compatible `request` object. It constructs and signs the same
ActionIntent locally using `action_for_chat_completion()`. The server
reconstructs the action, rejects a mismatched signature or request body, and
requires a pre-registered active identity and a narrow capability.

The route returns the signed decision receipt and execution authorization
alongside the Valta response. WARN returns 409 without an upstream call;
BLOCK returns 403 without an upstream call. An upstream timeout returns 504
with `retry_allowed: false`: the one-time authorization has already been
consumed and the upstream result may be uncertain.

The route fails closed in tenant-key mode. A shared global Valta key is not
safe for multiple tenants; a per-tenant virtual-key mapping and secret-store
integration must be implemented before enabling this route in a multi-tenant
deployment.

## Run the tests

From the repository root:

~~~bash
PYTHONPATH=. python3 -m unittest tests.test_valta_proxy_adapter -v
~~~

The tests cover:

- ALLOW: a valid signed action reaches the fake Valta client only after
  execution authorization is consumed.
- DENY: a policy denial produces no execution authorization.
- REPLAY: the second use of an authorization is rejected and the client is
  called only once.
- TAMPER: changing the request body after authorization is rejected before
  the client is called.
- Invalid run IDs and streaming requests are rejected.

## Live Valta connection

ValtaProxyClient requires a Valta virtual key beginning with vk_live_. That
key is accepted only by Valta's proxy endpoint and must be supplied from a
secret manager or process environment at runtime. Do not commit it, place it
in a fixture, or include it in a Verigate ActionIntent.

Valta's current proxy documentation specifies
POST https://valta.co/v1/chat/completions, Bearer authentication, and the
X-Valta-Run-Id header. It also documents that streaming is unsupported and
that the proxy evaluates Valta's Cap/freeze controls before forwarding to
OpenAI.

Provider keys and virtual keys are live-mode only. An approved real proxy call
can incur usage on the account's OpenAI bill. Until Valta supplies an agreed
sandbox or dedicated test credentials and the operator explicitly authorizes a
billable request, run only the mocked tests above.

## Remaining work before the Valta handoff

- Confirm the exact Verigate deployment database and provision a dedicated
  agent identity plus a narrow capability for valta.chat_completions.
- Confirm whether Valta can provide a sandbox virtual key or a tightly capped
  pilot agent for one non-streaming request.
- Run one controlled ALLOW request and one Valta-side deny, then export the
  Verigate receipt and Valta audit receipt.
- Agree with Valta on the expected evidence bundle and report format.

This pilot adapter is a reference execution boundary, not proof of a live
Valta integration until the live request and both sides' records are verified.
