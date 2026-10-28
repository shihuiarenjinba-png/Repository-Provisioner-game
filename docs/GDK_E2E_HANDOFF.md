# Signal Sprint GDK MSIXVC2 → Windows/E2E byte handoff

**Partner Center selection: GDK game.** This is a *read-only, post-SDK*
transport boundary for the single pinned Signal Sprint request, not a Microsoft
Store submission, ordinary APP MSIX handoff, or Windows-all-auto central ledger
mutation. The user-provided Partner Center Identity is already received.

## Prerequisites

1. Authorized post-CAS **dedicated build branch**, with actual CAS and build
   commit SHAs verified by the existing branch-history gate. The immutable
   Factory source branch remains at
   `c058cbf7fe38e02d929c67d047d717ff74bd522e`.
2. Original pinned EXE/ZIP bytes verified by `gdk_msixvc2_recheck.py` and
   `gdk_sdk_pack_plan.py`; no silent rebuild of the EXE.
3. Windows builder independently checks installed October 2026-or-later GDK,
   rechecks the staged files and executes the approved
   `makepkg.exe pack /msixvc2 ... /validationcritical` command.
4. SDK output contains exactly one package. Raw validation log and strict
   SDK-result evidence are outside the SDK output folder.
5. `gdk_sdk_result_intake.py` checks claimed SDK result and actual package/log
   bytes; **this does not independently authenticate SDK success**.

## Export

Run from Repository-Provisioner-game root on the authorized builder after the
above prerequisites, with paths replaced by real operator-controlled paths:

```powershell
python gdk_e2e_handoff.py `
  --pack-plan C:\\qa\\gdk\\pack-plan.json `
  --sdk-result-evidence C:\\qa\\gdk\\sdk-result.json `
  --package-dir C:\\qa\\gdk\\sdk-output `
  --validation-log C:\\qa\\gdk\\validation.log `
  --output-dir C:\\qa\\gdk\\handoff
```

The parent of `--output-dir` must exist, and the destination itself must
**not** exist. This avoids overwriting or mixing a previous attempt. The
exporter re-runs byte intake, pins the source/evidence hashes, copies the
original SDK-produced bytes without rebuilding them, verifies copied bytes,
and creates exactly:

- `package.msixvc2` — copied GDK package (SHA-256 and size in manifest)
- `validation.log` — copied raw SDK log (SHA-256 in manifest)
- `handoff.json` — `GDK_E2E_QA_INTAKE_PENDING` with immutable request,
  source/CAS/build refs, GDK routing, Store ID, version, SDK claim and hashes

**The manifest always records** `real_msix_pass=false`,
`e2e_pass=false`, `store_submitted=false`, and
`gdk_sdk_validation_independently_verified=false`. No file is uploaded to
Store, no central Windows-all-auto queue is written, and no CAS is attempted.

## Windows/E2E owner follow-up

The 36-minute Windows/E2E owner must independently re-hash the transferred
package and log; verify official GDK SDK output/validation, package identity
and version, package install/uninstall, GUI/playability, security and Store
certification gates; and then decide its own pass/fail. Never translate
`GDK_E2E_QA_INTAKE_PENDING` to `REAL_MSIX_PASS` automatically. Do not route
this to ordinary MSIX or PWA game workflows.

## Local no-SDK regression

```bash
python -m unittest discover -s tests -p 'test_gdk_e2e_handoff.py' -v
```

The tests deliberately use **synthetic** package bytes and synthetic logs.
Passing these tests is not evidence that an actual GDK package exists.
