# Signal Sprint GDK MSIXVC2 SDK handoff (check-only)

Partner Center selection: **GDK game**. Signal Sprint only. The source branch
`codex/game-signal-sprint-undo-20261027` must remain at
`c058cbf7fe38e02d929c67d047d717ff74bd522e` until authorized CAS.
Request ID: `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e`.

## After the approved Identity CAS

Use the dedicated post-CAS Factory build branch, the original pinned EXE ZIP,
a reviewed Package Version and reserved display name, and a staging directory
with exactly the six reviewed files. Run the existing
`gdk_msixvc2_preflight.py` and save its JSON check-only receipt *outside*
the Factory checkout and staging directory. Then run:

```text
python gdk_sdk_pack_plan.py --factory-checkout <dedicated-build-checkout> --pinned-artifact-zip <original-zip> --cas-commit-sha <actual-cas-sha> --build-head-sha <actual-build-head> --staging-dir <six-file-staging> --package-version <reviewed-version> --reviewed-display-name <reviewed-name> --preflight-receipt <preflight-json> --output-dir <existing-empty-output-dir>
```

The command only prints JSON. It re-runs CAS ancestry, dedicated-branch history,
approved Identity, pinned ZIP and staging checks via the existing recheck,
then independently re-hashes the six staged files and checks output isolation.
It **does not execute** the GDK SDK or claim that a package exists.

On a Windows machine with the October 2026 GDK or later, an *authorized builder*
must run a **fresh** preflight and recheck immediately before invoking the
SDK. The proposed command shape is:

```text
makepkg.exe pack /msixvc2 /d <staging> /pc /pd <empty-output> /validationcritical
```

Do not add `/skipvalidation`, `upload`, or Partner Center authentication.
Capture SDK version, validation output, actual package path and SHA-256 as
separate real-build evidence. A successful unit test or check-only receipt
is not `REAL_MSIX_PASS` or `E2E PASS`. Installation/GUI QA belongs to the
Windows/E2E lane.

**Release gate (October 2026 GDK):** Microsoft now documents MSIXVC2 as
**generally available** and eligible for public-release certification.
The managed packaging tool is `makepkg.exe`; the temporary `makepkg2.exe`
name has been removed. This corrects the obsolete preview-era restriction.
A successful build still is **not** Store approval: require actual SDK
validation, real package SHA evidence, Windows install/GUI QA, and explicit
Partner Center certification. Do not silently switch Signal Sprint to ordinary
MSIX or an MSIX/PWA Partner Center listing. Do not run developer-mode registry
or policy changes as part of this cloud-side handoff.

Official references:
- https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/packaging/overviews/packaging-getting-started-for-pc-msixvc2?view=gdk-2604
- https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/packaging/deployment/makepkg?view=gdk-2604

No new game generation, actual CAS, Store submission, branch merge, or
Windows-all-auto central ledger mutation is performed by this handoff.
