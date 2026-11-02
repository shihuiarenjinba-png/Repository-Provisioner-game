# Signal Sprint — distinct new-lineage post-CAS GDK gate (check-only)

**Partner Center selection: GDK game.** This contract applies only to the *new* Factory build lineage, not the expired original ZIP. It does not authorize or execute CAS, the GDK SDK, makepkg, MSIXVC2, Store submission or E2E.

## Immutable inputs

- Source: `c058cbf7fe38e02d929c67d047d717ff74bd522e` (never advance original source branch)
- Original request: `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e` (**historical HOLD**)
- New request: `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e-reissue-sprint-41361263698-41361263698`
- New Factory run: `41361263698`; artifact `13105352227`; build head `a1af3448cd2edeae5bd54cbaca486a53fd991944`
- GitHub outer ZIP SHA-256: `843496682662e871fc6e1b5df83ace2c6b01ef314cfc466b5072290890b70a8f`
- Inner Factory ZIP SHA-256: `46aff1ee7570459235c9e7ca7fb1faf6f494dc8100e62b6e132c6d07a6291b71`
- EXE SHA-256: `beb683b61b4fa4b2ec90fe1d413363c8a535bd4cb72b41b54b03a9685f516ee0`

The old Artifact `12706862577` is expired. Its EXE SHA authority conflict (`9c31...` versus `e851...`) is **not resolved** by this new lineage.

## Gate

`gdk_new_lineage_post_cas_gate.py` reuses the existing `gdk_factory_lineage_adapter.check_live` to independently read GitHub run/artifact metadata and hash the real outer ZIP, inner ZIP and EXE. It then checks the actual Git CAS commit parent (must be the immutable source), exact changed file (approved Identity only), new request and new EXE hash in committed Identity, approved official Store/Xbox fields including Title ID/SCID/MSA App ID, dedicated clean build branch, and unchanged product tree.

The staging directory must be outside the Factory checkout and contain **exactly** `SignalSprint.exe`, `MicrosoftGame.config`, `StoreLogo.png`, `Logo.png`, `SmallLogo.png`, and `SplashScreen.png`. The gate hashes all files, checks PNG CRC/dimensions, and verifies config Identity, Version, executable, display and asset references. It accepts only explicit new-request version and asset review records, rejecting missing, foreign, old-request or unapproved records. The files are *claims*, not authenticated review authority.

Usage **only after a separately authorized real new-request CAS**:

```bash
python gdk_new_lineage_post_cas_gate.py \
  --factory-checkout /path/to/clean-dedicated-post-cas-checkout \
  --outer-artifact-zip /path/to/github-actions-artifact-13105352227.zip \
  --cas-commit-sha ACTUAL_NEW_REQUEST_CAS_SHA \
  --build-head-sha ACTUAL_DEDICATED_BUILD_SHA \
  --staging-dir /path/outside/factory/staging \
  --version-review /path/outside/factory/version-review.json \
  --asset-review /path/outside/factory/asset-review.json
```

A structurally valid result is `NEW_LINEAGE_GDK_POST_CAS_CHECK_ONLY` with **exit code 2**, `ready_for_sdk=false`, `approval_authenticity_verified=false`, `gdk_sdk_validated=false`, `real_msixvc_built=false`. Missing/mismatched inputs produce `NEW_LINEAGE_GDK_POST_CAS_HOLD`. Neither status is permission to package. Independently authenticate the actual approver and approved Version/assets via a trusted authority outside these JSON files; establish real CAS authorization and recheck immediately before SDK execution. A saved JSON receipt cannot grant itself authority.

Do not use the old-request `gdk_build_intake.py` or `gdk_msixvc2_preflight.py` to consume the new EXE; those intentionally pin the old artifact and request. Do not change the 36-minute owner's central ledger. The GAME lane only supplies evidence and check-only contracts.
