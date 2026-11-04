# Partner outreach log — 2026-11-04

This log records actual outreach and verified channel limitations. It does not imply that any recipient is a customer, partner, endorser, or has agreed to a pilot.

## Sent

| Date | Organization | Recipient / channel | Subject / reference | Status |
|---|---|---|---|---|
| 2026-11-04 | Valta | Debo Jolaosho, `debo@valta.co`; existing Gmail thread | [Gmail thread](https://mail.google.com/mail/u/0/#all/1a1a196ebdee7d63) | Sent. Asked for sandbox/test credentials and target API boundary. Live smoke request is documented accurately as ALLOW + consumed authorization followed by upstream HTTP 429 `credit_balance_exhausted`. |
| 2026-11-04 | Valta | GitHub Issue | https://github.com/Valta-hq/Valta-MCP/issues/1 | Open. Scope now proposes gating `valta_transfer_funds` before `POST /wallet/transfer`. No transfer has been executed. |
| 2026-11-04 | Circle | `alliance@circle.com` | [Gmail thread](https://mail.google.com/mail/u/0/#all/1a1a56626dd47e94) | Sent. Subject: Circle Agent Stack × Verigate: independent authorization proofs for agent payments. Asked for technical routing, narrow testnet evaluation, and paid pilot / Alliance pathway. |
| 2026-11-04 | AiFinPay | `contact@aifinpay.io` | [Gmail thread](https://mail.google.com/mail/u/0/#all/1a1a5663177d42ae) | Sent. Subject: AiFinPay × Verigate: verifiable authorization before x402 payment execution. Proposed a quote-bound pre-payment authorization proof; asked for test route and commercial pilot / partnership discussion. |
| 2026-11-04 | Alchemy / AgentCard / AgentPay | `legal@alchemy.com` (published as business / partnership contact on AgentCard) | [Gmail thread](https://mail.google.com/mail/u/0/#all/1a1a567b86f119de) | Sent. Subject: Alchemy Agent Wallets / AgentPay × Verigate: independent authorization evidence. Asked to route to the Agent Wallets, AgentPay, or AgentCard product/engineering owner for a narrow evaluation. |
| 2026-11-03 | Griffin AI | `collaborations@griffinai.io` | [Gmail thread](https://mail.google.com/mail/u/0/#all/1a1a197c299a5573) | Previously sent. Subject: Griffin AI × Verigate: authority control for on-chain agent actions. No follow-up sent; allow time for response. |

| 2026-11-04 | x402 Agentic | `hello@x402agentic.ai` | [Gmail thread](https://mail.google.com/mail/u/0/#all/1a1a569f8ddfc692) | Sent. Subject: x402 Agentic × Verigate: quote-bound authorization and verifiable payment evidence. Proposed x402 quote-bound authorization, testnet/mock tests, and paid integration / ecosystem partnership. |
| 2026-11-04 | Axblade | `contact@axblade.io` | [Gmail thread](https://mail.google.com/mail/u/0/#all/1a1a56a05a422303) | Sent. Subject: Axblade × Verigate: independent authority proofs for agent payment mandates. Proposed Arc Testnet evaluation complementing Axblade mandates; asked about paid pilot / co-development. |
| 2026-11-04 | Wirex | `partners@wirexapp.com` | [Gmail thread](https://mail.google.com/mail/u/0/#all/1a1a56a10f14cdae) | Sent. Subject: Wirex AGENTS × Verigate: independent authorization for agent payment execution. Asked to route to AGENTS / developer platform owner and discuss a paid pilot / partnership. |

## Public projects mentioned in outreach

- **Verigate:** https://github.com/rudimentall1/verigate — action-bound identity/capability/policy authorization and one-time execution enforcement.
- **x402-attest:** https://github.com/rudimentall1/x402-attest — proof of concept for x402 v2 payment requirement parsing and Ed25519-signed ALLOW/BLOCK decisions. It is not a production product.
- **Agentic Wallet Guardian:** https://github.com/rudimentall1/agentic-wallet-guardian-v3 — a separate self-hosted on-chain transaction security project with a live Arc mainnet USDC demo and recorded successful transaction. It has not had an independent security audit.
- **Open Agent Attestation:** https://github.com/rudimentall1/open-agent-attestation — a draft proposal, not an adopted standard.

OWNERA is private and is deliberately excluded from all external outreach.

## Researched but not contacted yet

| Organization / route | Verified state | Reason not sent |
|---|---|---|
| Coinbase AgentKit | https://github.com/coinbase/agentkit is active and welcomes community contributions. | The repository already has several open proposals covering external spend authority, wallet wrappers, and x402 payment security (including issues #1582, #1282, #1384). No duplicate issue was opened and no unverified email was guessed. A distinct implementation contribution would need to be materially different. |
| Crossmint | Official sales and partnership forms exist. The partner form explicitly rejects `@gmail.com` and requires a professional/company email. | Do not bypass the stated requirement or invent a company domain. Revisit when a legitimate work-domain address is available. Free staging is documented by Crossmint; production requires an enterprise agreement. |
| Sony Onchain Entertainment Incubation Program (FANOVA) | Official application window runs 2026-10-29 through the end of December 2026. FANOVA is an early-stage Soneium entertainment/fan-community prototype with completed user-approved mainnet provenance transactions. | The official route is an application, not a published direct email. Do not invent a contact address or submit unknown company/team/legal details. Prepare the application from FANOVA's evidence map and confirm any missing mandatory founder/company fields before submission. |
| PortalDot | Public developer/community channels are present (Discord and official X account); our PortalPilot and Verigate-PortalDot work has testnet evidence. | No verified partner email was found. Do not guess an inbox or claim PortalDot Wallet/DaaS adoption. Continue through the official hackathon/community channel when available. |
| Pink Agentic AI Payments | Public sandbox and a call for three design partners are advertised. The stated target is teams with real agents making recurring purchases of API credits, ads, cloud, travel, or supplier payments. | Our current projects do not establish that live recurring business use case. Do not present ourselves as an operating design partner when that is not true. |

## Follow-up discipline

- Do not send duplicate messages while an initial message is still fresh.
- If there is no response, a single concise follow-up can be considered after five business days (from 2026-11-04, target date 2026-11-11).
- Do not expand into substantial custom integration work without an agreed scope, named technical owner, test environment, acceptance criteria, and written commercial model.
- Keep all claims tied to public repository evidence. Do not claim partner acceptance, production adoption, independent audit, revenue, or successful live provider completion where those have not been demonstrated.
