# Signal Sprint original EXE artifact preservation

Partner Center selection: **GDK game**. This is an owner-controlled backup of the **original** GitHub Actions artifact #12706862577, not a new build, an MSIXVC2 package, or a Store submission.

The original GitHub artifact expires at **2026-11-01 03:18:51 UTC**. An already recovered ZIP is required as input. The GitHub branch contains only the verification/copy code; the 11 MB binary is **not** committed to the repository.

Original ZIP: `signal-sprint-original-github-artifact-12706862577.zip`
SHA-256: `e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412`
Pinned `SignalSprint.exe` SHA-256: `9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad`
Immutable Factory source SHA: `c058cbf7fe38e02d929c67d047d717ff74bd522e`.

Run on the machine that holds the recovered ZIP, from a checkout of this Provisioner branch. Create the owner-managed backup directory in advance (prefer a separately backed-up volume):

```powershell
python signal_sprint_preserve_artifact.py --original-zip "C:\\path\\signal-sprint-original-github-artifact-12706862577.zip" --destination-dir "D:\\OwnerBackup\\SignalSprint"
```

The tool validates the original ZIP, CRC, member set, provenance, and EXE against pinned SHA-256 constants, then copies **the original ZIP bytes**, without extraction/recompression or EXE rebuild. It uses exclusive creation, never overwrites a conflicting target, verifies the stored copy, and emits JSON. `PRESERVED_VERIFIED` is a successful first copy; `EXISTING_VERIFIED` is a safe idempotent rerun. An error is HOLD/CONFLICT, not success.

The preservation helper now **automatically creates** a portable, strict JSON sidecar named `signal-sprint-original-github-artifact-12706862577.zip.integrity.json` beside the exact ZIP. The manifest binds the immutable source SHA, request ID, original artifact ID, full archive SHA/size, fixed EXE SHA, and explicit false CAS/build/E2E/Store states. The manifest is created exclusively, verified byte-for-byte on idempotent retries, and never overwrites a conflicting manifest. If the ZIP was preserved before this enhancement, an idempotent rerun can add the missing sidecar without replacing the original ZIP. Both files must verify before `PRESERVED_VERIFIED` or `EXISTING_VERIFIED` is reported. This is backup evidence, **not** SDK approval, a Store package, or certification.\n\nKeep the original ZIP and JSON evidence together under owner control. The copy remains a `QA_UNSIGNED` EXE artifact; it is **not** a signed or certifiable GDK package. CAS, Package Version, reserved display name, retail GDK SDK, MSIXVC2 build, Windows QA, and Store submission remain separate gates. This tool does not access Partner Center, change Factory source, perform CAS, or edit the Windows-all-auto ledger.


## Restoring from the rescued GitHub Actions wrapper (2026-10-31)

The original **byte-identical** ZIP was recovered inside Actions artifact
**12999968947** from [run 41105901884](https://github.com/shihuiarenjinba-png/AI-Game-Factory/actions/runs/41105901884).
That outer Actions download ZIP is **not** the original ZIP and must never be
passed directly to the GDK build gate. Its nested file
`signal-sprint-exact-archive/signal-sprint-original-github-artifact-12706862577.zip`
is the exact pinned original (SHA-256 `e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412`).

After downloading the rescued Actions artifact ZIP and preparing a durable
owner-managed destination directory, run:

```powershell
python signal_sprint_rescue_wrapper.py --rescue-wrapper-zip "C:\path\downloaded-rescue-wrapper.zip" --destination-dir "D:\OwnerBackup\SignalSprint"
```

The helper reads the wrapper as one snapshot, rejects unexpected/duplicate/
traversal/symlink members, checks wrapper CRC and the exact nested original ZIP
SHA-256, compares all three extracted member bytes with the nested original,
then delegates to `signal_sprint_preserve_artifact.preserve` for full
provenance validation and exclusive, restart-safe preservation. It never
rebuilds the executable, repacks the original ZIP, overwrites conflicting
backups, performs CAS, runs the SDK, or accesses Partner Center.

Successful statuses are `PRESERVED_VERIFIED` and `EXISTING_VERIFIED`;
both mean only the local **copy** passed verification, not Store readiness.
The rescued GitHub Actions artifact is temporary (90-day retention), and
this helper has not been run against an owner-managed durable destination.
