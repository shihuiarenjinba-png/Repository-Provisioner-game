# Signal Sprint — isolated real-byte GDK staging dry-run (CHECK ONLY)

**Scope:** Signal Sprint new lineage only, GDK_GAME (Partner Center: GDK game). Immutable source SHA c058cbf7fe38e02d929c67d047d717ff74bd522e is unchanged. This is not a GDK package build or an authorized staging operation.

Factory run 41361263698, Artifact 13105352227, build HEAD a1af3448cd2edeae5bd54cbaca486a53fd991944. New request: game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e-reissue-sprint-41361263698-41361263698.

## Command

With the original downloaded GitHub outer ZIP and the separately persisted live GitHub receipt:

~~~sh
python gdk_new_lineage_staging_dry_run.py \
  --outer-artifact-zip /safe/github-actions-artifact-13105352227.zip \
  --live-receipt-json docs/SIGNAL_SPRINT_NEW_LINEAGE_LIVE_CHECK_ONLY_20261102.json
~~~

The CLI always exits **2** and emits deterministic JSON. It first calls the **existing** cross-repo reconciler (no duplicate evidence validator), checks the exact outer ZIP SHA, inner ZIP SHA and EXE SHA, and writes only the real EXE to a new isolated temporary directory. It rereads and rehashes the temporary file, then deletes the directory before returning. The result never includes a transient machine-specific path. A second invocation with the same bytes must produce identical JSON.

An optional existing assembly plan and asset directory may be supplied for structural validation, but even a valid CHECK-ONLY plan **cannot authenticate a reviewer or CAS**. The tool deliberately never writes a MicrosoftGame.config or any unapproved PNG to staging, never persists a six-file staging tree, and never runs GDK SDK/MSIXVC2, CAS or Store actions.

## Actual-byte observation (2026-11-02 JST)

The provided GitHub Artifact ZIP was independently rehashed locally:

- Outer ZIP SHA-256: 843496682662e871fc6e1b5df83ace2c6b01ef314cfc466b5072290890b70a8f
- Inner ZIP SHA-256: 46aff1ee7570459235c9e7ca7fb1faf6f494dc8100e62b6e132c6d07a6291b71
- Transient EXE: SignalSprint.exe, **11,344,389 bytes**, SHA-256 beb683b61b4fa4b2ec90fe1d413363c8a535bd4cb72b41b54b03a9685f516ee0

Local nine-test synthetic suite passed and the actual EXE transient-stage hash matched. For this local execution only, the cross-repo reconciler was stubbed; therefore this is **not** a new end-to-end GitHub live verification. The earlier independent network live check is documented in SIGNAL_SPRINT_NEW_LINEAGE_LIVE_CHECK_ONLY_20261102.json. The repository's full reconciler is used by the committed CLI and must be validated separately before any higher-level decision.

**HOLD — five of six staging files are unavailable/unapproved:**

- Logo.png, SmallLogo.png, SplashScreen.png, StoreLogo.png: no independently approved real image bytes/review authority.
- MicrosoftGame.config: no independently approved Package Version and authenticated new-request CAS.

Do not fill these gaps with synthetic images, a guessed Version or a self-declared reviewer. Even a synthetic six-file fixture passing CI is **not** REAL_MSIXVC_PASS.

The expired original Artifact 12706862577 remains a **separate** ARTIFACT_EXACT_BYTES_HOLD with EXE SHA authority conflict. Never relabel this new build as recovery of the original.

## Consumer-quality gate

Do not mark SALE_READY based on packaging tests. First 30 seconds, complete JP/EN localization, visible failure/retry feedback, and repeat-play value still need actual Windows gameplay QA. The frozen source must not be modified to improve them; a future explicitly authorized revision is required.
