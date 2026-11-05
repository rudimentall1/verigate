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

| Blockchain0x | Official contact page only | https://www.blockchain0x.com/contact | Not sent. The official page describes a partnership form and masks its direct email address; the email link failed to reveal an address. Do not guess it. |
| Sony Onchain Entertainment Incubation Program (FANOVA) | Official application portal | https://onchain-entertainment.sony.com/en/incubation-program/ | Not emailed because the official route is an application form, not a public partnership inbox. FANOVA is a strong thematic fit; prepare an application from its actual Soneium evidence and do not invent company/team/legal facts. |

## Follow-up discipline

- Do not send duplicate messages while an initial message is still fresh.
- If there is no response, a single concise follow-up can be considered after five business days (from 2026-11-04, target date 2026-11-11).
- Do not expand into substantial custom integration work without an agreed scope, named technical owner, test environment, acceptance criteria, and written commercial model.
- Keep all claims tied to public repository evidence. Do not claim partner acceptance, production adoption, independent audit, revenue, or successful live provider completion where those have not been demonstrated.


## Additional outreach sent — 2026-11-04

| Organization | Recipient | Subject | Gmail message | Scope |
|---|---|---|---|---|
| Nevermined | `contact@nevermined.ai` | Nevermined × Verigate: independent authority proofs before agent payments | [Sent](https://mail.google.com/mail/u/0/#all/1a1a577f8ad839d6) | Proposed a sandbox payment-flow evaluation with mandate-bound ALLOW, out-of-policy DENY, replay/tamper rejection, and portable evidence. Asked about paid pilot / co-development / revenue sharing. |
| Privy | `sales@privy.io` | Privy Wallet Actions × Verigate: independent authorization for agent transfers | [Sent](https://mail.google.com/mail/u/0/#all/1a1a578089c287d3) | Proposed independent authorization before one Wallet Actions transfer; explicitly preserves Privy's signing policies and user consent. Mentioned Agentic Wallet Guardian as an unaudited working prototype. Asked about paid pilot / ecosystem partnership. |
| Exa | `sales@exa.ai` | Exa × Verigate: verifiable authorization for agent-initiated API purchases | [Sent](https://mail.google.com/mail/u/0/#all/1a1a5781b792502f) | Proposed authorization at agent API-purchase boundary, complementing Nevermined settlement. Clearly labelled x402-attest as PoC and no Exa integration as existing. Asked about co-integration and partner commercial model. |
| Prava | `support@prava.space` | Prava × Verigate: independent signed authorization for agent payments | [Sent](https://mail.google.com/mail/u/0/#all/1a1a5782494b43bb) | Proposed sandbox authorization before checkout, preserving Prava's passkey/biometric final user confirmation. Asked for product/engineering routing and paid pilot / partnership. |

All four messages were sent successfully through Gmail. No reply or commercial agreement is implied by delivery.


## Additional outreach sent — 2026-11-05

| Organization | Recipient | Subject | Gmail message | Scope |
|---|---|---|---|---|
| delta | `myles@delta.network` | delta × Verigate: independent agent authority before settlement | [Sent](https://mail.google.com/mail/u/0/#all/1a1aa07683b374f0) | Proposed complementing delta Domains / Local Laws with Verigate identity-capability checks and single-use action-bound authorization before execution. Asked about sandbox/testnet evaluation and paid pilot / design-partner / SDK route. |
| Subnet345 / Plexus | `hello@subnet345.com` | Subnet345 / Plexus × Verigate: execution authorization proofs for agent actions | [Sent](https://mail.google.com/mail/u/0/#all/1a1aa0772143d747) | Proposed Verigate as deterministic authorization at the execution boundary and Plexus as the tamper-evident record substrate. Explicitly distinguished shipped record capabilities from runtime enforcement still in development. Asked about a narrow paid evaluation / co-development. |
| Alloy | `hello@alloy.build` | Alloy WalletKit × Verigate: provider-neutral, single-use authority proofs | [Sent](https://mail.google.com/mail/u/0/#all/1a1aa077e5ea5daa) | Proposed an independent, portable one-time authorization artifact alongside Alloy PolicyKit / RiskGuard / WalletKit, not as a replacement. Asked about a mock/test-provider evaluation and a fixed-scope paid pilot / design partnership. |

All three messages were confirmed sent by Gmail. No replies or agreements are implied.


## New inbound response and meeting — 2026-11-05

| Organization | Response | Status / next step |
|---|---|---|
| Circle | Michael Onagoruwa replied on 2026-11-04, praised the Verigate approach and invited Rinat to book a call. [Original thread](https://mail.google.com/mail/u/0/#all/1a1a56626dd47e94) | Booking confirmed by Google Calendar email for 2026-11-05, 22:15–22:45 Yekaterinburg time (GMT+5). Rinat replied that he does not speak English and asked for written chat or a Russian-speaking colleague/interpreter. [Reply sent](https://mail.google.com/mail/u/0/#all/1a1aa05da34970ae). This is a scheduled introductory discussion, not a paid pilot or partnership agreement. |

## Monitoring

A daily Gmail monitoring automation was created on 2026-11-05 (task ID `6aec09becc9c8191b0c06ea03ad0c50c`). It alerts only for new substantive partner replies and does not send follow-ups or make commitments.


## Additional outreach sent — 2026-11-05

| Organization | Recipient | Subject | Gmail message | Scope |
|---|---|---|---|---|
| Openfort | `support@openfort.xyz` | Openfort × Verigate: independent authorization before agent wallet execution | [Sent](https://mail.google.com/mail/u/0/#all/1a1aa0958197071b) | Proposed a sandbox backend-wallet transaction test with exact-action authorization, ALLOW/DENY, replay/tamper rejection, and portable evidence. Asked for routing to product/integrations and a fixed-scope paid pilot or ecosystem partnership. |
| Particle Network | `pantao@particle.network` | Particle Network × Verigate: one-time authority proofs for agent smart-account actions | [Sent](https://mail.google.com/mail/u/0/#all/1a1aa0960438a418) | Proposed an additional action-bound authorization around Particle smart-account/session execution, preserving Particle's signer and session protections. Asked for account-abstraction/partnership contact and a paid pilot. |
| ZeroDev | `support@zerodev.app` | ZeroDev × Verigate: independent authorization for Kernel session transactions | [Sent](https://mail.google.com/mail/u/0/#all/1a1aa0969394058d) | Proposed a testnet Kernel-session integration with exact-action single-use permission and replay/tamper checks, complementing rather than bypassing ZeroDev's permissions. Asked for routing and paid pilot discussion. |

All three messages were confirmed sent by Gmail. These are initial partnership inquiries, not accepted integrations or commercial agreements.
