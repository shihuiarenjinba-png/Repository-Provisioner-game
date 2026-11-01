# Signal Sprint — preserved original artifact exact-byte gate

**Partner Center selection: GDK game.** This is an independent, read-only, pre-CAS provenance gate. It never retrieves Partner Center Identity, changes the immutable Factory branch, performs CAS, builds GDK packages or writes the Windows-all-auto ledger.

Original fixed evidence:

- Request: `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e`
- Factory source SHA: `c058cbf7fe38e02d929c67d047d717ff74bd522e`
- Original GitHub Actions artifact ID: `12706862577`, expired 2026-11-01 03:18:51 UTC
- **Original ZIP SHA-256:** `e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412`
- **Contained SignalSprint.exe SHA-256:** `9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad`

## Read-only verification

Locate a previously preserved, unmodified original artifact archive in a separate directory outside the Factory checkout. Run:

```bash
python gdk_exact_artifact_check.py --candidate /safe/preserved/original.zip
# Or scan one or more explicitly selected locations, to depth 4:
python gdk_exact_artifact_check.py --search-dir /safe/archived-artifacts
```

Both `--candidate` and `--search-dir` can be repeated. Search is bounded to 1,000 ZIP candidates; an incomplete search fails closed. The tool reports **ZIP SHA and contained EXE SHA separately**, including when a repacked ZIP contains an otherwise matching EXE. It then invokes the existing full pinned-artifact validation for ZIP CRC, three exact members, provenance and request ID. Symlinked inputs are rejected.

Only `ARTIFACT_EXACT_BYTES_CHECK_ONLY` with `exact_copy_count >= 1` proves the original bytes have been found. This does **not** authorize CAS or establish a GDK package. Missing files, no candidates, altered/repacked archives, incorrect provenance, unreadable files and scan-limit failures return **`ARTIFACT_EXACT_BYTES_HOLD`**, exit code 2. Never replace the pinned artifact with a newly rebuilt EXE or repacked ZIP even if the game runs.

A prior GitHub artifact download returning HTTP 404 is not evidence of a preserved copy. In the cloud execution environment for this run, the expired artifact could not be downloaded and no saved ZIP was available to inspect. The check-only tool was exercised with synthetic fixtures; **real artifact verification remains HOLD** until the exact original bytes are provided to a trusted runner.

After an exact match is independently verified, proceed only with the separately approved CAS, dedicated post-CAS build branch and `gdk_msixvc2_preflight.py` / `gdk_msixvc2_recheck.py` gates. Real GDK SDK validation, MSIXVC2 creation, install/launch and Windows E2E remain separate, unproven steps.
