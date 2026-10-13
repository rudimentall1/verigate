# Hackathon work

This directory holds competition-specific planning, adapters, demos, and evidence. Keep hackathon work isolated from Verigate's core protocol and production-facing code.

## PortaldotV3 Hacker House 2026

- [PortaldotV3 integration plan](portaldot-v3/PLAN.md)

Rules for this directory:
- Do not rewrite Verigate's core authority lifecycle, signing protocol, router, or execution model solely for a hackathon.
- Put chain-specific code, contracts, scripts, tests, and demo assets in the relevant hackathon subdirectory.
- Reuse existing Verigate capabilities only where their current behavior is accurate and documented. Do not describe planned integration as implemented.
- Keep secrets, private keys, seed phrases, and funded-wallet material out of Git.
- Record deployed addresses, transaction hashes, test results, and demo links only after independently verifying them.
- Follow the event's current submission rules. Confirm any ambiguity with organizers rather than assuming a local devnet is acceptable.
