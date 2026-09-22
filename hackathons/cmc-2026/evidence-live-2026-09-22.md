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
- Last historical data: 2026-09-22T12:15:00Z

## CMC quote
- Endpoint: GET /v5/real-world-assets/quotes/latest
- Source timestamp: 2026-09-22T12:17:06.764Z
- average_tokenized_price: 4324.937296653039 USD
- tokenized_market_cap: 4664439100.453683 USD
- tokenized_volume_24h: 504509245.6338366 USD
- tracked tokens: 7
- issuer provenance records: 6
- same-issuer price spread: 0.0007539251612624997

## Verigate authorization
- action_type: rwa.purchase
- purchase amount: 500 USD
- decision: ALLOW
- matched rules: none
- execution authorization: issued
- transaction broadcast: no
- action fingerprint: 88749ce0d5424a4c67d7e24c224907d37cf239afbb0447769b08dac61e249b54

## Reproducibility
- Full test suite before live verification: 69/69 passed.
- Demo mode intentionally stops before transaction broadcast.
