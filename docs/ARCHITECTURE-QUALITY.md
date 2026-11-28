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

## Cycle remediation — PR #88

The initial `module-cycle` diagnostic is addressed structurally in Draft PR [#88](https://github.com/rudimentall1/verigate/pull/88):

- `core/adversarial.py` was moved to `attest/adversarial.py`, next to signed execution-authority verification.
- `core/genesis_lifecycle.py` was moved to `application/genesis_lifecycle.py`, because it composes core services with `enforcement.router.ExecutionRouter`.
- API and test imports now use the owning layers. The old `core` modules were removed, without compatibility re-exports that would restore the reverse dependency.

The intended dependency direction is `attest -> core`, `enforcement -> attest/core`, and `application -> core/enforcement`. Core remains the protocol-agnostic domain/policy layer and must not import any of these higher layers.

The fixed source head passed [CI run #46115841371](https://github.com/rudimentall1/verigate/actions/runs/46115841371): 698 Python tests, 69/69 Anna UI tests, contracts, container/API-auth, and Linux Anna Executa 0.1.18 smoke all passed. A fresh architecture scan has not yet been observed because this workflow has not landed on `main`; the source-level import graph has been corrected, but do not claim a new analyzer report is zero-cycle until the workflow produces one.

## Second cycle review and expanded dependency-boundary remediation — 2026-11-28

The first remediation moved the obvious application orchestrator and adversarial harness, but the next completed analyzer run [#46116545770](https://github.com/rudimentall1/verigate/actions/runs/46116545770) still reported one cycle between `core` and `attest`. Its import evidence named `core/authorization.py` and `attest/authority_replay.py`. Source inspection also found `core/evidence.py` importing `attest.receipt`; that was another reverse dependency hidden by the package-level cycle summary.

The PR's expanded move set now assigns the modules to their owners:

- `core/authorization.py`'s concrete signer moved to `attest/authorization.py`. The remaining `core.authorization` module contains only the `AuthorizationArtifactIssuer` Protocol. `core.engine.GuardrailEngine` receives this port by injection; `application.engine.GuardrailEngine` supplies the attestation implementation at the composition boundary.
- Evidence graph construction and immutable graph snapshot service moved from `core` to `attest`.
- Historical authority replay and adversarial mutation checks stay in `attest`.
- Wallet enrollment and Genesis lifecycle orchestration stay in `application`.

Consumers in API, CMC adapter, Genesis workflow and tests were updated to import their owning packages. Old attestation/application modules were removed from `core`; no reverse-dependency shims were added.

**Current verification status:** the second analyzer result is not clean. The expanded source changes were pushed after that report, so a new architecture scan and full CI run on the current head are required before the remediation can be declared complete. The structural report still has 11 field-leak, 4 wide-directory and 1 long-file diagnostics in addition to the single cycle; those other diagnostics have not been treated as defects or automatically rewritten.

### Remaining cycle edge — portable proof verification

The current-head analyzer run [#46120175666](https://github.com/rudimentall1/verigate/actions/runs/46120175666) narrowed the remaining cycle to `core/offline_verifier.py -> attest.receipt`, with the reverse `attest/authority_replay.py -> core`. This is not a reason to invert the attestation import. Offline verification and portable proof-package serialization are attestation responsibilities, so both files moved together:
- `core/offline_verifier.py` → `attest/offline_verifier.py`
- `core/proof_package.py` → `attest/proof_package.py`

Callers in CLI, Genesis lifecycle, and tests now import from `attest`. A fresh analyzer report for the new head is pending; do not report the cycle as resolved until it confirms no `module-cycle` diagnostic.

### Outcome attestation was the final reverse edge — 2026-11-28

The latest completed analyzer report [#46121019285](https://github.com/rudimentall1/verigate/actions/runs/46121019285) still reported one cycle. The complete JSON artifact identified the exact pair:
- `core/outcome.py:507` imports `verify_execution_authorization` and `verify_execution_receipt` from `attest.receipt`.
- `attest/authority_replay.py` imports core authority models and services.

Outcome claim signing, attestor authority verification, and stored outcome-attestation validation belong in the attestation layer. The service moved to `attest/outcome.py`. The two reusable lower-level items that core also needs — `ATTESTOR_TYPES` and the Ed25519 `key_fingerprint()` helper — were extracted into dependency-free `core/attestor_types.py`. Core attestor governance and application wallet enrollment now import that helper module, not the outcome service. API, Genesis lifecycle, evidence graph, chain worker, E2E script and tests were updated to use `attest.outcome`.

The move preserves claim fields, signature canonicalization, attestor governance replay, storage behavior, authority-event writes and EVM chain-verifier checks. The old `core/outcome.py` module was removed rather than kept as a compatibility re-export, which would have recreated the cycle.

A new architecture scan and full CI run for the current HEAD are pending. The previous report #46121019285 is not a clean report and must not be used to claim zero cycles.

### Final remaining cycle edge — submission ingestion — 2026-11-28

The current-head analyzer report [#46122297534](https://github.com/rudimentall1/verigate/actions/runs/46122297534) showed one remaining cycle:
- `core/submission_ingest.py` imports `verify_execution_authorization` and `verify_execution_receipt` from `attest.receipt`.
- `attest/authority_replay.py` depends on core authority models.

`ExecutionSubmissionService` is an application workflow: it validates an enrolled Anna installation wallet, verifies the issuer-signed authorization and wallet receipt, checks the exact submitted EVM transaction fields, then persists the external submission. It moved to `application/submission_ingest.py`; the API and its tests now import the application module. The old core module was deleted. Request/response shapes, enrollment lookups, signing-time TTL validation, idempotency, persistence and chain-verifier behavior are unchanged.

A new architecture scan and full CI run for the final head are pending. The previous report still had one cycle and must not be used as evidence that the final cycle is gone.

### Final result — zero module cycles — 2026-11-28

The last reverse edge was removed by moving `core/submission_ingest.py` to `application/submission_ingest.py`. The service verifies the enrolled wallet and signed authorization/receipt, checks the exact submitted transaction, then persists the external submission. Its old core module was deleted and the API/test imports were updated.

On exact final implementation HEAD `4f0bd4020658e020a5df6256fa2429d1c4a0b103`:
- Architecture audit [#46122668412](https://github.com/rudimentall1/verigate/actions/runs/46122668412): **zero `module-cycle` diagnostics**. Remaining advisory categories: 11 field-leak, 4 wide-directory, 1 long-file.
- Full CI [#46122668307](https://github.com/rudimentall1/verigate/actions/runs/46122668307): **699 Python tests passed**; 69/69 Anna UI E2E; contracts/Arc Registry; container/API-auth; Linux Anna Executa 0.1.18 build and binary smoke all passed.
- Anna binary smoke reported: signed ALLOW, one-time App approval consumed once, wallet hand-off consumed once, submitted receipt persisted and verified.

The remaining field and size diagnostics were not auto-fixed: review their evidence individually. In particular, receipt payload and domain data carriers are public protocol objects, and a wide test directory or a 2172-line SQLite storage module should be decomposed based on ownership/behavior, not to game an advisory counter.

### Documentation-head revalidation — 2026-11-28

The PR's documentation/checkpoint commits after the final code change were also revalidated on exact latest PR HEAD `83dc32eab7113507e29762fd2093c5820c7a3139`:
- Architecture Audit [#46122891729](https://github.com/rudimentall1/verigate/actions/runs/46122891729): still **zero module-cycle diagnostics**. Remaining advisories are 11 field-leak, 4 wide-directory, and one long-file finding.
- Full CI [#46122891728](https://github.com/rudimentall1/verigate/actions/runs/46122891728): **699 Python tests**; 69/69 Anna UI tests; contracts, container/API-auth, and Linux Anna Executa 0.1.18 build + binary smoke all passed.
