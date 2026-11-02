# Signal Sprint original-byte recovery receipt (fail-closed)

Partner Center selection: **GDK game**. This is a read-only pre-CAS check for the single pinned Signal Sprint product. It does not change the Factory source, perform CAS, build MSIXVC2, install, submit to Store, or edit the Windows-all-auto ledger.

## Blocking discrepancy discovered 2026-11-02

The supervisor handoff supplies original ZIP SHA-256 `e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412` and contained EXE SHA-256 **`e8517df8cd31a40e5ce72afdd4e6a4d63626fb99f7ff8a4fa3296ff8deef05f4`**. However, existing `gdk_build_intake.py` and `docs/SIGNAL_SPRINT_EXACT_ARTIFACT_GATE.md` pin that same ZIP to a **different** EXE SHA-256: **`9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad`**.

**Do not silently select either EXE hash.** Both independent authorities must agree, and then the actual preserved ZIP must match the original ZIP hash and the contained EXE hash, with exact members, CRC, request ID, product provenance and source SHA. Until the discrepancy is resolved from primary evidence, `EXPECTED_DIGEST_AUTHORITY_CONFLICT` forces `ARTIFACT_EXACT_BYTES_HOLD`, even if a candidate is present. No original-byte recovery is claimed.

Original GitHub Actions artifact ID `12706862577` was previously reported expired (2026-11-01 03:18:51 UTC) and its archive download returned 404. This repository does not contain a verified preserved original ZIP.

## Check-only command

Run only in an environment with access to the preserved original ZIP:

```bash
python gdk_exact_bytes_recovery_receipt.py --candidate /external/archive/original.zip
python gdk_exact_bytes_recovery_receipt.py --search-dir /external/archived-zips
```

The script prints a deterministic JSON recovery receipt on stdout and returns 2 on HOLD, 0 only on verified check-only evidence. It reports each candidate's ZIP and internal EXE hashes separately, compares each with both independently supplied pins, and delegates complete ZIP/provenance validation to `gdk_exact_artifact_check.py` / `gdk_build_intake.py`. Symlinks, invalid archives, unexpected members, wrong product/request/source, repacks and incomplete scans fail closed.

The `evidence_sha256` is a checksum of the printed evidence section, **not** an authenticated signature or proof of the receipt's author. `receipt_authenticity_verified=false`, `ready_for_cas=false`, `cas_return_pass=false`, `real_msixvc_built=false`, `e2e_pass=false`, and `store_submitted=false` remain mandatory even when the archive eventually matches.

For a later real build, independently approve Package Version, perform authorized Identity CAS, use a dedicated post-CAS build branch, keep staging outside the Factory checkout, then run the separate GDK SDK and Windows QA gates. Never substitute a newly built EXE, repacked ZIP, or synthetic fixture for the original bytes.

The user-provided GDK Identity is already received; no Partner Center Identity re-request is needed.
