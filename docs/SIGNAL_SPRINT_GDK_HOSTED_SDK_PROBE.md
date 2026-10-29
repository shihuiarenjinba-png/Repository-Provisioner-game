# Signal Sprint — hosted Windows GDK SDK availability evidence

Partner Center selection: **GDK game**. Read-only capability probe; no SDK installation, SDK execution, CAS, or Store operation.

## What the probe now measures

The initial 2026-10-29 run reported MAKEPKG_NOT_ON_PATH. That proved only PATH discovery failed. This second probe also checks known installed locations: GameDK/bin, GameDKCoreLatest/bin, GDK_BIN, and Program Files (x86)/Microsoft GDK/bin. It records runner image metadata, candidate file paths, observational (unapproved) SHA-256 digests, reparse-point flags, and environment-variable presence. The JSON artifact `signal-sprint-gdk-sdk-environment-probe` uses schema_version 2.

Statuses:
- MAKEPKG_NOT_DISCOVERED: no candidate in the bounded search; not proof of absence elsewhere.
- MAKEPKG_CANDIDATE_DISCOVERED_UNAPPROVED: one non-linked candidate found; **not** SDK approval.
- MAKEPKG_MULTIPLE_CANDIDATES_UNAPPROVED: several distinct candidate paths; explicit version selection is needed.
- MAKEPKG_LINKED_CANDIDATE_UNTRUSTED: discovered candidate is a reparse point; refuse to trust it.

The Windows SDK runner's discovery additionally enumerates every absolute PATH directory, rather than accepting only the first `shutil.which` match. Two different `makepkg.exe` installations on PATH cause HOLD until an exact `--makepkg-path` and independent approved digest are supplied. Empty/relative PATH entries are ignored; linked executable paths and linked/junction parent directories are rejected. The hosted probe already uses `Get-Command -All` and can report multiple candidates. These are offline discovery safeguards, not proof that a usable GDK exists.\n\nNo probe result approves SDK provenance. Independently review the exact makepkg.exe bytes and SHA-256 before any real --execute run. The SDK runner now supports --makepkg-path for an explicit approved selection when more than one version is installed. It always requires an independently supplied --trusted-makepkg-sha256 for execution.

The GitHub-hosted probe never downloads GDK, runs makepkg, generates packages, retrieves Identity, touches immutable Factory source, or asserts CAS_RETURN_PASS / REAL_MSIX_PASS / E2E PASS. Real packaging still requires CAS, the dedicated post-CAS build branch, reviewed reserved display name and package version, fixed ZIP/EXE byte checks, and authorized Windows GDK.

Microsoft's public GDK documentation describes free GDK installation via winget, but no installation is attempted by this workflow: https://github.com/microsoft/GDK

No new game, main/release write, force push, merge, or Partner Center action is involved. The 36-minute Windows/E2E owner retains the central ledger/queue.
