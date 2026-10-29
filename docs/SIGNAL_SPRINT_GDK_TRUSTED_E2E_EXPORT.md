# Signal Sprint — independently anchored GDK E2E export

**Partner Center selection: GDK game.** This is the Signal Sprint GAME lane only. No CAS, SDK invocation, Store submission, central Windows-all-auto ledger edits or source changes.

## Why this additional gate is required

The older gdk_e2e_handoff.py checked the builder-provided plan, evidence and SDK output hashes, but did not require the independently trusted **prebuild handoff SHA-256**. An adversary able to replace the plan, SDK result and output together could manufacture an internally consistent handoff. gdk_e2e_trusted_export.py closes that gap by requiring the independent prebuild anchor before any transfer is created.

## Required sequence (after an authorized CAS and real Windows GDK build)

1. Obtain the original GDK SDK handoff JSON and its SHA-256 **from a trusted channel separate from the SDK result and transfer folder**. Never read the trusted hash from the untrusted transfer itself.
2. Keep the original pack-plan JSON, SDK result JSON, raw validation log and SDK package/sidecar output. The existing trusted intake checks all of these against the independent prebuild handoff and pinned source/EXE.
3. Run:

       python gdk_e2e_trusted_export.py \
         --sdk-handoff <prebuild-handoff.json> \
         --trusted-handoff-sha256 <independently-approved-sha256> \
         --pack-plan <plan.json> \
         --sdk-result-evidence <sdk-result.json> \
         --package-dir <sdk-output> \
         --validation-log <sdk-validation.log> \
         --output-dir <new-isolated-transfer-directory>

4. Only on exit code 0, hand the **new directory** and separately recorded handoff_manifest_sha256 to the Windows/E2E owner. The receiving owner must still independently run gdk_e2e_handoff_verify.py with that SHA obtained through a trusted channel.

The wrapper performs trusted_intake -> byte-preserving export -> local receiver verification, checks source/CAS/build identity and package/log/sidecar SHA continuity, and rehashes the independent anchor and evidence at the end. It never overwrites an existing transfer. **On any nonzero exit, do not consume the transfer directory even if one was created before a late verification failure.** Quarantine it and retry to a new destination only after investigating the mismatch.

## Status and remaining gates

Success status: GDK_TRUSTED_E2E_HANDOFF_CHECK_ONLY_PASS. The fields real_msix_pass, e2e_pass, gdk_sdk_validation_independently_verified and store_submitted always remain false. The separate Windows GDK SDK build, independent validation log review, install/GUI QA, and Store certification are not performed here.

Immutable source_sha: c058cbf7fe38e02d929c67d047d717ff74bd522e
Request ID: game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e
Approved Store ID: 9N21MJM7S57P (GDK_GAME, user supplied)
Package Version and reserved display name remain separate reviewed build gates. No Identity re-request.
