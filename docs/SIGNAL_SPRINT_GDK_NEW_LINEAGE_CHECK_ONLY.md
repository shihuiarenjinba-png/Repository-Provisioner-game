# Signal Sprint: new immutable GDK build lineage (check-only)

**Scope:** one existing product, `Signal Sprint`. Partner Center selection: **GDK game**.
The immutable Factory source is `c058cbf7fe38e02d929c67d047d717ff74bd522e`
on `codex/game-signal-sprint-undo-20261027`. Do not change that branch.

## Why this is separate from recovery

Original GitHub Actions Artifact `12706862577` has expired. Its ZIP digest was
`e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412`.
The original job log supports EXE digest
`9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad`,
while a historical central handoff claims
`e8517df8cd31a40e5ce72afdd4e6a4d63626fb99f7ff8a4fa3296ff8deef05f4`.
Neither a new build nor a new receipt recovers or replaces the original ZIP.

If the exact original ZIP is found, use the existing read-only original-run
and exact-bytes auditors. Keep `EXPECTED_DIGEST_AUTHORITY_CONFLICT` open until
independent primary evidence reconciles it.

## Distinct lineage protocol

1. Independently review the decision to **request** a new build from the exact
   pinned source. Do not call it a retry of the original request.
2. Assign a **new** GitHub Actions run ID and artifact ID. Set
   `new_request_id = game-signal-sprint-reissue-<source_sha>-<run_id>`
   and `build_id = gdk-reissue-<run_id>-<artifact_id>`.
3. New ZIP must contain exactly `SignalSprint.exe`, `provenance.json` and
   `provisioner-request.json`. Both JSON records must identify the new
   request/build/run/artifact IDs, pinned product and pinned source.
   Provenance must record the actual new EXE digest; the request must retain
   `dry_run: true`. Do not use a ZIP produced for the original request.
4. Provide a separate UTF-8 JSON proposal with **exactly** these keys:
   `schema_version=1`, `decision=REQUEST_NEW_IMMUTABLE_BUILD_LINEAGE`,
   `product=Signal Sprint`, `partner_center_selection=GDK_GAME`,
   `source_sha`, `source_branch`, `original_request_id`,
   `original_artifact_id=12706862577`, `new_request_id`, `build_id`,
   `workflow_run_id`, `artifact_id`, `zip_sha256`, `exe_sha256`,
   `reviewed_by`, `reviewed_at`, `store_id`, `xbox_title_id`,
   `xbox_scid`, `msa_app_id`. Identity values must equal the existing
   reviewed Signal Sprint GDK values. Package Version is intentionally
   excluded and requires independent later approval.
5. From a safe working directory outside Factory checkout, run:

```bash
python gdk_new_lineage_reissue_check.py --reissue-proposal /safe/reissue.json --new-artifact-zip /safe/new-lineage.zip
```

Exit code `2` is **intentional**, including on valid synthetic check-only
evidence. A `NEW_LINEAGE_CHECK_ONLY` receipt only confirms internal
consistency of submitted evidence. The operator's review JSON is **not**
cryptographically authenticated. It is not a CAS grant, package success, or
approval to update any existing approved Identity.

**Critical separation:** current `gdk_build_intake.py`, CAS ledger and
`gdk_msixvc2_handoff.py` still pin the original request and ZIP/EXE.
Do **not** feed a new lineage into those old gates or rewrite their pins.
Before real use, a separately reviewed and tested new-request CAS contract,
authentic provenance/approval checks, dedicated build branch, GDK SDK
verification, and independent Package Version approval are required.
`ARTIFACT_EXACT_BYTES_HOLD` remains on the original lineage.

No Partner Center login, Store submission, main/release writes, or new product
generation are part of this checker.
