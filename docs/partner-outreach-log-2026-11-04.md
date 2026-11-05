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


## Additional outreach sent — 2026-11-05 (continued)

| Organization | Recipient | Subject | Gmail message | Scope |
|---|---|---|---|---|
| Openfort | `support@openfort.xyz` | Openfort × Verigate: independent authorization before agent wallet execution | [Sent](https://mail.google.com/mail/u/0/#all/1a1aa0958197071b) | Proposed a sandbox backend-wallet transaction test with exact-action authorization, ALLOW/DENY, replay/tamper rejection, and portable evidence. Asked for routing to product/integrations and a fixed-scope paid pilot or ecosystem partnership. |
| Particle Network | `pantao@particle.network` | Particle Network × Verigate: one-time authority proofs for agent smart-account actions | [Sent](https://mail.google.com/mail/u/0/#all/1a1aa0960438a418) | Proposed an additional action-bound authorization around Particle smart-account/session execution, preserving Particle's signer and session protections. Asked for account-abstraction/partnership contact and a paid pilot. |
| ZeroDev | `support@zerodev.app` | ZeroDev × Verigate: independent authorization for Kernel session transactions | [Sent](https://mail.google.com/mail/u/0/#all/1a1aa0969394058d) | Proposed a testnet Kernel-session integration with exact-action single-use permission and replay/tamper checks, complementing rather than bypassing ZeroDev's permissions. Asked for routing and paid pilot discussion. |

All three messages were confirmed sent by Gmail. These are initial partnership inquiries, not accepted integrations or commercial agreements.


## Funding and sponsorship opportunities — 2026-11-05

| Program | Official route / status | Fit and constraints | Action / status |
|---|---|---|---|
| Tether Developer Grants | https://tether.dev/grants/ ; application route: https://tether.dev/grants/apply-for-a-grant/ ; official grants contact: grants@tether.io | Relevant to open-source AI, wallet infrastructure, security and integrations. Proposed a fixed-scope WDK adapter milestone: exact recipient/asset/amount authorization, replay/tamper tests, runnable demo and docs. | Initial fit inquiry actually sent 2026-11-05 to grants@tether.io; subject: "Verigate × Tether WDK: open-source agent authorization integration"; Gmail message: https://mail.google.com/mail/u/0/#all/1a1aa0efaeeeb5d8. Requested guidance and asked whether approximately USD 4,000 could fund the milestone. This is not a formal grant application or an award. Legal caution: Tether's application terms state submissions are non-confidential and grant Tether a broad, perpetual, royalty-free licence to submitted materials; do not provide non-public information without reviewing the terms. |
| Sentient Foundation — Open Source AGI Grant Program | https://sentient.foundation/grants ; official application: https://form.typeform.com/to/IRj7WaKH ; rolling intake | Very strong thematic fit: trusted-agent foundations, proof, identity and safe agents. The page advertises $42M committed to the programme overall, not as a per-project grant amount. Public-goods grant track is described as no-equity/no-strings. | Application not submitted. Prepare an evidence-led application using only public Verigate material and confirm scope and requested funding in the form. |
| HTX DAO — Genesis Grant | https://www.htxdao.com/en-us/genesis | Multi-million-dollar ecosystem development programme for builders, infrastructure and tools; initial Genesis Fund announced at $10M. Potential fit for agent infrastructure, but ecosystem relevance / integration case must be made. | Portal located; no application submitted and no direct grant email verified. |
| COTI — Vibe Code Challenge, Agent Edition | https://stay.coti.io/vibe-coding/ | Agent Infrastructure track accepts tools, SDKs, templates and primitives using COTI privacy stack. Published prizes: 100,000 / 50,000 / 25,000 COTI. Official page currently says end date to be announced. | Strong thematic opportunity but requires a working launch on COTI and a public demo / submission. Verigate does not currently have a COTI integration; do not submit before that exists. |
| Safe Ecosystem Foundation — spontaneous grants | https://safefoundation.org/grants | Strong product fit for smart-account security, protocol tooling, SDKs and interoperability. Spontaneous proposals accepted on a rolling basis; milestone plan and budget expected. | Grant contact is hidden behind website email protection; no direct address verified and no email sent. Do not guess an inbox. |
| Base Ecosystem Fund | https://www.base.org/ecosystem-fund/apply ; Base Request for Builders: https://www.base.org/blog/request-for-builders-1 | Potential pre-seed / seed funding for financial infrastructure and agentic commerce. This is an investment route, not a guaranteed grant. A stronger application would need a clear Base-first strategy. | Application not submitted. Base Batches 004 is closed; do not represent it as open. |
| Nosana Grants | https://nosana.com/grants/ | Public page advertises non-dilutive grants and GPU credits, but eligibility requires a meaningful use of Nosana's decentralized GPU network for AI/LLM compute. | Weak current fit: Verigate is deterministic authorization infrastructure and does not currently depend on Nosana compute. Revisit only with a real, useful Nosana integration. |

Funding-search discipline: verify every opportunity from official rules before acting; distinguish grants, prizes, paid pilots and investment. Do not submit legal, company or team facts that have not been confirmed. Do not pay application fees, buy tokens, deposit funds, or promise unpaid custom development. No funding award, sponsor commitment or partnership acceptance is implied by this research or by the Tether inquiry.


## Additional funding routes verified — 2026-11-05 (continued research)

| Program | Current official status and support | Fit / constraints | Next step |
|---|---|---|---|
| ARIA — Scaling Trust, Track 2: Tooling | Official page: https://aria.org.uk/opportunity-spaces/trust-everything-everywhere/scaling-trust/funding ; application portal: https://aria.grantplatform.com/ . Nearly £49.8m programme overall. The current call is rolling, reviewed quarterly. Track 2 funding is stated as £200k–£2m per project for 4–6 teams; tooling must be open-source components for secure agent coordination, protocol generation and verification. The 2026-10-31 proposal cut-off has passed; proposals after that date go into the next quarterly cycle, whose dates are to be confirmed. | Very strong technical fit for Verigate's signed authority, delegation and independently checkable execution proofs. ARIA welcomes individuals as well as companies. UK is its primary funding focus; applicants outside the UK must show a concrete contribution to UK programme impact. Funded foreground software must use dual MIT + Apache 2.0 licensing; Verigate's pre-existing background IP remains owned by its owner. This is a substantial R&D proposal rather than a small quick grant. | Highest-priority application candidate for next cycle. Prepare a focused Track 2 proposal around a reusable open-source agent authority / execution verification component, but confirm applicant geography/UK impact, project team, deliverables, budget, and dual-licence implications before submission. No application submitted. |
| Circle Developer Grants | Official programme: https://www.circle.com/grant ; application portal: https://circle.questbook.app/ . Offers milestone-based USDC funding, co-marketing, technical mentorship and Circle ecosystem access. No public fixed grant amount. | Very strong use-case overlap with agentic economic activity, but the criteria specifically require Arc to be core to value flow/liquidity/settlement and Circle products (USDC, Wallets, CCTP, Nanopayments, Gateway, etc.) to be meaningful parts of the product. Verigate has not yet shipped an Arc/Circle integration. | Discuss in the already-booked Circle meeting on 2026-11-05: ask whether a narrowly scoped Arc testnet + USDC/Wallets authorization pilot is eligible for milestone funding and whether the grants team can route the project into the portal. No grant application submitted. |
| Arbitrum Foundation grants / ArbiFuel / Audit Program | Official directory: https://arbitrum.foundation/grants . Foundation grant page currently lists rolling milestone-based support for dApps and Infrastructure & Tools. ArbiFuel is active gas-fee sponsorship for early teams. The Arbitrum Audit Program is listed as $10M in ARB over 12 months for third-party smart-contract audit subsidies. | Relevant as a separate pathway from the already-submitted Arbitrum Mentorship application. An Arbitrum-focused Verigate adapter could fit Infrastructure & Tools; ArbiFuel can reduce test/deployment gas costs but is not cash grant funding. Audit subsidy would apply only if a qualifying Arbitrum smart-contract project actually needs an external audit. | Do not re-submit Mentorship. Evaluate a separate Foundation infrastructure grant only after defining a specific Arbitrum deliverable and scope. ArbiFuel is a possible no-cash-cost support route. No new application submitted. |

For ARIA, the official solicitation also specifies a 3–18 month project period, detailed technical/team/budget proposal, and requires that foreground software funded under Track 2/3 be released under MIT and Apache 2.0; pre-existing background IP remains owned by the applicant. Non-UK organisations must explain how their work will contribute to impact in the UK. These terms must be considered before applying.


## Inbox review — 2026-11-05 (evening)

| Organization | New inbound message | Verified status / next step |
|---|---|---|
| Circle | Michael Onagoruwa said the Circle team has no Russian-speaking colleagues and proposed continuing by email. [Message](https://mail.google.com/mail/u/0/#all/1a1ac12ea150b1c9) | Rinat accepted email communication and asked for the next step toward technical evaluation, a product/engineering contact, and a possible fixed-scope paid pilot or grant route. [Reply sent](https://mail.google.com/mail/u/0/#all/1a1acb7234d15967). The Google Calendar appointment for 2026-11-05 22:15–22:45 GMT+5 was subsequently cancelled by Michael; this is consistent with switching to email, not a partnership rejection. [Cancellation notice](https://mail.google.com/mail/u/0/#all/1a1acb8d8063ed8c). No funding or pilot commitment yet. |
| ZeroDev | Automated acknowledgement from Linear created support ticket **ZDS-368** for the Verigate inquiry. [Ticket acknowledgement](https://mail.google.com/mail/u/0/#all/1a1aa0969394058d) | Not a substantive product/engineering response. Await review; do not send duplicate inquiry. |
| Openfort | No reply located as of the evening inbox review. | Initial email sent; no follow-up due yet. |
| Particle Network | No reply located as of the evening inbox review. | Initial email sent; no follow-up due yet. |
| Tether | No reply located as of the evening inbox review. | Initial grant-fit inquiry sent; not a formal grant application. |
| Other contacted prospects | No other substantive human response located in the inbox search for 2026-11-04 onward. | Continue monitoring; automated receipts and marketing mail are not counted as partner interest. |

Circle's meeting is no longer scheduled. Continue by email only unless Michael proposes another format.
