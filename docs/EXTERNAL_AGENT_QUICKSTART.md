# External agent quickstart

Connect a Python agent to Verigate's protocol-agnostic action authorization API.
This example protects a tool call; it does not broadcast a payment or use Arc.

## Execution contract

1. The agent signs an exact ActionIntent with its own Ed25519 key.
2. It submits the signed intent to POST /v1/actions/authorize.
3. Verigate checks the registered identity, capability and policy.
4. The agent consumes the returned one-time authorization through
   POST /v1/execution/consume.
5. The protected tool may run only when the decision is ALLOW and consumption
   returns execute: true.

HTTP 200 alone is not permission. WARN, BLOCK, invalid signatures, expired
authorizations, replay, tampering, API errors and network failures must all
fail closed.

## 1. Create the agent key and public enrollment package

Run locally on the agent owner's machine. The private key stays on that
machine; only the public JSON package is transferred to the Verigate operator.

~~~python
import json
import time
from pathlib import Path
from integrations.agent_sdk import (
    build_agent_enrollment_package,
    load_or_create_agent_key,
)

agent_id = "my-agent-prod"
key = load_or_create_agent_key("~/.config/verigate/my-agent.key")
package = build_agent_enrollment_package(
    key,
    agent_id=agent_id,
    capability_id="my-agent-ticket-v1",
    allowed_actions=["mcp.tool.call"],
    allowed_targets=["demo.create_ticket"],
    allowed_resources=["ticket:demo-001"],
    allowed_purposes=["Create a low-risk demonstration ticket"],
    context_constraints={"environment": "sandbox"},
    expires_at=time.time() + 30 * 24 * 60 * 60,
)
Path("agent-enrollment.json").write_text(json.dumps(package, indent=2))
~~~

Review every capability field before approving it. Do not use wildcards or
broad targets for a production agent.

## 2. Operator approves and enrolls the agent

Transfer agent-enrollment.json to the Verigate API host. The operator reviews
the package and applies it to the exact database used by the running API:

~~~bash
python scripts/enroll_agent.py \
  --package agent-enrollment.json \
  --db "$VERIGATE_DB"
~~~

The command prints the registered identity and capability IDs. Enrollment is
operator-controlled; there is no unauthenticated self-registration endpoint.
The package contains public identity material only. The API service must be
restarted only if its deployment configuration requires it; enrollment writes
to the shared Verigate database.

## 3. Configure and run the example agent

~~~bash
export VERIGATE_AGENT_ID="my-agent-prod"
export VERIGATE_CAPABILITY_ID="my-agent-ticket-v1"
export VERIGATE_BASE_URL="https://verigate.example"
export VERIGATE_API_KEY="<operator-issued-api-key>"
export VERIGATE_AGENT_KEY="~/.config/verigate/my-agent.key"
# Optional for tenant-scoped deployments:
export VERIGATE_TENANT_ID="tenant-a"

PYTHONPATH=. python examples/external-agent/agent.py
~~~

The example signs the exact demo.create_ticket intent, requests
authorization, consumes the one-time permission and prints a local simulated
side effect only after execute: true. It does not call a real external tool.

## 4. Use the HTTP client in your own agent

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

The client sends Authorization: Bearer and X-Verigate-Tenant when configured.
It does not create issuer decisions, enroll identities, define capabilities,
hold issuer keys, broadcast transactions, or execute the protected side
effect. The integration must bind the actual tool arguments to the signed
intent and must not substitute a different action after authorization.

## 5. Failure handling and limitations

- VerigateAPIError exposes status_code, detail and the parsed response body.
  Treat every non-2xx response as denial.
- VerigateTransportError indicates timeout, connection failure or an
  unreadable response. Never fall back to unguarded execution.
- The client does not retry requests automatically. An ambiguous timeout
  during consumption must be reconciled before any side effect is retried.
- Never send an agent private key to the API. Never log API keys or private
  key material.
- The example's simulated action is not evidence of a production integration.
- Arc payment execution uses the dedicated Arc Authority Registry sequence
  and wallet client. Do not route Arc authorizations through generic
  /v1/execution/consume.

## 6. Verification

~~~bash
PYTHONPATH=. python -m unittest discover -s tests -p 'test_agent_http_client.py' -v
PYTHONPATH=. python -m unittest discover -s tests -p 'test_agent_enrollment.py' -v
PYTHONPATH=. python -m unittest discover -s tests -p 'test_external_agent_flow.py' -v
~~~

The HTTP client tests mock transport. The enrollment and external-flow tests
exercise the real local API and storage using temporary databases. They do
not claim a live API deployment or blockchain transaction.
