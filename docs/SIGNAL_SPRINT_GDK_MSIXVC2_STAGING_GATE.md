# Signal Sprint — GDK MSIXVC2 staging inventory gate

**Partner Center selection: GDK game.** This is a read-only cloud-testable gate. It does not call Partner Center, GDK SDK, makepkg, GitHub CAS, Windows-all-auto, or Store. The original source SHA remains `c058cbf7fe38e02d929c67d047d717ff74bd522e`.

## Purpose

The earlier `gdk_microsoft_game_config.py` validates the reviewed GDK Identity, pinned executable and artwork, but does not prohibit *additional* unreviewed files in the makepkg staging folder. `gdk_msixvc2_preflight.py` closes this gap before Windows packaging.

It re-runs the real Git CAS parent/ancestry and approved-identity verification, re-verifies the immutable ZIP and EXE SHA, and independently generates the reviewed MicrosoftGame.config. The staging directory must contain **exactly**:

- `SignalSprint.exe` — original EXE SHA-256 `9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad`
- `MicrosoftGame.config` — byte-for-byte equal to the generated reviewed XML
- `StoreLogo.png`, `Logo.png`, `SmallLogo.png`, `SplashScreen.png` — checked for PNG dimensions and CRC by the existing config gate

Additional DLLs, nested folders, symlinks, missing files, invalid sizes, modified XML and altered EXE bytes cause fail-closed rejection. The check-only JSON includes SHA-256 of **every** staging file for later Windows re-verification. This is a snapshot, not an atomic filesystem lock; the builder must rehash all six files immediately before `makepkg`.

## Run after explicitly approved CAS

Use an independent post-CAS build checkout; never move the original source branch merely to run this command. Provide a reviewed package version (A.B.C.0), independently reviewed display name, original preserved artifact ZIP, and the actual CAS and build SHA values.

```bash
python gdk_msixvc2_preflight.py \
  --factory-checkout /path/to/AI-Game-Factory-post-cas \
  --pinned-artifact-zip /path/to/original-signal-sprint.zip \
  --cas-commit-sha ACTUAL_CAS_SHA \
  --build-head-sha ACTUAL_BUILD_SHA \
  --staging-dir /path/to/reviewed-gdk-staging \
  --package-version REVIEWED_A.B.C.0 \
  --reviewed-display-name "REVIEWED_DISPLAY_NAME"
```

`MicrosoftGame.config` must already exist in staging. It can be created using `gdk_microsoft_game_config.py --write-staging-config` after the reviewed configuration check. Do not insert placeholder art or silently rebuild the EXE.

Successful output status is `GDK_MSIXVC2_STAGING_CHECK_ONLY`, with `gdk_sdk_validated=false`, `real_msixvc_built=false`, and `store_submitted=false`. It does **not** establish CAS_RETURN_PASS, REAL_MSIX_PASS or E2E PASS.

## Windows GDK handoff (36-minute owner)

1. Rehash the staging files against `staging_files_sha256` immediately before building.
2. Use the installed official GDK SDK to validate `MicrosoftGame.config`, dependencies and assets.
3. Generate `layout.xml` with `makepkg genmap`; package for PC with `makepkg pack /msixvc2` as supported by the installed SDK.
4. Verify the real MSIXVC2 bytes and package payload; perform install, launch and GUI QA.
5. Only after real validation, pass the package SHA and machine-readable evidence to the Windows-all-auto owner. Do not edit the central E2E ledger or cross-product queue in the GAME lane.

Original Artifact #12706862577 expires 2026-11-01 03:18:51 UTC; preserve the original ZIP bytes. Never substitute a different rebuild. Store submission requires separate approval.

Current state: GDK Identity received; staging contract is CI-testable; actual CAS, Windows SDK validation, real MSIXVC2 and E2E remain unproven.
