# Verigate Agent SDK: Arc Mainnet

This is the framework-independent path for an autonomous agent to request and execute an Arc USDC payment. Anna, MetaMask and a browser are not required.

## 1. Create a dedicated agent identity key

Keep the Ed25519 identity key in the agent's secret store. Do not reuse Verigate's issuer key or copy the agent identity key to the API server.

```python
from integrations.agent_sdk import load_or_create_agent_key, public_identity

key = load_or_create_agent_key("~/.config/my-agent/verigate-ed25519.key")
identity = public_identity(key, "my-agent-prod")
print(identity["identity_id"])
```

The raw key file is created with POSIX mode 0600. Existing files with group/other access are rejected.

## 2. Enroll the agent and its capability

Build a public-only enrollment package:

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

The operator uses the same `VERIGATE_DB` database as the API. Do not expose an unauthenticated HTTP self-registration endpoint.

## 3. Build and sign an exact payment intent

The agent signs the exact sender, recipient, amount, token, network and ERC-20 calldata:

```python
import json
from pathlib import Path
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
Path("arc-payment-request.json").write_text(json.dumps(request))
```

The request is sent to `POST /v1/integrations/arc/authorize` with the API's normal authentication headers. Verigate checks the Ed25519 signature, enrolled identity, capability, policy and exact Arc USDC transfer envelope.

## 4. Execute headlessly from the agent runtime

The primary executor is `integrations/arc-agent-executor.mjs`. It uses an ethers-compatible JSON-RPC provider and two separate signer interfaces. It does not require MetaMask, an EIP-1193 browser provider, or a manual confirmation for each transaction.

| Signer | Responsibility | Key ownership |
|---|---|---|
| Registry issuer signer | Submits the Registry registration transaction | Operator-controlled KMS/HSM or restricted signer service |
| Agent executor signer | Submits Registry consumption and the exact USDC payment | Agent's own runtime or agent-scoped signing service |
| Verigate API | Authorizes and verifies; never broadcasts | Holds neither EVM private key |

The issuer address is the Registry owner/authorized issuer. The per-payment executor is taken from the `from` address in the agent's signed EVM payment envelope and stored in the Registry. That executor alone can consume the authorization.

Install ethers v6 in the agent runtime:

```bash
npm install ethers
```

Headless orchestration:

```js
import { readFile } from "node:fs/promises";
import { JsonRpcProvider, Wallet } from "ethers";
import { executeAuthorizedArcPayment } from "./integrations/arc-agent-executor.mjs";

const request = JSON.parse(await readFile("arc-payment-request.json", "utf8"));
// Pin this PEM out-of-band for the expected Verigate tenant. Do not trust a
// public key fetched from the same API response path being authenticated.
const verigatePublicKey = await readFile(process.env.VERIGATE_PUBLIC_KEY_PATH, "utf8");
const provider = new JsonRpcProvider("https://rpc.mainnet.arc.io");

// Local/dev illustration only. For production, replace the issuer Wallet with
// a restricted KMS/HSM signer adapter that can submit only Registry registration.
const issuerSigner = new Wallet(process.env.ARC_ISSUER_SIGNING_KEY, provider);
const agentSigner = new Wallet(process.env.AGENT_ARC_SIGNING_KEY, provider);

const result = await executeAuthorizedArcPayment({
  provider,
  issuerSigner,
  agentSigner,
  apiBaseUrl: process.env.VERIGATE_API_URL,
  authorizationRequest: request,
  verigatePublicKey,
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

The executor requires a pinned Verigate Ed25519 public key (`verigatePublicKey`) provisioned out-of-band for the tenant. It verifies the signed execution authorization locally before any transaction is submitted. Fetching the key from the same API endpoint at runtime would be trust-on-first-use and would not protect against an API or transport key substitution.

The helper performs the following sequence:

1. Requests Verigate authorization using the signed agent intent.
2. Submits Registry registration with the operator's issuer signer.
3. Waits for the transaction receipt and asks Verigate to verify registration.
4. Submits one-time Registry consumption with the agent's signer.
5. Waits for the receipt and asks Verigate to verify consumption.
6. Submits the exact USDC payment with the same agent signer.
7. Asks Verigate to verify the successful USDC Transfer event and finalized Arc block.
8. Returns the three transaction hashes and settlement evidence.

The issuer signing service should enforce an allowlist for the Registry contract and registration selector. Do not distribute the raw issuer private key to agents. The agent executor key must remain in a restricted agent-scoped signing boundary. **Do not give an autonomous model or untrusted agent process unrestricted access to the raw EVM private key.** This executor validates the transaction before calling its signer, but an agent that can bypass this process and call an unrestricted key directly can bypass Verigate as well. For production, the signer service/KMS policy must independently enforce the same authorization and transaction constraints, and only expose the constrained signing operation. A raw `Wallet` loaded from an environment variable is a local integration example, not a production security boundary. The agent executor also needs the Arc native gas asset for transaction fees.

## 5. Registry issuer configuration

Set `VERIGATE_ARC_ISSUER_ADDRESS` to the Registry owner/issuer account. For backward compatibility, the API still accepts the legacy `VERIGATE_ARC_EXECUTOR_ADDRESS` as a fallback issuer setting.

Do not set a global executor address for all agents. Each executor is taken from the signed payment authorization. Verigate verifies the on-chain Registry owner and enabled issuer before preparing registration.

## Browser adapter

`integrations/arc-client.mjs` and `docs/ARC_WALLET_CLIENT.md` remain available as an optional EIP-1193 adapter for interactive demos and human-operated wallets. They are not the primary autonomous-agent path.

## Evidence boundary

The headless flow is covered by tests and source-level implementation. It is not yet deployed to a hosted Verigate API and has not yet been used for a live Verigate-authorized Arc USDC payment. Do not claim live settlement until an actual agent signer executes the flow and the payment-confirmation endpoint returns verified finalized evidence.
