# Signal Sprint GDK MicrosoftGame.config staging gate

**Partner Center selection: GDK game.** This stage is cloud-reviewable preparation only. It does not certify the GDK SDK schema, build MSIXVC/MSIXVC2, test GUI/install, or submit to Store. Never route Signal Sprint through generic MSIX/PWA.

## Immutable source and Identity
Factory source branch: codex/game-signal-sprint-undo-20261027
Immutable source SHA: c058cbf7fe38e02d929c67d047d717ff74bd522e
Request ID: game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e
Store ID: 9N21MJM7S57P
Identity Name: OkinawaDesktopTools.SignalSprint
All other reviewed GDK identifiers are pinned in package_identity_provisioner.py.
Original ZIP SHA-256: e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412
Internal EXE SHA-256: 9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad
Original Artifact #12706862577 expires 2026-11-01 03:18:51 UTC. Preserve the same bytes, not a replacement build.

## Preconditions and check-only usage
Only after explicit approval of the real CAS and creation of a dedicated post-CAS build branch. The existing gdk_build_intake.create_intake first verifies actual CAS parent/ancestry, approved Identity, and original ZIP/EXE provenance.

Prepare a separate staging folder containing the original SHA-verified SignalSprint.exe and real reviewed PNG artwork: StoreLogo.png (100x100), Logo.png (150x150), SmallLogo.png (44x44), SplashScreen.png (1920x1080). Do not use placeholder artwork.

Package Version is a later, explicitly reviewed A.B.C.0 build-gate input; fourth component is reserved by Store. The display name must be independently reviewed. Neither is invented from the GDK Identity.

Read-only command:

    python gdk_microsoft_game_config.py --factory-checkout PATH_TO_POST_CAS_FACTORY --pinned-artifact-zip PATH_TO_ORIGINAL_ZIP --cas-commit-sha ACTUAL_CAS_SHA --build-head-sha ACTUAL_BUILD_SHA --asset-root PATH_TO_STAGING --package-version REVIEWED_A.B.C.0 --reviewed-display-name "REVIEWED_DISPLAY_NAME"

This produces machine-readable JSON with MicrosoftGame.config XML, XML SHA-256, separate source/CAS/build SHAs, and GDK_CONFIG_CHECK_ONLY. It refuses changed EXE bytes, wrong Identity, invalid version, missing/corrupt/wrong-size icons, and missing reviewed display name. PNG dimensions, chunk CRC/order, IDAT zlib stream completeness, decompressed scanline lengths and filter-byte ranges are checked; full pixel reconstruction, visual quality, and GDK SDK validation are not claimed. A CRC-valid PNG with missing IDAT, invalid deflate data, truncated scanlines or illegal filter bytes is rejected before staging.

After manual review, optionally add --write-staging-config to exclusively create a new MicrosoftGame.config in the staging folder. Existing files are not overwritten. The immutable Factory source, Windows-all-auto queue, and central E2E ledger are not edited.

## Remaining Windows GDK gates
1. Validate MicrosoftGame.config with installed October 2026 GDK editor/SDK and check real artwork, runtime dependencies and launch behavior.
2. Build only on the dedicated post-CAS branch from pinned EXE bytes.
3. October 2026 GDK: makepkg genmap /f layout.xml /d GAME_FOLDER; then PC MSIXVC2: makepkg pack /msixvc2 /f layout.xml /d GAME_FOLDER /pc /pd OUTPUT_FOLDER.
4. Verify actual MSIXVC2 package SHA, payload and launch, install, GUI and Checker QA. Give the real package receipt to the 36-minute Windows-all-auto owner.
5. No Store upload/submission without separate authorization.

Microsoft references:
https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/packaging/overviews/packaging-getting-started-for-pc
https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/packaging/overviews/packaging-getting-started-for-pc-msixvc2
https://learn.microsoft.com/en-us/gaming/gdk/docs/reference/system/microsoftgameconfig/microsoftgameconfig-schema

Current status: PRE_IDENTITY_READY=code/CI tested; USER_MANAGED_IDENTITY_GATE=received; POST_IDENTITY_READY=config contract tested only; CAS_RETURN_PASS=false; REAL_MSIX_PASS=false; E2E_PASS=false.
