# Verigate Authority (Anna App)

Verigate Authority lets a user describe a payment or transfer, uses Anna AI to extract the structured fields, and asks Verigate to evaluate those exact fields against its deterministic policy.

The AI does not decide whether the action is authorized. Verigate returns the decision and a signed Decision Receipt. The UI displays ALLOW, WARN, or BLOCK with a plain-language explanation, matched policy rules, and the receipt for technical inspection. No transaction is executed by this app.

## User flow

1. Describe the payment in natural language.
2. Select **Interpret with Anna AI** and review the proposed recipient, asset, network, amount, and purpose.
3. Correct any fields as needed and select **Check authority**.
4. Review the Verigate decision and matched rules. The receipt can be inspected or saved from the details panel.

Do not treat ALLOW as a guarantee that the transaction is safe, will execute, or has executed.

## Anna packaging

The App uses Anna's Bundled Executa model. The stable handle is `verigate-authority`; Anna resolves it to the platform-assigned production `tool_id` when publishing. Local development keeps `tool-dev-verigate-authority`.

The app manifest explicitly requests the Anna host LLM completion surface (`host_api.llm: ["complete"]`) and the bundled Verigate tool. The LLM is used only for request extraction and explanation. Policy evaluation and the final decision stay inside Verigate.

The Executa is distributed as four platform binaries:

- `darwin-arm64`
- `darwin-x86_64`
- `linux-x86_64` (required for Anna Cloud Agent)
- `windows-x86_64`

GitHub Actions builds and smoke-tests all four binaries and publishes them as GitHub Release assets. Download the four release archives into `anna/executas/verigate-authority/dist/` before publishing the app if fresh artifacts are required.

## Local validation

From this directory:

```bash
anna-app validate --strict
```

From the repository root, run the Anna Executa protocol tests and the regular Verigate test suite:

```bash
python -m unittest tests.test_anna_executa_manifest -v
python -m unittest discover -s tests -v
```

Before resubmitting, publish the app bundle, install it as a fresh Anna Cloud Agent, and test at least these independent inputs:

- a small payment to a new recipient (expected policy result based on the default policy);
- an amount exceeding the configured per-transaction cap (BLOCK);
- an amount above the confirmation threshold or first-payee cap (WARN);
- a network outside the default allowed list (BLOCK).

Record the actual returned decision and matched rules during those tests. Do not state that a case passed unless the cloud agent returned that result.
