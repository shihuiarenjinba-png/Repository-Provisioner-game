# Signal Sprint — GDK SDK result intake (read-only)

**Partner Center selection: GDK game.** Signal Sprint only.
Immutable source SHA: c058cbf7fe38e02d929c67d047d717ff74bd522e.
Request ID: game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e.

## After an authorized Identity CAS and actual GDK build

An authorized Windows builder with October 2026 GDK or later must run a **fresh**
gdk_sdk_pack_plan.py preflight/recheck immediately before invoking the actual
makepkg.exe pack /msixvc2 ... /validationcritical command.

Save four inputs separately:
1. Original check-only pack-plan JSON.
2. SDK result evidence JSON (exact schema below).
3. Package output directory with exactly one real .msixvc or .msixvc2 file.
4. Raw SDK validation log outside the output directory.

Run (read-only; no GDK SDK invocation):

    python gdk_sdk_result_intake.py --pack-plan <plan.json> --sdk-result-evidence <sdk-result.json> --package-dir <package-output> --validation-log <sdk-validation.log>

The result JSON requires **exactly** these fields:

| Field | Value |
|---|---|
| schema_version | 1 |
| status | GDK_SDK_PACK_EXECUTED |
| partner_center_selection | GDK_GAME |
| package_format | MSIXVC2 |
| request_id, source_sha | Pinned Signal Sprint values from plan |
| cas_commit_sha, factory_head_sha | Actual post-CAS commit IDs from plan |
| package_version, reviewed_display_name | Exact reviewed values from plan |
| verified_receipt_sha256, staging_files_sha256 | Exact hashes from plan |
| sdk_command_argv | Exact nine-element command from plan |
| sdk_executable | makepkg.exe |
| sdk_version | Version observed by Windows builder |
| sdk_exit_code | 0 (builder claim; not independently trusted) |
| validation_log_sha256 | SHA-256 of actual SDK validation log |
| package_filename | Basename of one .msixvc/.msixvc2 output |
| package_sha256 | SHA-256 of actual package bytes |
| package_size_bytes | Actual package byte length |
| store_submitted | false |

Unexpected keys, duplicate JSON keys, wrong source/CAS/build correlations,
incorrect package/log SHA, symlinks, path traversal, extra output files,
altered SDK command lines and false Store-submission claims are rejected.
Original EXE SHA and six-file staging provenance remain enforced by the
existing preflight/recheck chain; do not rebuild or replace that EXE.

On success, status is GDK_PACKAGE_BYTES_AND_SDK_RECEIPT_CHECK_PASS.
gdk_sdk_validation_independently_verified=false, real_msix_pass=false,
e2e_pass=false, store_submitted=false are **always** returned.
The SDK result JSON is a builder claim, not a signed attestation.
Do not promote this to REAL_MSIX_PASS without independent SDK validation
and real Windows package inspection.

Hand the verified package bytes, SHA, raw log and evidence to the 36-minute
Windows/E2E owner for SDK log review, permitted installation/GUI QA and
separate release gate. Do not edit its central E2E ledger in this lane.

No new GAME, CAS, Store submission, main/release mutation, force push,
certificate-store or Code Integrity policy changes. Never switch to
ordinary MSIX/PWA Partner Center routing.
