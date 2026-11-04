# Valta × Verigate pilot

## Scope

This pilot places Verigate in front of Valta's OpenAI-compatible Chat
Completions proxy. It does not call Valta's wallet-spend endpoint, create a
wallet, move funds, deposit assets, or store an OpenAI provider key.

Valta remains responsible for its own Cap limits, freeze state, virtual-key
checks, and upstream OpenAI billing. Verigate adds an independent,
agent-identity-bound authorization for the exact request body.

The first implementation is a local Python execution adapter. It is designed
to run in the same trusted process as the Verigate ExecutionRouter and its
SQLite storage. It is not a new public API route and is not a hosted multi-
tenant deployment.

## Request lifecycle

1. The agent creates an OpenAI Chat Completions request and a Valta run ID.
2. The action builder canonicalizes the request and hashes its exact UTF-8 JSON
   bytes into a Verigate ActionIntent.
3. The agent signs that intent with its registered Ed25519 identity.
4. GuardrailEngine.authorize_action() checks the policy, identity and
   registered capability. Only ALLOW can return an ExecutionAuthorization.
5. ExecutionRouter.execute() verifies the signed authorization, validates the
   Valta adapter binding, and consumes the one-time nonce.
6. Only after successful consumption does the adapter's private client send
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
