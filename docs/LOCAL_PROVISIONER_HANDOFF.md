# LOCAL_PROVISIONER_HANDOFF — GAME

更新日: 2026-10-27 (Asia/Tokyo)

## 判定

**HOLD: オフライン実装、モック検証、DRY_RUNは完了。実製品MSIX生成、Partner Center公式ID取得、Factoryへの実返却は未確認。** テストPASSだけを完成とは扱わない。

## GitHub情報

- Repository: https://github.com/shihuiarenjinba-png/Repository-Provisioner-game
- 基準: `main` / `6b404e0e8955dcf96ee3d9cf12b1d3b899f73637`
- 作業ブランチ: `codex/provisioner-bootstrap-20261026`
- 作業開始時HEAD: `c4e73b686a2101a969cd834f483e37dd7e941f52`
- 資料生成時の実装HEAD: `8331d42dacdd3469f24b14dfe0d0a32316b0dc71`
- コミット: `c4e73b6 docs: redirect...`、`8331d42 feat: implement package identity round-trip provisioner`
- Draft PR: https://github.com/shihuiarenjinba-png/Repository-Provisioner-game/pull/1
- 実装・テスト検証HEAD: `e7d86e18a8431990d3e0c5cb2f5a65693e1c147f`
- GitHub CI: https://github.com/shihuiarenjinba-png/Repository-Provisioner-game/actions/runs/40423370942 （Windows / Ubuntu とも成功）
- GitHub Actions: SUCCESS — https://github.com/shihuiarenjinba-png/Repository-Provisioner-game/actions/runs/40382373076
- Provisioner作業ブランチpush: 成功（非force）。
- 差分: Package+Identity CLI、共通Schema、SHA固定取得、Windows build adapter、MSIX/署名/PFN/SID解析、型別台帳・排他、公式Identity照合、GitHub CAS返却、CI、テスト。資料更新commit自体のSHAはDraft PRの最新HEADを正とする。

## テスト情報

- 自動テスト: 49件 / PASS 49 / FAIL 0 / SKIP 0
- Python compile: PASS
- DRY_RUN: PASS。build、Partner Center、GitHub writeは0回。
- 実Factory Identity書込: 未実施。Factory側commit SHAなし。
- 実Windows build/MSIX: 未実施。モックMSIX解析のみPASS。
- Partner Center公式ID: 未取得。Store ID推測機能はない。
- 作成・削除したテストリポジトリ: なし。

## 起動と契約

```powershell
python provisioner.py --input job.json --output result.json
python provisioner.py --input job.json --output result.json `
  --official-identity C:\secure\partner-center-evidence.json --apply
```

- 入力: `schemas/job-v1.0.schema.json`
- 出力: `schemas/result-v1.0.schema.json`
- Factory入口: `GAME` / `AI-Game-Factory`
- 返却先: `shihuiarenjinba-png/AI-Game-Factory`、`codex/factory-autoloop-20261026`、`products/<slug>/store/approved-identity.json`
- Windows-all-auto: `type=game`、`expected_head_sha`付きのIdentity返却契約。
- 成功条件: 実MSIXと公式Identityの完全一致、およびGraphQL CASが返す実commit SHA。

## 必要な権限

- GitHub: Factory metadata/read、contents/read、作業ブランチへのcontents/write。main/release権限は不要。
- Partner Center: 対象製品を閲覧できる認証済み担当者。MFA/CAPTCHA回避や未承認の名前予約は禁止。
- 証明書/token/PFXは環境Secret、credential store、証明書ストアで管理し、Gitへ保存しない。

## 重複・復旧

- `.provisioner-state/game/` でrequest fingerprintを記録。同一完了案件は再ビルドせず結果を再掲。
- 同request_idで別入力/SHA、同時起動、既存Identity相違、HEAD不一致は`CONFLICT`。
- HOLD/RETRYABLE_FAILUREは同一入力で再開可能。429/5xx/timeoutは書込済みか再照会してから再試行。
- 既存approved-identity.jsonは一致時のみ`EXISTING_VERIFIED`。自動上書きしない。

## HOLD項目

1. Git credentialによるProvisioner pushは成功したが、`gh auth status`のtokenは失効中。Factory Identity API書込権限は未確認。
2. 承認済み実Factory job、実Windows build、実MSIXが未提供。
3. 認証済みPartner Centerでの公式Identity確認が未実施。
4. Factory→Provisioner→Windows-all-autoのE2EはChatGPT側の別工程。

CIはWindows/Ubuntuでテストとcompileのみ実行し、権限は`contents: read`。Store提出は行わない。


## 2026-10-27 — Signal Sprint active GAME resume (current)

The historical fixed-branch guidance above is superseded for this one active product. This is a **stage checkpoint**, not a claim of Store or GAME E2E success. Do not generate a second product.

```json
{
  "active_product": "signal-sprint",
  "phase": "WINDOWS_EXE_BUILT__LOCAL_PROVISIONER_HOLD",
  "last_completed_step": "Factory Windows Actions generated unsigned SignalSprint.exe and SHA-pinned GAME intake artifact; Provisioner live local run not yet evidenced",
  "next_action": "On authenticated local Windows: download verified Factory EXE Artifact, validate SHA and job fields, run Provisioner DRY_RUN, then real EXE build and official Partner Center evidence/Identity return on same pinned Factory source branch; integrate Factory official-identity MSIX safety gate before real MSIX",
  "resume_repository": "shihuiarenjinba-png/Repository-Provisioner-game",
  "resume_branch": "codex/game-signal-sprint-exe-identity-stage-20261027",
  "source_sha": "c058cbf7fe38e02d929c67d047d717ff74bd522e",
  "blocked_by": [
    "No proven local Provisioner Windows build of pinned Factory SHA",
    "No authenticated Partner Center official Identity export",
    "Factory safety PR #7 is diverged from Signal Sprint PR #10",
    "No real MSIX / Windows-all-auto game receipt / local GUI QA"
  ],
  "new_product_allowed": false,
  "request_id": "game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e",
  "product_type": "GAME",
  "source_factory": "AI-Game-Factory",
  "source_repository": "shihuiarenjinba-png/AI-Game-Factory",
  "source_branch": "codex/game-signal-sprint-undo-20261027",
  "slug": "signal-sprint",
  "factory_exe_artifact": "game-signal-sprint-exe-c058cbf7fe38e02d929c67d047d717ff74bd522e",
  "factory_exe_artifact_zip_sha256": "e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412",
  "factory_exe_run_id": 40443340158,
  "official_identity_status": "HOLD",
  "real_msix_status": "HOLD",
  "windows_all_auto_type_game_receipt": "HOLD",
  "local_gui_qa": "HOLD"
}
```

### Local Windows operator handoff (no credentials in GitHub)

1. Factory source: [Signal Sprint Draft PR #10](https://github.com/shihuiarenjinba-png/AI-Game-Factory/pull/10), `codex/game-signal-sprint-undo-20261027` at `c058cbf7fe38e02d929c67d047d717ff74bd522e`. Read [Windows EXE run #40443340158](https://github.com/shihuiarenjinba-png/AI-Game-Factory/actions/runs/40443340158) and download Artifact `game-signal-sprint-exe-c058cbf7fe38e02d929c67d047d717ff74bd522e`. Verify the downloaded ZIP SHA-256 `e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412` before extraction. Inside it expect `SignalSprint.exe`, `provenance.json`, `provisioner-request.json`. Independently check executable SHA-256 against `provenance.json` and validate the seven immutable correlation fields. This is **EXE_QA_UNSIGNED**, not an MSIX.
2. Local Provisioner: use this repo branch `codex/game-signal-sprint-exe-identity-stage-20261027` (re-fetch its latest HEAD before running). Start with `python provisioner.py --input <extracted>\\provisioner-request.json --output <local>\\dry-run-result.json`; the artifact's request has `dry_run=true`. Verify `DRY_RUN` and no side effects. For an approved live build, create a local-only copy with **only** `dry_run=false` and run `python provisioner.py --input <local>\\live-job.json --output <local>\\result.json`. This should build the pinned source EXE, preserve its package SHA and report `HOLD / OBTAIN_AUTHENTICATED_OFFICIAL_IDENTITY` until genuine evidence exists. Never commit the local job or evidence.
3. Partner Center: with an authorized session, export the actual Store ID, Identity Name, Publisher, Version, authenticated account, timestamp and evidence URL. Only after local verification, run the same pinned live job with `--official-identity <local-secure>\\partner-center-evidence.json --apply`. Expected **stage**: `github_return.status=APPLIED` or `EXISTING_VERIFIED`, a real **commit** SHA, `status=HOLD`, `next_stage=GITHUB_REBUILD_MSIX`, `windows_all_auto_record=null`. Same request and SHA must replay without a second write; changed SHA/slug with the same request ID is `CONFLICT`.
4. Before actual MSIX: safely integrate Factory official-evidence/CRC gates from its diverged safety PRs into the active product branch without force push or main merge. Build a real MSIX only from authenticated official Identity, validate payload CRC, executable, package SHA and provenance, then deliver only the real `type=game` MSIX to Windows-all-auto and perform local GUI QA plus Windows-checker. CI alone is not E2E PASS.

**No verified local execution, official Identity, real MSIX or bridge receipt has been observed in this run.**


## 2026-10-27 14:09 JST — GAME E2E safety gate correction

- **Active product remains** `signal-sprint`; `new_product_allowed=false`. Do not generate another game.
- **Factory source is immutable:** `AI-Game-Factory/codex/game-signal-sprint-undo-20261027@c058cbf7fe38e02d929c67d047d717ff74bd522e`. Request ID remains `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e` and slug remains `signal-sprint`.
- **Resume repository / branch:** `shihuiarenjinba-png/Repository-Provisioner-game` / `codex/game-signal-sprint-exe-identity-stage-20261027`; re-fetch latest HEAD, never reuse a stale Provisioner checkout. Source Factory SHA above is *not* changed by Provisioner code commits.
- **This cycle's implementation:** MSIX inspection now checks CRC for **all** ZIP members, not just the manifest; bounded total uncompressed size and member count. The Windows-all-auto adapter now carries the original request_id, product_type, source_factory, source_repository, source_branch and source_sha in addition to slug/expected_head_sha. Regression tests cover CRC-corrupted non-manifest payload and immutable receipt fields.
- **Phase:** `WINDOWS_EXE_BUILT__LOCAL_PROVISIONER_HOLD`. Last completed step: Factory unsigned EXE Artifact verified via GitHub metadata; Provisioner code safety fix committed. Local Windows job is **not** verified, and newly committed tests require fresh CI.
- **Next action / local job:** download exact Factory run `40443340158`, Artifact `game-signal-sprint-exe-c058cbf7fe38e02d929c67d047d717ff74bd522e` (ZIP SHA-256 `e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412`); extract `provisioner-request.json`, validate immutable keys, run local DRY_RUN then reviewed live job using this branch. Expected: `DRY_RUN` without side effects, then real EXE SHA and `HOLD / OBTAIN_AUTHENTICATED_OFFICIAL_IDENTITY` until Partner Center authenticated evidence is provided. Identity return target: same pinned Factory branch, `products/signal-sprint/store/approved-identity.json` via CAS, commit SHA required. Any changed Factory HEAD or reused request_id with different SHA/slug => `CONFLICT`.
- **Blocked by:** actual Windows Provisioner build, authenticated official Partner Center Identity, Factory safety PR #7 vs product PR #10 divergence, real MSIX, Windows-all-auto `type=game` receipt, Windows-checker/GUI QA. Do not promote an unsigned EXE to MSIX or E2E PASS. CI and code fixes are not an E2E receipt.
