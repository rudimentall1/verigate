# Privacy Policy

Last updated: 2026-10-20

This policy covers the **Verigate Authority** app for Anna and the open-source **Verigate** software in this repository (https://github.com/rudimentall1/verigate).

## What the Anna app does with your data

Verigate Authority checks a payment you describe against a policy and returns ALLOW, WARN or BLOCK with a signed Decision Receipt. It does not send, sign or execute any transaction.

- **What you enter:** the plain-language description and the form fields (agent identifier, recipient, asset, network, amount, purpose or invoice).
- **Anna's language model:** to read your request, ask about missing details, flag risks and explain the result, the app sends your description and the form values to the language model provided by Anna through its app runtime. That processing is governed by Anna's own privacy policy and terms. The developer of Verigate does not receive, store or see these prompts.
- **The policy check:** it runs locally inside the Verigate tool on the Anna agent where you installed the app. It does not call any external service.
- **What is stored:** a check is a simulation and is not recorded. The tool keeps only a signing key (used to sign Decision Receipts) and a small local policy database in its app data folder on your agent. They stay on your agent; the developer does not receive them.
- **Receipts:** the signed Decision Receipt is shown in the app window. If you copy or share it, it contains the details of the request.

## What we do not do

- No analytics, tracking, advertising or profiling.
- No sale or sharing of data with third parties.
- No access to your wallets, private keys or funds. Please never type private keys or seed phrases into the app.
- No hosted service: the developer operates no server that receives your data.

## Verigate as open-source software

If you run Verigate yourself, the data you process stays under your control. The software contains no telemetry.

## Children

The app is not directed at children.

## Security

Report vulnerabilities privately as described in SECURITY.md.

## Changes and contact

We may update this policy; the date above changes when we do. Questions: https://github.com/rudimentall1/verigate/issues
