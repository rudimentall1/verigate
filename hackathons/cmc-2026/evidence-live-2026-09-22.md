# CMC RWA Live Evidence — 2026-09-22

Live run executed locally with a CMC API key entered interactively.
The credential is not stored in this evidence or repository.

## CMC map
- Endpoint: GET /v5/real-world-assets/map
- Symbol: GOLD
- Name: Gold
- rwa_id: 1
- asset_type: commodity
- has_tokens: true
- Last historical data: 2026-09-22T13:15:00Z

## CMC quote
- Endpoint: GET /v5/real-world-assets/quotes/latest
- Source timestamp: 2026-09-22T13:21:29.264Z
- average_tokenized_price: 4339.445333488919 USD
- tokenized_market_cap: 4680046906.622491 USD
- tokenized_volume_24h: 492779966.6268578 USD
- tracked tokens: 7
- issuer provenance records: 6
- same-issuer price spread: 0.0006582250575146856

## Verigate authorization
- action_type: rwa.purchase
- purchase amount: 500 USD
- decision: ALLOW
- matched rules: none
- execution authorization: issued
- transaction broadcast: no
- action fingerprint: e2e4432a02dabd8f63b9f6cb6af4c466cdb8a1e04cdc8a42ac507bd61da12da0

## Hard block verification
- blocked purchase: 5001 USD
- decision: BLOCK
- matched rule: rwa_purchase_cap_exceeded
- execution authorization: not issued
- transaction broadcast: no

## Reproducibility
- Full test suite before live verification: 69/69 passed.
- Demo mode intentionally stops before transaction broadcast.
