# Signal Sprint cross-repo Factory Artifact ↔ GDK assembly — CHECK ONLY

Partner Center selection: **GDK game** (`GDK_GAME`). Immutable source `c058cbf7fe38e02d929c67d047d717ff74bd522e`; no source-branch edits.

## Reproducible input

- Factory PR #15: `https://github.com/shihuiarenjinba-png/AI-Game-Factory/pull/15`
- Factory build run `41361263698`, build HEAD `a1af3448cd2edeae5bd54cbaca486a53fd991944`, Artifact `13105352227`.
- Provisioner PR #10: `https://github.com/shihuiarenjinba-png/Repository-Provisioner-game/pull/10`
- New request: `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e-reissue-sprint-41361263698-41361263698`.
- Existing **prior live GitHub check-only** evidence: `docs/SIGNAL_SPRINT_NEW_LINEAGE_LIVE_CHECK_ONLY_20261102.json`. This is a persisted evidence snapshot, **not fresh authentication**.
- Actual outer Artifact ZIP `github-actions-artifact-13105352227.zip` is not committed to Git.

## Actual Artifact recheck (2026-11-02)

The available original Artifact ZIP was read directly, with independent SHA-256 checks of each nested layer and all three manifest JSONs. This is a local exact-byte recheck, **not** an authenticated new GitHub network run and **not** an assembly-plan approval.

| Input | SHA-256 |
| --- | --- |
| GitHub outer ZIP | `843496682662e871fc6e1b5df83ace2c6b01ef314cfc466b5072290890b70a8f` |
| Factory inner ZIP | `46aff1ee7570459235c9e7ca7fb1faf6f494dc8100e62b6e132c6d07a6291b71` |
| SignalSprint.exe | `beb683b61b4fa4b2ec90fe1d413363c8a535bd4cb72b41b54b03a9685f516ee0` |
| provenance.json | `54649b9d2ce1e0420062c6f84ff4b8ea677fb3e83e26f26baf79e884b041144d` |
| provisioner-request.json | `d17827c37bcae305bdb7205798c7d6beb99c907516b2d0159209046b93fda9b0` |
| lineage-receipt.json | `439b752d67587cbbb1bc0d7ddba94839a138f6a64afbc2afa28ce27eea453fc5` |

The EXE is 11,344,389 bytes. Request, source, build HEAD, run ID and old-artifact-not-replaced flags matched across the real manifests.

## No-write integration command

```sh
python gdk_new_lineage_cross_repo.py \
  --outer-artifact-zip /safe/github-actions-artifact-13105352227.zip \
  --live-receipt-json docs/SIGNAL_SPRINT_NEW_LINEAGE_LIVE_CHECK_ONLY_20261102.json
```

Without an authenticated CAS and approved Version/assets, expected output is `CROSS_REPO_INTEGRATION_HOLD` with `artifact_manifest_bound=true`, six **expected path names only**, and **no six-file assembly plan**. The six paths are `SignalSprint.exe`, `MicrosoftGame.config`, `Logo.png`, `SmallLogo.png`, `SplashScreen.png`, `StoreLogo.png`.

Once the **separately verified** `gdk_new_lineage_assembly_plan.py` returns its CHECK-ONLY plan and the exact approved asset files exist, pass `--assembly-plan-json /safe/plan.json --asset-dir /safe/approved-assets`. The cross-repo reconciler binds all six SHA/byte-size/source-kind entries, official Title ID/SCID/MSA App ID, GDK registration, request/source/build HEAD and actual ZIP/EXE. A repeated invocation on identical bytes is deterministic. Unit tests use **synthetic** plan/reviewer/CAS inputs and are not authorization evidence.

The CLI **always exits 2** (even on a positive check-only contract). A human must distinguish `CROSS_REPO_ASSEMBLY_CONTRACT_CHECK_ONLY` from `REAL_MSIXVC_PASS`. Do not use shell `|| true` to convert HOLD to success.

## Mandatory HOLD and consumer quality

The old expired Artifact `12706862577` and its conflicting historical EXE SHA authority remain `ARTIFACT_EXACT_BYTES_HOLD`; the new lineage is **not** recovery of the old ZIP. No real new-request CAS, independent reviewer authentication, approved Package Version/assets, GDK SDK validation, real MSIXVC2, E2E or Store submission has occurred.

Consumer `SALE_READY` also remains HOLD: verify real first-30-second onboarding, JP/EN complete localization, failure explanation, retry timing, controls/visibility, and replay value beyond a single board. Any product revision requires a **separately authorized future source lineage**; never alter the pinned source SHA in this contract.
