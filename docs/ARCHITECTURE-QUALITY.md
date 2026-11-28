# Architecture Quality Audit

**Status:** advisory pilot enabled on pushes to `main`, pull requests targeting `main`, and manual dispatch.  
**Workflow:** `.github/workflows/architecture-audit.yml`  
**Scope:** Python, TypeScript, and JavaScript source projects discovered by the tool. Solidity is not supported by this scanner.

## Purpose

[deslop-please](https://github.com/Bor4brn/deslop-please) checks source structure using the principle of deep modules and narrow interfaces. The pilot reports:

- `module-cycle` — cycles between modules;
- `tangle` — tangled dependencies between types, functions, and constants;
- `field-leak` — object fields exposed beyond the object boundary;
- `shallow-module` — modules with an overly broad, shallow interface;
- `wide-directory` — directories with too many source files;
- `long-file` — source files exceeding the configured line threshold.

Review a finding against the real dependency and ownership boundaries. Do not mechanically move code, widen abstractions, or change public APIs just to reduce a diagnostic count.

## Pinned toolchain

The workflow pins:

- `deslop-please` to multi-language port commit `cfabfb9ee417e150d5342e8ef0d6a0fe725cc9a0`;
- Rust toolchain `1.99.0` to build the CLI;
- `@sourcegraph/scip-python` `0.6.8`;
- `@sourcegraph/scip-typescript` `0.5.2`.

These tools are installed only on the ephemeral GitHub Actions runner. They are not added to Verigate's runtime dependencies, `requirements.txt`, or npm lockfiles.

The workflow runs `deslop-please --language auto --json`. The tool discovers supported language projects from repository manifests, including the root Python project and nested Python packages. For JavaScript/TypeScript it uses the project's own `tsconfig.json`, or creates a temporary inferred config under its user cache when none exists. Python and TypeScript/JavaScript SCIP indexes are cached outside the repository.

## Execution and reporting

The workflow runs on pushes to `main`, pull requests targeting `main`, and manual dispatch. Its JSON report and indexer stderr are uploaded as the `deslop-please-verigate-<run-id>` artifact for 14 days.

The CLI exit codes are:

- `0`: no architectural findings;
- `1`: architectural findings were reported;
- `2`: the scan could not complete because of a tool, indexer, or configuration error.

The scan step is explicitly advisory. Findings and scan-time errors do not block the existing Verigate CI jobs. Toolchain/indexer installation failures still fail the Architecture Audit workflow. The step summary distinguishes findings from execution errors; an execution error must never be treated as a clean scan.

No allowlist is configured, and the workflow never runs `--update-allow`. Existing findings remain visible for review instead of being silently baselined.

## Manual execution

On an Ubuntu 24.04 environment with Rust 1.99.0 and Node.js 22:

```bash
cargo install --git https://github.com/Bor4brn/deslop-please --rev cfabfb9ee417e150d5342e8ef0d6a0fe725cc9a0 --locked deslop-please
npm install --global --no-audit --no-fund @sourcegraph/scip-python@0.6.8 @sourcegraph/scip-typescript@0.5.2
deslop-please --language auto --json
```

The Python and TypeScript/JavaScript indexes are cached under the user's cache directory. The tool does not rewrite Verigate source files.

## Coverage limits

- Solidity contracts are not analyzed. The presence of Solidity files does not mean they were checked.
- The tool does not analyze Go code, so it does not cover Go-based projects such as OWNERA-Core.
- Python and plain JavaScript findings depend on what the SCIP indexer can resolve. Untyped/dynamically typed references may be absent from the model.
- JavaScript `field-leak` coverage is partial; the upstream documentation limits it to class-body fields.
- This is not a security audit. It does not check authorization invariants, contract vulnerabilities, cryptography, dependency CVEs, secrets, or runtime behavior.
- It does not replace Verigate's Python/contract/UI tests, security reviews, threat-model review, or live evidence requirements.

## Review policy

- Investigate findings in the context of Verigate's protocol-agnostic authorization core and adapter boundaries.
- Keep security-critical behavior unchanged unless a confirmed defect requires a focused fix with regression tests.
- Do not use blanket allowlists. Any necessary exception must be narrow, justified, and documented.
- Do not claim that Solidity or unsupported languages were scanned.

## Initial baseline — 2026-11-28

The first completed multi-language scan ran as [Architecture Audit run 46112311890](https://github.com/rudimentall1/verigate/actions/runs/46112311890) against source head `f0a830c3298e3523b9ddc68fc78798238b57af26`. It indexed the root Python project, root JavaScript project, nested Anna Executa Python project, and standalone verifier Python project.

The analyzer returned exit code `1` with **17 diagnostics**:

| Lint | Count | Initial locations |
|---|---:|---|
| `module-cycle` | 1 | Dependency cycle across `attest/`, `core/`, and `enforcement/` |
| `field-leak` | 11 | Receipt payload, authority/service state, Arc registry addresses, Anna client disabled-state fields, and related object boundaries |
| `wide-directory` | 4 | Repository root, `core/`, `enforcement/`, and `tests/` |
| `long-file` | 1 | `core/storage.py` — 2,172 lines |

These are structural diagnostics, not 17 confirmed defects. The `attest/core/enforcement` cycle needs a deliberate dependency-direction review because those modules sit on the authorization, evidence, and execution boundary. The 2,172-line storage module is a strong candidate for a separate, test-backed decomposition review, but it should not be split mechanically. Field-leak findings involving public immutable data or intentional read-only policy state may be acceptable; mutable state exposure deserves closer inspection.

The report and indexer stderr are available in [artifact 15249918282](https://github.com/rudimentall1/verigate/actions/runs/46112311890/artifacts/15249918282), retained by GitHub Actions for 14 days. The analyzer result is not clean. The workflow job is green only because findings are explicitly advisory. Solidity was not scanned.
