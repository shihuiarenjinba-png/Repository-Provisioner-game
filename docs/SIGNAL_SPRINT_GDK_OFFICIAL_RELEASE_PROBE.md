# Signal Sprint — official retail GDK release metadata probe

Partner Center selection: **GDK game**. Signal Sprint only.

This read-only probe queries the official public Microsoft GDK GitHub release
metadata on an ephemeral GitHub Actions runner. It complements the existing
WinGet catalog probe. Neither source is an independently approved SDK installer.

- Script: `gdk_official_release_probe.py`
- Workflow: `.github/workflows/signal-sprint-gdk-official-release-probe.yml`
- Source: https://github.com/microsoft/GDK/releases
- Output: `signal-sprint-official-gdk-release-metadata` (JSON, 7-day retention)

Only published, non-draft, non-prerelease tags with the
`October-2026-v2610.x` or `October-2026-Update-N-v2610.x`
shape are reported as **unapproved candidates**. A missing tag on the
observed page is not proof that an SDK is unavailable elsewhere. A failed,
unparseable or truncated catalog is UNKNOWN; no result ever authorizes
an installer, an SDK executable digest, MSIXVC2 build, CAS, or Store action.

This job never downloads or executes an installer. The original
Signal Sprint source branch and pinned EXE remain immutable. Real GDK
packaging still requires independently approved SDK version and
`makepkg.exe` SHA-256, actual CAS and post-CAS build branch, reviewed
package version and reserved display name, and subsequent Windows QA.

Immutable source: `c058cbf7fe38e02d929c67d047d717ff74bd522e`.
Request ID: `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e`.
