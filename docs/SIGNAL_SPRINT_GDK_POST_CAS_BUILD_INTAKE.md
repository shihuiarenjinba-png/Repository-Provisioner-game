# Signal Sprint GDK post-CAS build intake (read-only)

This is **only** for the existing Signal Sprint product. Do not generate another game, change the immutable source commit, invent Store Identity, or use the generic Factory MSIX export. The registered packaging family is **GDK**; a real GDK MSIXVC/MSIXVC2 build and its version gate are separate.

## Frozen inputs

- Factory repository: `shihuiarenjinba-png/AI-Game-Factory`
- Original source branch: `codex/game-signal-sprint-undo-20261027`
- Immutable source SHA: `c058cbf7fe38e02d929c67d047d717ff74bd522e`
- Request ID: `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e`
- Original GitHub Artifact: `12706862577`, ZIP SHA-256 `e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412`
- Internal `SignalSprint.exe` SHA-256: `9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad`
- Artifact expires **2026-11-01 03:18:51 UTC**. Preserve the exact ZIP bytes; a rebuild is not a replacement.

## Preconditions

1. Provisioner PR #10 check-only validates the reviewed GDK Identity and original pinned EXE.
2. An explicitly approved Provisioner CAS returns `approved-identity.json` to the original Factory source branch. Do **not** run CAS merely because this script exists.
3. Record the actual CAS commit SHA, not a guessed value. The CAS commit must have the immutable source SHA as its **direct parent**, and must change **only** `products/signal-sprint/store/approved-identity.json`.
4. Create a **separate** post-CAS GDK build branch at/after that CAS commit. Check it out locally. Do not re-run Factory source generation or rebuild the original EXE.

## Check-only command (after CAS)

```bash
python gdk_build_intake.py \
  --factory-checkout /path/to/AI-Game-Factory-post-cas-checkout \
  --pinned-artifact-zip /path/to/signal-sprint-factory-exe-c058cbf7.zip \
  --cas-commit-sha ACTUAL_40_HEX_CAS_COMMIT \
  --build-head-sha ACTUAL_40_HEX_BUILD_BRANCH_HEAD
```

This script performs **no GitHub writes, package builds, Store submissions or Identity retrieval**. It verifies the checked-out Git HEAD, CAS parent, ancestry, single-file CAS change, approved Identity at CAS and build HEAD, and exact ZIP/EXE SHA, CRC, provenance and request ID. It emits a machine-readable JSON result with `status=GDK_BUILD_INPUT_CHECK_ONLY`, `next_stage=BUILD_GDK_MSIXVC_FROM_PINNED_EXE`, separate `source_sha`, `cas_commit_sha`, `factory_head_sha`, and `package_version=null`.

The returned JSON is **not** a Windows-all-auto QA receipt and is **not** a real MSIXVC. The Windows/GDK builder must separately choose a reviewed package version, use the pinned executable bytes, produce a real MSIXVC/MSIXVC2, validate its package contents and launch path, and only then hand off the actual package hash to the Windows-all-auto owner (36-minute lane). No central queue or ledger is edited here.

## Remaining blockers

- Actual Signal Sprint CAS return has not been performed.
- Factory PR #11 remains generic MSIX-only; GDK build/handoff must not be routed through it unchanged.
- No real GDK MSIXVC/MSIXVC2, install test, GUI QA or Store approval has been demonstrated.
- CI green validates this contract, not product E2E.
