# Hackathon work

This directory holds competition-specific planning, adapters, demos, and evidence. Keep hackathon work isolated from Verigate's core protocol and production-facing code.

## Portaldot V3 Hacker House 2026

- [Integration plan and official event milestones](portaldot-v3/PLAN.md)
- [Verigate source reuse audit and security boundaries](portaldot-v3/REUSE_AUDIT.md)
- [First build day checklist](portaldot-v3/START_TOMORROW.md)

PortalDot implementation work now lives in the separate public repository [rudimentall1/verigate-portaldot](https://github.com/rudimentall1/verigate-portaldot). The initial contract, bridge-signing CLI, test suite, RPC preflight and docs are committed there. GitHub Actions reports 15 passing tests and a successful Solidity compile. No live PortalDot RPC check or deployment is claimed yet.

Rules for this directory:
- Do not rewrite Verigate's core authority lifecycle, signing protocol, router, or execution model solely for a hackathon.
- Put chain-specific code, contracts, scripts, tests, and demo assets in the relevant hackathon subdirectory or the dedicated contest repository.
- Reuse existing Verigate capabilities only where their current behavior is accurate and documented. Do not describe planned integration as implemented.
- Keep secrets, private keys, seed phrases, and funded-wallet material out of Git.
- Record deployed addresses, transaction hashes, test results, and demo links only after independently verifying them.
- Follow the event's current submission rules. Confirm any ambiguity with organizers rather than assuming a local devnet is acceptable.
