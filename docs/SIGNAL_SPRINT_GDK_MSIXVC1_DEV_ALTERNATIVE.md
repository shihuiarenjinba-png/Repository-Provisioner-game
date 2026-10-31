# Signal Sprint — optional GDK MSIXVC1 development plan

**Partner Center selection: GDK game.** This is an **explicitly selected,
development-only alternative**, not an automatic fallback from MSIXVC2.
The original Factory source ref remains pinned at
`c058cbf7fe38e02d929c67d047d717ff74bd522e`.
The original EXE bytes, GDK Identity, and request ID are unchanged.

## Why this exists

On 2026-10-31, the public Microsoft GDK release catalog and observed hosted
WinGet catalog showed 2604 releases but no confirmed 2610 retail release.
MSIXVC2 is a preview in the April 2026 GDK (2604) and public certification
is blocked in preview; GA starts with the October 2026 GDK (2610).
**Legacy GDK MSIXVC1** is a separate supported format, so a developer can
prepare its pack command while waiting for MSIXVC2 GA.

Microsoft's official `makepkg` documentation states that `/msixvc2` opts
into MSIXVC2; omitting the flag produces MSIXVC. It also states that final
XVC/MSIXVC submissions normally require `/l` or `/lk` encryption.
This plan deliberately omits both: **its output, if later built, is for
development/QA only and must never be passed off as a Store-ready package**.

Sources:
- https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/packaging/deployment/makepkg
- https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/packaging/overviews/packaging-msixvc2-overview

## Prerequisites

1. A **real, authorized** Identity-only CAS commit on
   `codex/game-signal-sprint-gdk-cas-c058cbf7fe38` with the pinned immutable
   source as its only parent. Do not create it as part of this plan.
2. An independent post-CAS build checkout and matching Factory gate.
3. The original byte-for-byte ZIP, reviewed package version and display name,
   exact six-file GDK staging inventory, and first-pass preflight receipt.
4. The existing `gdk_sdk_pack_plan.make_pack_plan` must pass **all** of its
   strict source/CAS/Identity/provenance/staging/output checks. No shortcut.
5. A separately reviewed official GDK SDK and executable digest are required
   before **any** actual SDK execution. No SDK install or execution is
   authorized by this document.

## Read-only invocation

```bash
python gdk_msixvc1_dev_pack_plan.py \
  --factory-checkout /path/to/approved-post-cas-build-checkout \
  --pinned-artifact-zip /path/to/original-signal-sprint.zip \
  --cas-commit-sha ACTUAL_CAS_SHA \
  --build-head-sha ACTUAL_BUILD_SHA \
  --staging-dir /path/to/reviewed-gdk-staging \
  --package-version REVIEWED_A.B.C.0 \
  --reviewed-display-name "REVIEWED_NAME" \
  --preflight-receipt /path/to/receipt.json \
  --output-dir /path/to/empty-gdk-output
```

Successful check-only status: `GDK_MSIXVC1_DEV_PACK_PLAN_CHECK_ONLY`.
The unexecuted command is:

```text
makepkg.exe pack /d <reviewed_staging> /pc /pd <empty_output> /validationcritical
```

This command is **not** executed by the script. Do not add `/skipvalidation`,
`upload`, `/l`, or `/lk` without an independent build and security review.
For retail MSIXVC1 packaging, review the appropriate encryption choice,
regenerate an authorized package and validate it independently. The current
`gdk_windows_sdk_runner.py` and `gdk_sdk_result_intake.py` remain
**MSIXVC2-only** and must **not** consume this MSIXVC1 plan as a real package
receipt. Format-specific runner/intake and Windows install/GUI QA would need
separate implementation and review before REAL_MSIX_PASS.

## State boundaries

This plan does not imply `POST_IDENTITY_READY`, `CAS_RETURN_PASS`,
`REAL_MSIX_PASS`, or `E2E PASS`. It does not change the canonical MSIXVC2
route or select MSIXVC1 for retail. No Partner Center access, Store action,
new GAME, Factory source mutation, SDK install, CAS, merge, or central ledger
write is performed.
