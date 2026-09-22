# CMC 2026 — Verigate RWA Pack

This pack is an adapter, not a fork of Verigate.

## Flow

CMC RWA API
→ normalized RWA market evidence
→ ActionIntent(type=rwa.purchase)
→ deterministic RWA policy
→ ALLOW / WARN / BLOCK
→ signed DecisionReceipt
→ one-time ExecutionAuthorization
→ EVM execution adapter

The CMC API supplies evidence. It never authorizes execution.

## CMC endpoints used

- GET /v5/real-world-assets/map
- GET /v5/real-world-assets/quotes/latest

The RWA API uses a stable rwa_id as the primary asset identifier and
provides tokenized aggregate price, market cap, 24h volume, underlying tokens,
and TradFi markets. The adapter resolves the symbol first, then carries the
stable ID into the quote request.
## Local demo

Create an environment variable without committing the secret:

    $env:CMC_API_KEY = "..."

Then run:

    .\\.venv\\Scripts\\python.exe .\\demo_cmc_rwa.py --symbol GOLD --amount-usd 500

Offline smoke test:

    .\\.venv\\Scripts\\python.exe .\\demo_cmc_rwa.py --fixture

The live demo prints the CMC endpoint, visible response evidence, the Verigate
decision, the matched policy rules, and whether an execution capability was
minted. It intentionally does not broadcast a transaction.

## Current policy

See policy.yaml.

Default controls:

- allowed RWA types: stock, commodity, currency, government security, ETF,
  real estate
- tokenization required
- maximum purchase: 5,000 USD
- WARN when purchase exceeds 1% of tokenized 24h volume
- WARN when purchase exceeds 0.1% of tokenized market cap
- require CMC issuer provenance on tracked tokens
- WARN when multiple tracked tokens from the same issuer show price dispersion above 2%
## Hackathon status

The CMC hackathon build window is 9–30 September 2026. Submission requires a
public repository, a working demo/deployed link or recording, the CMC
endpoints named explicitly, and visible evidence of a real API call and
response.

Verigate remains the canonical repository. This folder is only the CMC
submission layer.

Live verification is complete: a real CMC API call was captured on 2026-09-22 and stored without credentials in evidence-live-2026-09-22.md.

Before submission:

1. deploy or record the working flow;
2. freeze the product;
3. add the submission link and final evidence to hackathons/registry.yaml.
