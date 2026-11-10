# External agent quickstart

This guide connects a Python agent to a Verigate API using the generic,
protocol-agnostic action authorization endpoints. It does not broadcast a
payment or connect to Arc.

## What this integration does

1. The agent signs an exact ActionIntent with its own Ed25519 key.
2. It submits the signed intent to POST /v1/actions/authorize.
3. Verigate checks the registered identity, capability and policy.
4. The client consumes the returned one-time execution authorization through
   POST /v1/execution/consume.
5. The agent may invoke the protected operation only when the response contains
   execute: true.

HTTP 200 alone is not permission. No execution authorization means no
execution. WARN, BLOCK, invalid signatures, expired authorizations, replay,
tampering, API errors and network failures must all fail closed.

## 1. Operator enrollment

The agent owner creates a dedicated key locally. The public identity and
capability must be registered by the Verigate operator before the agent can
receive executable authority. Use the operator-controlled identity and
capability registry; do not expose self-registration.

Set the runtime configuration:

~~~bash
export VERIGATE_AGENT_ID="my-agent-prod"
export VERIGATE_CAPABILITY_ID="my-agent-ticket-v1"
export VERIGATE_BASE_URL="https://verigate.example"
export VERIGATE_API_KEY="<operator-issued-api-key>"
export VERIGATE_AGENT_KEY="~/.config/verigate/my-agent.key"
~~~

The API key is sent as Authorization: Bearer. For tenant-scoped deployments,
also set VERIGATE_TENANT_ID; the client sends X-Verigate-Tenant.

## 2. Run the example

From the repository root, with project dependencies installed:

~~~bash
PYTHONPATH=. python examples/external-agent/agent.py
~~~

The example signs a harmless demo.create_ticket intent, requests
authorization, consumes the one-time permission and prints a local simulated
side effect only after execute: true. It does not call a real external tool.

## 3. Use the client in your agent

~~~python
from integrations.http_client import VerigateClient, VerigateError

client = VerigateClient(
    "https://verigate.example",
    api_key="operator-issued-api-key",
    tenant_id="tenant-a",  # omit for single-tenant deployments
    timeout=10,
)

try:
    result = client.authorize_and_consume(signed_action_request)
except VerigateError:
    # Fail closed: do not invoke the protected tool.
    raise

if result["authorized"] and result["consumption"].get("execute") is True:
    invoke_the_exact_action_bound_in_signed_action_request()
else:
    do_not_execute()
~~~

The client transports the signed request and authorization. It does not
create agent keys, enroll identities, define capabilities, hold issuer keys,
broadcast transactions, or execute the protected side effect. The integration
must bind the actual tool arguments to the signed intent and must not
substitute a different action after authorization.

## 4. Error handling and security requirements

- VerigateAPIError exposes status_code, detail and parsed response body.
  Treat all non-2xx responses as denial.
- VerigateTransportError indicates timeout, connection failure or an
  unreadable response. Do not fall back to unguarded execution.
- The client does not automatically retry authorization or consumption. A
  caller must not retry a side effect based only on an ambiguous network
  timeout; reconcile authorization state first.
- Never send an agent private key to the API. Never log API keys or private
  key material.
- The example's simulated action is not evidence of a production integration.
- Arc payment execution uses the dedicated Arc Authority Registry sequence and
  wallet client. Do not route Arc authorizations through generic
  /v1/execution/consume.

## 5. Verification

~~~bash
PYTHONPATH=. python -m unittest tests.test_agent_http_client -v
PYTHONPATH=. python examples/external-agent/agent.py
~~~

The HTTP client unit tests mock the network. They verify request paths,
authentication headers, payload envelopes, API error handling and fail-closed
transport behavior. They do not claim a live API or blockchain transaction.
