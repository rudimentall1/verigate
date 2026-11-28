# Verigate package dependency boundaries

**Status:** source-level dependency-cycle remediation implemented in PR #88.  
**Date:** 2026-11-28.

## Intended dependency direction

Verigate uses four logical layers:

- `core` owns protocol-agnostic domain models, identity/capability/policy evaluation, authority state, evidence primitives, and proof construction. It must not import higher-level attestation, execution, API, or application orchestration packages.
- `attest` owns signed decision receipts, executable authorization artifacts, cryptographic verification, and adversarial checks of those artifacts. It may depend on core domain primitives.
- `enforcement` owns the execution router, one-time execution gate, chain/tool adapters, and effect verification. It may depend on core contracts and attestation verification.
- `application` owns workflows that compose core services with enforcement adapters. It is the correct home for end-to-end lifecycle orchestration.

The intended graph is:

```text
             application
              /       \
             v         v
           core <---- enforcement
             ^          |
             |          v
             +------- attest
```

More precisely, `attest -> core`, `enforcement -> attest/core`, and `application -> core/enforcement`. There must be no reverse dependency from `core` to `attest` or `enforcement`.

## Cycle found by the initial architecture scan

The initial scan [Architecture Audit #46112311890](https://github.com/rudimentall1/verigate/actions/runs/46112311890) reported one module cycle across `attest`, `core`, and `enforcement`. Its import evidence identified two misplaced modules inside `core`:

- `core/adversarial.py` imported `attest.receipt.verify_execution_authorization`. This is an adversarial verification harness for signed execution-authority artifacts, not a core domain primitive.
- `core/genesis_lifecycle.py` imported `enforcement.router.ExecutionRouter`. This is a high-level application workflow that composes the engine, enforcement router, outcome service, evidence graph, and proof package.

Together with the natural lower-level edges `attest -> core` and `enforcement -> attest/core`, those imports made the dependency graph cyclic.

## Remediation in PR #88

- Moved `core/adversarial.py` to `attest/adversarial.py`. The API route remains `POST /v1/verify/adversarial`; only its internal import changed.
- Moved `core/genesis_lifecycle.py` to `application/genesis_lifecycle.py`. The `GenesisLifecycle` class and lifecycle behavior were preserved; the import in `tests/test_genesis_lifecycle.py` changed to the application layer.
- Removed the old modules from `core`. No compatibility re-export was added, because a re-export that imports the higher-level package would recreate the dependency edge this change removes.
- Kept the Genesis demo entry point unchanged: it still runs `tests.test_genesis_lifecycle.GenesisLifecycleTest.test_full_genesis_lifecycle_reuses_enforcement_and_proof_boundaries`.

No changes were made to Ed25519 canonicalization/signatures, DecisionReceipt or ExecutionAuthorization fields, expiry checks, capability/identity bindings, nonce consumption, replay protection, adapter contracts, or side-effect ordering.

## Verification

The test-first import-only commit was checked by [CI run #46115786079](https://github.com/rudimentall1/verigate/actions/runs/46115786079). It failed as expected because the new module paths did not exist yet; the test loader and Genesis demo showed the missing imports.

After the module moves, [CI run #46115841371](https://github.com/rudimentall1/verigate/actions/runs/46115841371) passed all four jobs:

- Full Python suite: **698 tests**.
- Anna UI E2E: **69/69**.
- Contracts and Arc Authority Registry checks.
- Container/API-auth checks.
- Linux Anna Executa 0.1.18 build and smoke test.

The initial architecture scan's cycle evidence is addressed by removing the two `core -> attest` and `core -> enforcement` edges. **A fresh automated architecture scan has not yet been observed**: the Architecture Audit workflow is introduced by separate Draft PR #87 and is not yet available on the default branch. Do not describe the analyzer as having re-reported zero cycles until a fresh report exists.
