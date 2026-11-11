# Verigate Agent SDK: Arc

This is the framework-independent Python entry point for an agent that wants to request an Arc USDC payment authorization. Anna is not required.

## 1. Create a dedicated agent key

Keep this key on the agent host. Do not reuse Verigate's issuer key and do not copy the private key to the API server.

```python
from integrations.agent_sdk import load_or_create_agent_key, public_identity

key = load_or_create_agent_key("~/.config/my-agent/verigate-ed25519.key")
identity = public_identity(key, "my-agent-prod")
print(identity["identity_id"])
```

The key file is raw Ed25519 private-key material and is created with POSIX mode 0600. Existing files with group/other access are rejected.

## 2. Create a public enrollment package

```python
import json
import time
from pathlib import Path
from integrations.agent_sdk import build_arc_enrollment_package

package = build_arc_enrollment_package(
    key,
    agent_id="my-agent-prod",
    capability_id="my-agent-prod-arc-usdc-v1",
    allowed_targets=["0x2222222222222222222222222222222222222222"],
    max_per_action_usdc="25",
    expires_at=time.time() + 30 * 24 * 60 * 60,
)
Path("arc-enrollment.json").write_text(json.dumps(package, indent=2))
```

Transfer only `arc-enrollment.json` to the Verigate operator. On the API host, the operator reviews it and runs:

```bash
python scripts/enroll_agent_arc.py --package arc-enrollment.json
```

The operator uses the same `VERIGATE_DB` database as the running API. Never expose an unauthenticated HTTP self-registration endpoint.

## 3. Sign an exact Arc payment intent

```python
from integrations.agent_sdk import build_arc_payment_authorization_request

request = build_arc_payment_authorization_request(
    key,
    agent_id="my-agent-prod",
    identity_id=identity["identity_id"],
    capability_id="my-agent-prod-arc-usdc-v1",
    sender="0x1111111111111111111111111111111111111111",
    recipient="0x2222222222222222222222222222222222222222",
    amount_usdc="1.25",
    resource="invoice-123",
)
```

Send `request` to `POST /v1/integrations/arc/authorize`, with the API's normal authentication headers. The signed payload binds the exact recipient, amount, asset, network, sender and canonical Arc USDC transfer calldata.

## 4. Execute only through the Arc authority flow

Use `integrations/arc-client.mjs` from a wallet-enabled client to:
1. request authorization;
2. register the authorization on Arc;
3. confirm registration;
4. consume the authorization on Arc;
5. confirm consumption;
6. receive the exact payment transaction.

Payment broadcast remains a separate explicit wallet action. The client does not automatically send the payment.

## Scope

This SDK provides key handling, public enrollment package creation and signed Arc payment request construction. It does not register identities remotely, hold wallet keys, submit transactions, or bypass Verigate's operator-controlled capability registry.