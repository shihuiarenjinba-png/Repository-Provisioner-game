# Signal Sprint — ephemeral hosted GDK SDK bootstrap

**Partner Center selection: GDK game** (GDK_GAME, MSIXVC2). Signal Sprint only.

## Why

The October 29 hosted Windows probe did not find makepkg.exe. The Microsoft public GDK project documents installation via `winget install Microsoft.Gaming.GDK`, while Microsoft's October 2026 GDK packaging documentation requires the managed `makepkg.exe` for MSIXVC2. This is an **optional cloud-only preparation route**, not a substitute for an approved SDK or actual CAS.

References:
- https://github.com/microsoft/GDK
- https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/packaging/overviews/packaging-getting-started-for-pc-msixvc2?view=gdk-2604
- https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/packaging/deployment/makepkg?view=gdk-2604

## Safe workflow

`.github/workflows/signal-sprint-gdk-hosted-bootstrap.yml` on its development branch performs **probe-only** on push. It checks for WinGet and, when available, performs a **read-only** `winget show --id Microsoft.Gaming.GDK --exact --versions --source winget` catalog query. It does not install or execute any GDK tool. The artifact is `signal-sprint-gdk-hosted-sdk-bootstrap`. The JSON fields `catalog_query_status` and `unapproved_version_candidates` distinguish an unavailable catalog from candidate version strings. **Catalog versions are unapproved hints, not a version pin, an SDK installation, or a trusted makepkg.exe digest.** The probe reports both April 2026 (`2604.x`) and October 2026 (`2610.x`) candidates, with a separate `unapproved_2610_candidates` field. This is discovery only: the installation gate still requires an independently approved `2610.x` pin and SHA-256. The first live read-only probe on October 30 (Actions run `40928168484`) returned `NO_2610_CANDIDATES`; this does **not** prove the public catalog has no supported earlier SDK. Query failure must not be treated as evidence that the SDK is unavailable.

## Preview vs retail SDK catalog decision (October 30, 2026)

Microsoft's current MSIXVC2 packaging documentation distinguishes **April 2026 GDK 2604 preview**, which uses `makepkg2.exe` and cannot be treated as retail certification-ready, from **October 2026 GDK 2610 general availability**, which uses managed `makepkg.exe`. This bootstrap intentionally accepts **only an independently approved 2610.x** SDK for its retail-oriented install gate; do not substitute 2604.x simply because WinGet lists it.

Read-only probe JSON now exposes `unapproved_2604_candidates`, `unapproved_2610_candidates`, `preview_2604_catalog_status`, `retail_2610_catalog_status`, and `retail_msixvc2_sdk_approved=false`. The candidate output is capped at 50 versions **per release family after classification**, rather than globally before classification, so a long 2604 list cannot conceal an available 2610 candidate. Versions use numeric component ordering. The catalog remains unapproved evidence only. A successful query with only 2604 versions means `retail_2610_catalog_status=NOT_LISTED`; a failed or unavailable query means `UNKNOWN`, **not** proof of absence. Even if 2610 appears, `CANDIDATE_UNAPPROVED` is not permission to install, build, or submit. The independent SDK executable digest and explicit install authorization remain mandatory.

Authoritative references:
- https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/packaging/overviews/packaging-getting-started-for-pc-msixvc2
- https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/packaging/overviews/packaging-msixvc2-overview

A later **manual** workflow_dispatch on a branch containing this workflow (GitHub generally requires a workflow on the default branch for manual dispatch) may set:
- `install_sdk=true`
- `sdk_version` = an independently reviewed exact **2610.x** GDK package version
- `approved_makepkg_sha256` = an independently approved 64-character digest of the exact expected `makepkg.exe`, obtained outside the install output

WinGet discovery searches **only absolute PATH directories** (not the working directory or relative PATH entries), refuses checkout-local executables, and fails closed when multiple distinct `winget.exe` candidates exist. A successful WinGet probe does **not** approve an SDK version or `makepkg.exe` digest.

The helper refuses installation unless running on GitHub-hosted Windows with `CI=true`, `GITHUB_ACTIONS=true`, `RUNNER_OS=Windows`, `RUNNER_ENVIRONMENT=github-hosted`. It additionally checks `GITHUB_EVENT_NAME=workflow_dispatch` and `INSTALL_REQUESTED=true` **inside the Python installer**; a push or PR event cannot install even if a workflow accidentally supplies a version and digest. Supplying both `--probe-versions` and `--install` fails closed. Three negative regression tests cover these cases. This is defense in depth, not a replacement for independent SDK hash approval. It runs only `winget install --id Microsoft.Gaming.GDK --exact --version ... --source winget --silent` with agreement flags. The installed executable must be unambiguously discovered and SHA-256-matched. Installer success alone never counts as approval.

**Current limitation:** The October 2026 package version and independent makepkg.exe digest have not been approved. Do not dispatch install with guessed values. WinGet may not be present or work on the GitHub-hosted Windows image; this route must be tested before being relied on. No automatic installation is authorized by a push or PR. The current PR remains Draft and unmerged.

A successful hosted bootstrap means only `GDK_HOSTED_SDK_BYTES_APPROVED_NO_BUILD`, not `POST_IDENTITY_READY`, `CAS_RETURN_PASS`, `REAL_MSIX_PASS` or `E2E PASS`. No real package can be produced until actual authorized CAS, post-CAS build checkout, reviewed reserved display name and package version, preserved fixed EXE ZIP, and the full independent GDK handoff gate pass. SDK installation does not imply certification.

The immutable source SHA is `c058cbf7fe38e02d929c67d047d717ff74bd522e`; request ID is `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e`. Neither is modified. The approved user-provided Store ID is `9N21MJM7S57P`. No new GAME, source mutation, local security changes, Partner Center login, Identity retrieval, Store upload, main/release write, merge or central E2E ledger edit.

## 2026-10-30 live hosted WinGet catalog re-probe (Draft #38)

The active Signal Sprint Draft branch now triggers the **read-only** hosted Windows
catalog probe on changes to the probe workflow or SDK discovery/bootstrap code.
Push-triggered jobs cannot install the SDK (the Python install gate requires
explicit manual workflow_dispatch plus independent SDK version and makepkg SHA).

- Workflow run: https://github.com/shihuiarenjinba-png/Repository-Provisioner-game/actions/runs/41032064494 (SUCCESS, 2026-10-30 UTC).
- `winget_available=true`, `catalog_query_status=CANDIDATES_FOUND`.
- Observed **unapproved** 2604 versions: `2604.0.7822`, `2604.1.7839`, `2604.2.7849`, `2604.3.7874`, `2604.4.7897`, `2604.5.7903`.
- `unapproved_2610_candidates=[]`, `retail_2610_catalog_status=NOT_LISTED` in this specific WinGet source at probe time.
- `sdk_installed_by_this_run=false`, `makepkg_executed=false`, `real_msix_pass=false`.

**Decision:** This is not evidence that 2610 is unavailable from every Microsoft
channel. It does establish that the tested hosted WinGet catalog cannot yet
supply a reviewed 2610 SDK version pin. Keep the MSIXVC2 retail build gate
closed until an official 2610+ installer and independently approved
`makepkg.exe` SHA-256 are available. Do not substitute preview 2604 or guess a
digest. The source SHA and original EXE artifact remain immutable.
