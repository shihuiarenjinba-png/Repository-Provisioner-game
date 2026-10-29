# Signal Sprint — ephemeral hosted GDK SDK bootstrap

**Partner Center selection: GDK game** (GDK_GAME, MSIXVC2). Signal Sprint only.

## Why

The October 29 hosted Windows probe did not find makepkg.exe. The Microsoft public GDK project documents installation via `winget install Microsoft.Gaming.GDK`, while Microsoft's October 2026 GDK packaging documentation requires the managed `makepkg.exe` for MSIXVC2. This is an **optional cloud-only preparation route**, not a substitute for an approved SDK or actual CAS.

References:
- https://github.com/microsoft/GDK
- https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/packaging/overviews/packaging-getting-started-for-pc-msixvc2?view=gdk-2604
- https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/packaging/deployment/makepkg?view=gdk-2604

## Safe workflow

`.github/workflows/signal-sprint-gdk-hosted-bootstrap.yml` on its development branch performs **probe-only** on push. It checks for WinGet but does not install or execute any GDK tool. The artifact is `signal-sprint-gdk-hosted-sdk-bootstrap`.

A later **manual** workflow_dispatch on a branch containing this workflow (GitHub generally requires a workflow on the default branch for manual dispatch) may set:
- `install_sdk=true`
- `sdk_version` = an independently reviewed exact **2610.x** GDK package version
- `approved_makepkg_sha256` = an independently approved 64-character digest of the exact expected `makepkg.exe`, obtained outside the install output

The helper refuses installation unless running on GitHub-hosted Windows with `CI=true`, `GITHUB_ACTIONS=true`, `RUNNER_OS=Windows`, `RUNNER_ENVIRONMENT=github-hosted`. It runs only `winget install --id Microsoft.Gaming.GDK --exact --version ... --source winget --silent` with agreement flags. The installed executable must be unambiguously discovered and SHA-256-matched. Installer success alone never counts as approval.

**Current limitation:** The October 2026 package version and independent makepkg.exe digest have not been approved. Do not dispatch install with guessed values. WinGet may not be present or work on the GitHub-hosted Windows image; this route must be tested before being relied on. No automatic installation is authorized by a push or PR. The current PR remains Draft and unmerged.

A successful hosted bootstrap means only `GDK_HOSTED_SDK_BYTES_APPROVED_NO_BUILD`, not `POST_IDENTITY_READY`, `CAS_RETURN_PASS`, `REAL_MSIX_PASS` or `E2E PASS`. No real package can be produced until actual authorized CAS, post-CAS build checkout, reviewed reserved display name and package version, preserved fixed EXE ZIP, and the full independent GDK handoff gate pass. SDK installation does not imply certification.

The immutable source SHA is `c058cbf7fe38e02d929c67d047d717ff74bd522e`; request ID is `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e`. Neither is modified. The approved user-provided Store ID is `9N21MJM7S57P`. No new GAME, source mutation, local security changes, Partner Center login, Identity retrieval, Store upload, main/release write, merge or central E2E ledger edit.
