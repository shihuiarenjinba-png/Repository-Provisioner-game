# Signal Sprint new-lineage deterministic GDK assembly plan — CHECK ONLY

Partner Center selection: **GDK game**. This applies only to the separately issued new Factory lineage, not expired Artifact #12706862577. The original EXE SHA authority conflict remains `ARTIFACT_EXACT_BYTES_HOLD`.

Immutable source: `c058cbf7fe38e02d929c67d047d717ff74bd522e`.
New request: `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e-reissue-sprint-41361263698-41361263698`.
Factory run `41361263698`, Artifact `13105352227`, build HEAD `a1af3448cd2edeae5bd54cbaca486a53fd991944`.
Outer ZIP SHA `843496682662e871fc6e1b5df83ace2c6b01ef314cfc466b5072290890b70a8f`.
Inner ZIP SHA `46aff1ee7570459235c9e7ca7fb1faf6f494dc8100e62b6e132c6d07a6291b71`.
EXE SHA `beb683b61b4fa4b2ec90fe1d413363c8a535bd4cb72b41b54b03a9685f516ee0`.

## No-write command

```sh
python gdk_new_lineage_assembly_plan.py \
  --factory-checkout /safe/clean-post-cas-factory \
  --outer-artifact-zip /safe/github-actions-artifact-13105352227.zip \
  --cas-commit-sha ACTUAL_AUTHORIZED_NEW_REQUEST_CAS_SHA \
  --build-head-sha ACTUAL_DEDICATED_BUILD_HEAD \
  --asset-dir /safe/approved-gdk-assets \
  --version-review /safe/version-review.json \
  --asset-review /safe/asset-review.json \
  --staging-target /safe/new-staging-target
```

The staging target **must not exist**. Its parent must exist. This script never creates staging, writes XML, copies files, runs SDK or modifies Git. The asset directory must contain exactly four approved PNGs: `StoreLogo.png` (100x100), `Logo.png` (150x150), `SmallLogo.png` (44x44), `SplashScreen.png` (1920x1080). Symlinks, unexpected files, bad PNG CRC/dimensions, or altered SHA fail closed.

The script reuses `gdk_factory_lineage_adapter.check_live`, `gdk_new_lineage_post_cas_gate.verify_cas_git`, and `read_review` to avoid duplicate validation. It separately hashes the actual outer ZIP, inner ZIP and EXE. Only when the complete evidence is present does it return a deterministic six-file plan with SHA-256 and byte sizes, generated `MicrosoftGame.config` XML/hash, official Xbox identifiers, CAS SHA and approved Identity blob reference. **Every invocation exits 2**, including `NEW_LINEAGE_GDK_ASSEMBLY_PLAN_CHECK_ONLY`.

Missing CAS, missing/unapproved Version/assets, wrong request/source/EXE, mixed Title ID/SCID/MSA ID, foreign product, altered ZIP or an existing staging target returns `NEW_LINEAGE_GDK_ASSEMBLY_HOLD` without a plan. Positive tests are synthetic and do not prove real CAS.

A review JSON with `decision=APPROVED` is not proof of reviewer identity. Independent reviewer authentication and CAS authorization are mandatory before SDK execution. The plan always records `cas_return_pass=false`, `review_authenticity_verified=false`, `ready_for_sdk=false`, `gdk_sdk_validated=false`, `real_msixvc_built=false`, `e2e_pass=false`, `store_submitted=false`.

No Store submission, GDK SDK, central ledger writes, main/release changes, or immutable source changes. Consumer sale-ready QA remains separate: first 30-second onboarding, objective, failure feedback, retry, controls, visibility, pacing and replay value need actual gameplay verification.
