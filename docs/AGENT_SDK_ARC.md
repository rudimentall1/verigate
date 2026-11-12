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

## 4. Browser-based wallet adapter (optional)

The optional `integrations/arc-client.mjs` helper is an EIP-1193/browser adapter. It is useful for interactive wallet demos, but it is not the primary autonomous-agent execution path. It assumes the browser wallet can access both the Registry issuer and agent executor accounts.

## Scope

This SDK provides key handling, public enrollment package creation and signed Arc payment request construction. It does not register identities remotely, hold wallet keys, submit transactions, or bypass Verigate's operator-controlled capability registry.

## 4. Execute headlessly from an autonomous agent

The Python SDK above signs the exact intent request. The execution path is a separate Node.js helper and does not require a browser, MetaMask, or an EIP-1193 provider.

The transaction roles are deliberately separate:

- **Registry issuer signer:** operator-controlled signer or restricted KMS/HSM adapter. It submits only the Registry registration transaction returned by Verigate.
- **Agent executor signer:** the agent's own EVM account. Its address must match the `from` address in the signed payment intent. It submits Registry consumption and the exact USDC payment.
- **Verigate API:** never receives either private key and never broadcasts a transaction.

Install ethers v6 in the agent runtime (or provide signer adapters with the same `getAddress()` and `sendTransaction(tx)` interface):

```bash
npm install ethers
```

Example:

```js
import { JsonRpcProvider, Wallet } from "ethers";
import { executeAuthorizedArcPayment } from "./integrations/arc-agent-executor.mjs";

// Load these from the agent platform's secret manager / signer service.
// Do not place private keys in prompts, agent context, or Verigate API config.
const provider = new JsonRpcProvider("https://rpc.mainnet.arc.io");
const issuerSigner = new Wallet(process.env.ARC_ISSUER_SIGNING_KEY, provider);
const agentSigner = new Wallet(process.env.AGENT_ARC_SIGNING_KEY, provider);

// request is built and Ed25519-signed by the Python agent SDK shown above.
const result = await executeAuthorizedArcPayment({
  provider,
  issuerSigner,
  agentSigner,
  apiBaseUrl: process.env.VERIGATE_API_URL,
  authorizationRequest: request,
  headers: { Authorization: `Bearer ${process.env.VERIGATE_API_KEY}` },
});

console.log({
  settled: result.settled,
  registration: result.registration_tx_hash,
  consumption: result.consume_tx_hash,
  payment: result.payment_tx_hash,
  settlement: result.payment_settlement,
});
```

For production, the issuer signer should be an isolated operator/KMS/HSM service restricted to the Registry registration call, not a raw issuer private key distributed to each agent. The agent's own signer must remain in its execution environment or an agent-scoped signing service.

The agent executor address is taken from the signed EVM payment envelope, registered on-chain as the authorization executor, and is the only address allowed to consume that authorization. The payment must use the same signed sender. The agent executor also needs the Arc native gas asset for transaction fees.

## Scope

This is a non-custodial agent execution path. It supports autonomous signing/broadcast by the agent's own signer while keeping Registry issuance under operator control. Verigate authorizes and independently verifies; the execution keys remain outside the Verigate API.
