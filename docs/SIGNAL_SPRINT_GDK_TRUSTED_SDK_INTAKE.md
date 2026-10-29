# Signal Sprint GDK — independently anchored SDK intake

**Partner Center selection: GDK game.** Signal Sprint only. The immutable
Factory source remains `c058cbf7fe38e02d929c67d047d717ff74bd522e`.
No new game, CAS, SDK invocation, Store operation, source movement or central
Windows-all-auto ledger edit is performed by this tool.

## Why this gate exists

`gdk_sdk_result_intake.py` already checks real package and log bytes against
the builder's SDK result JSON and a pack plan. But the plan and result can both
be replaced in the same transfer. This tool additionally binds them to the
**prebuild** `GDK_SDK_HANDOFF_CHECK_ONLY` receipt and requires its **raw file
SHA-256** from a separate, trusted channel.

**Do not read the trusted digest from the same ZIP, directory, handoff.json,
pack-plan.json, sdk-result.json, or untrusted message as the files being
verified.** A digest carried beside the files provides no authenticity.

## Procedure (after an authorized CAS and Windows GDK SDK build)

1. Produce the original check-only handoff using
   `gdk_sdk_handoff_gate.py`. Preserve its exact JSON bytes outside the SDK
   output folder. Before transferring anything, calculate its SHA-256 and
   record that digest through a separately trusted GitHub/owner-controlled
   channel. The JSON's canonical `sdk_pack_plan_sha256` is **different**
   from the raw handoff file SHA-256.
2. Save the exact `GDK_SDK_PACK_PLAN_CHECK_ONLY` JSON used for the actual
   Windows SDK execution, the builder's SDK result JSON, the real package
   output directory and the original validation log.
3. On the receiver, supply the independently trusted raw handoff digest:

```text
python gdk_sdk_trusted_intake.py --sdk-handoff <prebuild-handoff.json> --trusted-handoff-sha256 <SHA256-from-independent-channel> --pack-plan <pack-plan.json> --sdk-result-evidence <sdk-result.json> --package-dir <one-package-output-dir> --validation-log <validation.log>
```

This checks the independent raw SHA-256, the exact handoff schema, pinned
source and original EXE/ZIP hashes, prebuild false flags, the canonical
pack-plan digest, all cross-document CAS/build/version/display/staging/SDK
command correlations, and the existing byte-level package/log intake. It
rehashes the handoff and pack plan again after the intake to reject concurrent
changes.

**Interpretation:** `GDK_TRUSTED_PREBUILD_TO_PACKAGE_BYTES_CHECK_PASS` means
the transferred package/log bytes and builder claims are tied to the
independently pinned prebuild inputs. It does **not** prove the SDK genuinely
executed, the validation log is authentic, the package is installable, or
that Microsoft certified the game. `gdk_sdk_validation_independently_verified`,
`real_msix_pass`, `e2e_pass`, and `store_submitted` remain false.
The 36-minute Windows/E2E owner must independently verify SDK execution and
install/GUI QA. Do not report `REAL_MSIX_PASS` or `E2E PASS` from this gate.

The Microsoft Partner Center Identity supplied on 2026-10-28 remains
user-provided, not a reason to repeat WAITING_USER_IDENTITY. The reviewed
reserved display name and package version are separate downstream build-gate
inputs; neither may be invented.

This code is read-only and does not change Windows certificate stores,
Code Integrity, SmartScreen or developer-mode policies.
