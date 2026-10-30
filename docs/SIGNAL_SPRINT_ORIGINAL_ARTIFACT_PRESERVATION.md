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

Keep the original ZIP and JSON evidence together under owner control. The copy remains a `QA_UNSIGNED` EXE artifact; it is **not** a signed or certifiable GDK package. CAS, Package Version, reserved display name, retail GDK SDK, MSIXVC2 build, Windows QA, and Store submission remain separate gates. This tool does not access Partner Center, change Factory source, perform CAS, or edit the Windows-all-auto ledger.
