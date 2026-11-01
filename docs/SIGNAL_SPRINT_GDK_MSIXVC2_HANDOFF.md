# Signal Sprint GDK MSIXVC2 handoff — version review and immutable evidence

**Partner Center selection: GDK game.** This is a check-only contract for the existing Signal Sprint product, never a successful CAS, GDK SDK validation, MSIXVC2 build, install, E2E or Store submission.

The fixed source is `c058cbf7fe38e02d929c67d047d717ff74bd522e`, request ID `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e`. Keep `source_sha` separate from actual post-CAS `factory_head_sha`. The original ZIP SHA-256 is `e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412`, and the internal EXE SHA-256 is `9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad`. No rebuilt executable can replace these bytes.

## Independent version review (not part of Partner Center Identity)

Create a separately reviewed JSON file **outside the Factory checkout**. The following is a **synthetic schema illustration only**, not a real version approval; do not use it as an authorization:

```json
{
  "schema_version": 1,
  "decision": "APPROVED",
  "partner_center_selection": "GDK_GAME",
  "package_format": "MSIXVC2",
  "request_id": "game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e",
  "source_sha": "c058cbf7fe38e02d929c67d047d717ff74bd522e",
  "package_version": "1.0.1.0",
  "reviewed_display_name": "Signal Sprint",
  "reviewed_by": "Fixture Operator",
  "reviewed_at": "2026-11-01T23:00:00+09:00"
}
```

The version, display name, reviewer and timestamp in this example are fixtures, **not approved production values**. Version must be independently chosen/reviewed at the later build gate, not copied from the Identity. The script validates schema, decision, version format, reviewer, timestamp and SHA binding; it **cannot cryptographically authenticate the human review**. A Windows owner must separately verify approval provenance.

## Post-CAS handoff

Only after a real, authorized Identity CAS, a clean dedicated `codex/game-signal-sprint-gdk-build-*` branch, and recovery of the **byte-identical original ZIP**, prepare staging outside the Factory checkout. Generate the reviewed `MicrosoftGame.config` and PNG assets using the earlier gates. Run `gdk_msixvc2_preflight.py`, saving its complete JSON receipt. Immediately before SDK packaging, run:

```bash
python gdk_msixvc2_handoff.py \
  --factory-checkout /safe/AI-Game-Factory-post-cas \
  --pinned-artifact-zip /safe/preserved/original.zip \
  --cas-commit-sha ACTUAL_CAS_SHA \
  --build-head-sha ACTUAL_BUILD_SHA \
  --staging-dir /safe/gdk-staging \
  --version-review /safe/reviews/version.json \
  --preflight-receipt /safe/reviews/preflight.json
```

The handoff calls the **existing full second-pass recheck**, which re-derives actual CAS ancestry and approved Identity, immutable original ZIP and EXE, dedicated build branch, reviewed XML, exact staging inventory and SHA-256 of every staged file. It also binds the independently reviewed version, Store ID, Xbox Title ID, SCID, MSA App ID, the Identity blob SHA, the MicrosoftGame.config SHA, source/CAS/build SHA and review/receipt hashes.

Successful status is **`GDK_MSIXVC2_HANDOFF_CHECK_ONLY`**. `version_review_authenticity_verified=false`, `gdk_sdk_validated=false`, `real_msixvc_built=false`, `cas_return_pass=false`, `e2e_pass=false`, and `store_submitted=false` are deliberate. Never translate this into `REAL_MSIX_PASS`.

## True blockers and owner boundary

Original GitHub Artifact #12706862577 expired at 2026-11-01 03:18:51 UTC. If no preserved ZIP passes **both** original ZIP and internal EXE SHA, report `ARTIFACT_EXACT_BYTES_HOLD`. Do not substitute a rebuilt EXE. Actual CAS, reviewed production version, Windows GDK SDK/schema validation, real MSIXVC2, install/GUI QA and Windows-all-auto ledger remain separate. The 12-minute GAME owner never edits the central ledger; 36-minute Windows owner consumes the later **real** package evidence only.

All source/receipt/review/staging paths must remain outside the immutable Factory checkout where applicable. This tool writes nothing and never invokes `makepkg`.
