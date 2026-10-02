# Verigate Authority (Anna App)

Give Verigate an agent action. Verigate decides whether the agent has the
authority to execute it. Execution produces evidence. Anyone can later
verify that evidence without trusting Verigate.

This Anna App is a thin wrapper, not a fork: the bundled Executa
(`executas/verigate-authority/verigate_authority_plugin.py`) imports
`core.engine.GuardrailEngine` from the real `verigate` package at the
repository root and calls it directly. Nothing in `core/`, `api/`, or
`attest/` is modified or duplicated for Anna.

## What it does

The App exposes one tool, `verigate_check`, which takes a payment-shaped
agent action (`agent_id`, `payee`, `asset`, `network`, `amount`, optional
`resource`) and returns Verigate's signed decision: a full `decision_receipt`
(the evaluated policy, the matched rules, and an Ed25519 signature over all
of it) plus an `execution_authorization` when the action is allowed. Any
third party holding that receipt can verify it independently -- they do not
need to trust this Anna App, Anna, or Verigate's own server.

## Local development

```bash
anna-app validate           # static checks
anna-app dev                # local harness: http://127.0.0.1:5180/
```

To call the tool directly without the browser UI:

```bash
cd executas/verigate-authority
anna-app executa dev --invoke verigate_check \
  --args '{"agent_id":"demo-agent","payee":"0xMerchant","asset":"USDC","network":"base","amount":10.5}' \
  --json
```

The Executa generates its own throwaway Ed25519 issuer key on first run,
under `executas/verigate-authority/.data/` (gitignored -- never commit it).
It uses its own SQLite database too, entirely separate from whatever
database a real `verigate` deployment (`api/main.py`, `cli.py`) uses.

## Publishing

```bash
anna-app executa publish     # from executas/verigate-authority/
anna-app apps publish        # from the anna/ app root
```
