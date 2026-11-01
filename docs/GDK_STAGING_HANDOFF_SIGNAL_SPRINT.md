# Signal Sprint GDK — byte-pinned SDK handoff (check-only)

**Partner Center selection: GDK game.** This document covers only the received Signal Sprint Identity and immutable Factory source `c058cbf7fe38e02d929c67d047d717ff74bd522e`. It does not create a new game, run Partner Center, or claim a real package.

## Inputs and trust boundaries

1. The user-provided GDK Identity is already received. Preserve the original source branch and SHA; CAS must be independently verified before the dedicated build branch is used.
2. The `SignalSprint.exe` must be extracted from the **pinned** artifact without rebuilding it. Its SHA-256 must equal the immutable `EXE_SHA256` in the code.
3. The staging folder must contain exactly named inputs `SignalSprint.exe`, `StoreLogo.png` (100×100), `Logo.png` (150×150), `SmallLogo.png` (44×44), and `SplashScreen.png` (1920×1080). PNG validation is structural; artwork quality still needs human QA.
4. Supply a separately reviewed display name and an explicit four-component package version ending in `.0`. Neither is inferred from the received Identity. The contract intentionally omits Xbox-service initialization IDs from `MicrosoftGame.config` for the standalone no-Xbox-services build; it does **not** discard their received Identity evidence.

## Offline contract preparation

From the Provisioner checkout, after the approved CAS and build SHA are available:

```powershell
python gdk_microsoft_game_config.py --factory-checkout "<factory checkout>" --pinned-artifact-zip "<pinned zip>" --cas-commit-sha "<actual CAS SHA>" --build-head-sha "<actual build SHA>" --asset-root "<staging folder>" --package-version "<reviewed A.B.C.0>" --reviewed-display-name "<reviewed name>" --write-staging-config > "<reviewed-contract.json>"
```

Keep `reviewed-contract.json` **outside** the mutable staging folder (not in any subdirectory of it). The verifier now rejects contracts located inside staging, including paths disguised with `..`, and rejects linked contract files or ancestors. This separation is necessary but not an authenticity guarantee: retain the reviewed external copy under access controls and do not accept a replacement without review. Do not reuse an old JSON contract with newly rebuilt assets. The JSON contains SHA-256 values for the executable, four PNG files, and generated XML; it explicitly states `gdk_sdk_validated=false` and `real_msixvc_built=false`. It also records the independently reviewed display name and explicit package version; the handoff verifier deterministically regenerates the permitted XML from those values and the pinned Store Identity. A self-consistent, recomputed JSON/XML SHA-256 is **not** sufficient to change Store ID, executable, Xbox-service tags, version or display name.

Immediately before any future GDK SDK invocation:

```powershell
python gdk_staging_handoff_verify.py --contract-json "<reviewed-contract.json>" --asset-root "<staging folder>"
```

A zero exit code means only that the five staged files and the written `MicrosoftGame.config` match the reviewed byte manifest at the moment of checking. Nonzero means **HOLD**; do not run the SDK. Re-run the verifier after any staging change. It never creates branches, runs MakePkg, installs packages, uploads to Store, or reports `REAL_MSIX_PASS`.

## Remaining gates

- Obtain a verified CAS return and dedicated build-branch checkout without moving the immutable source.
- On a Windows GDK SDK machine, independently validate `MicrosoftGame.config` and run the appropriate supported MakePkg / MSIXVC or MSIXVC2 flow; retain tool versions, command logs, output SHA-256, and package version.
- Send package provenance to Windows-all-auto through the 36-minute Windows/E2E lane. Complete Windows installation/runtime/GUI QA and Store draft checks separately. **No submission or certification is authorized here.**
