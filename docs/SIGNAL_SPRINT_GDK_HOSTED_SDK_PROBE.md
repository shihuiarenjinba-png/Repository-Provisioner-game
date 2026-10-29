# Signal Sprint — hosted Windows GDK SDK availability evidence

Partner Center selection: **GDK game**. This workflow is a read-only environment capability probe, not a build, SDK approval, CAS operation, or Store upload.

## Purpose

The Windows GDK makepkg runner is implemented, but local Windows is temporarily unavailable. The new workflow records whether the GitHub-hosted `windows-latest` runner can find `makepkg.exe` **on PATH**. It records an observational SHA-256 if found, the runner image metadata, and the presence of four known GDK environment hints. It never runs makepkg, downloads a GDK SDK, creates a package, retrieves Identity, or changes the immutable Factory source.

The JSON artifact `signal-sprint-gdk-sdk-environment-probe` has `status=MAKEPKG_ON_PATH_UNAPPROVED` or `MAKEPKG_NOT_ON_PATH`. The latter means only that the executable was not discoverable on PATH; it **does not prove the SDK is absent**. The former is not SDK approval: the observed hash must be reviewed against a trusted SDK installation source independently before a real run. This probe deliberately never sets `CAS_RETURN_PASS`, `REAL_MSIX_PASS`, or `E2E PASS`.

## Next action by result

- `MAKEPKG_ON_PATH_UNAPPROVED`: independently confirm GDK SDK licensing/install provenance and approve the exact makepkg executable hash before any `--execute` use. Real packaging still requires CAS, a dedicated post-CAS build branch, reviewed display name and package version, and fixed ZIP/EXE byte checks.
- `MAKEPKG_NOT_ON_PATH`: do not mark the game blocked by Identity. Use an authorized Windows machine with the GDK installed later, or investigate a compliant hosted Windows setup; do not auto-download an unapproved SDK or treat a Windows CI PASS as a GDK build.
- Workflow failure: inspect the Actions log and preserve the prior build state. Do not mark the game ready.

No external SaaS, server, new game, main/release write, force push, merge, or Partner Center action is involved. The 36-minute Windows/E2E owner retains the central ledger/queue.
