# Signal Sprint — original GitHub Actions run evidence audit

**Partner Center selection: GDK game.** This is a read-only discrepancy audit, not a CAS or GDK SDK build. The Factory source stays `c058cbf7fe38e02d929c67d047d717ff74bd522e`; request ID is `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e`.

## New primary evidence (2026-11-02)

The original [Factory run #40443340158, Windows job #121988766700](https://github.com/shihuiarenjinba-png/AI-Game-Factory/actions/runs/40443340158/job/121988766700), generated from the pinned source on 2026-10-27, has these independently emitted lines:

- Build output `GAME_UNSIGNED_EXE_SHA256=9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad`
- Verification output `GAME EXE SHA256: 9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad`
- Upload output `SHA256 digest of uploaded artifact zip is e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412`
- Upload output `Artifact ID 12706862577` (11,094,247 bytes); name includes the exact source SHA.

The original job log therefore supports the repository EXE pin **9c31…85ad**, not the older supervisor handoff EXE SHA **e851…05f4**. The old value remains recorded as a conflicting claim, not overwritten. GitHub Actions artifact ID 12706862577 currently returns 404 and the run's artifact listing is empty. The original ZIP bytes and its embedded provenance remain unavailable, so **EXPECTED_DIGEST_AUTHORITY_CONFLICT / ARTIFACT_EXACT_BYTES_HOLD** remains mandatory. A job log is not a substitute for the original ZIP.

## How to run read-only audit

Save the original GitHub job log to a trusted external path (outside the Factory checkout). With a previously archived, byte-for-byte original ZIP, run:

```bash
python gdk_original_run_evidence_audit.py \
  --original-job-log /external/evidence/original-job.log \
  --candidate /external/archive/original.zip
```

For an authorized bounded read-only search, replace `--candidate` with `--search-dir /external/archive`. All input files are read-only. The script rejects symlinked job-log paths, contradictory duplicate records, changed source SHA, missing run output and wrong artifact ID. It delegates ZIP/EXE/CRC/provenance/request verification to `gdk_exact_bytes_recovery_receipt.py` and its exact-artifact checker. The JSON receipt lists each source URL and SHA, both log EXE outputs, the original ZIP candidate results, and the explicit conflict. The job-log text is supplied by the operator; **`log_authenticity_verified=false`** is deliberate and no signature is inferred.

The receipt never permits CAS. Even if a future original ZIP is recovered, separately reconcile the conflicting EXE authority from the primary evidence, verify the ZIP and EXE SHA independently and inspect `provenance.json` plus `provisioner-request.json` for exact request/source. Package Version approval, authorized CAS, dedicated post-CAS build branch, GDK SDK MSIXVC2, Windows E2E and Store review are separate later gates. Never substitute a newly rebuilt EXE or repacked ZIP.

The Partner Center GDK Identity has already been received. No Identity re-request is needed.
