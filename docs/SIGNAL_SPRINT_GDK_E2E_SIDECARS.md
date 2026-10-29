# Signal Sprint GDK SDK sidecar-preserving E2E handoff

**Partner Center selection: GDK game.** Signal Sprint only. This is not a Store upload, SDK attestation, CAS authorization, or E2E approval.

## Fixed provenance
- Source branch: `codex/game-signal-sprint-undo-20261027`
- Immutable source SHA: `c058cbf7fe38e02d929c67d047d717ff74bd522e`
- Request ID: `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e`
- Partner Center Identity: user-supplied GDK_GAME; do not infer Package Version or reserved display name.

## Contract

After an authorized CAS and a **real Windows GDK SDK** build, the read-only `gdk_sdk_result_intake.py` must first verify the entire output inventory, including any .ekb/.xml/.zip/.log/.json sidecars. `gdk_e2e_handoff.py` then copies the **same verified bytes** to a new isolated directory:

- `package.msixvc2`: the single package, preserving its SHA-256; original SDK filename is recorded in the manifest (the original can have a .msixvc suffix).
- `validation.log`: raw SDK validation log, preserving SHA-256.
- `sdk-sidecar-<original filename>`: every allowed sidecar, copied byte-for-byte and individually hashed.
- `handoff.json`: schema v2, containing `sdk_sidecars_sha256` (transferred basename to SHA-256), source/CAS/factory identity and package/log hashes. Zero sidecars is an empty object.

Before SDK output intake or receiver acceptance, every filename must be a portable Windows basename: no Win32 reserved devices (including CON/NUL/COM/LPT), alternate-data-stream colon, forbidden punctuation, control characters, trailing dot/space, or Unicode-normalization/case-insensitive collisions. This is deliberately stricter than a Linux filesystem to prevent E2E transfer aliasing or loss on Windows. Synthetic regression tests do not claim a real SDK build.\n\nNo other files, symlinks, or nested directories are allowed. Output is created once and never overwritten; a failed copy removes only that new handoff. The sender emits `handoff_manifest_sha256` **outside the transferred directory**.

The receiving owner invokes:

```sh
python gdk_e2e_handoff_verify.py --handoff-dir <isolated-transfer> --expected-manifest-sha256 <trusted-out-of-band-digest>
```

The expected SHA-256 **must** be obtained through a trusted channel separate from the transfer. The receiver accepts legacy schema v1 (exact three-file bundle, no sidecars) and schema v2 (strict sidecar inventory). It verifies every file against the independently anchored manifest and rejects added, missing, modified, linked or unsupported files.

**Do not infer `REAL_MSIX_PASS` or `E2E PASS` from this transfer check.** A Windows GDK SDK build, independent log inspection, allowed installation/GUI QA, and the separate release gate remain required. The 36-minute Windows/E2E owner handles the central ledger and queue; this GAME lane does not edit them. No source branch mutation, recompiled EXE substitution, merge, certificate store/policy changes, or Store submission.
