# LOCAL_PROVISIONER_HANDOFF — GAME

更新日: 2026-10-27 (Asia/Tokyo)

## 現行統合判定（旧スナップショットより優先）

**HOLD — Signal SprintのSHA固定Windows EXE生成と検査までは実証済み。公式Partner Center Identity、Factory CAS書戻し、正式IdentityによるMSIX再生成、Windows-all-auto受領、Windows-checker/UI QAは未実施。** Store提出は0件で、新規製品の生成は禁止を維持する。

- 統合元: `codex/game-signal-sprint-exe-identity-stage-20261027` / `9a27eb3b7bb9bab4898acc42b028d1d0a0b04cf7`
- ローカル作業ブランチ: `codex/e2e-belt-connection-20261027`
- 現行Draft PR: https://github.com/shihuiarenjinba-png/Repository-Provisioner-game/pull/7
- 自動テスト: **70件 / PASS 70 / FAIL 0 / SKIP 0**
- 共通Schema正規化SHA-256: job `0fbdaf38d25563bf60f756fbf2dd03468517584fb7b05b1bf5f942bf27c1d599` / result `1264f0285283c77aceb2956d687ff3898657578b82ba37ff475a8565f8709310`
- PowerShell 7 (`pwsh`)を優先し、未導入環境のみWindows PowerShellへフォールバックする。長いビルド失敗ログは秘密を伏せ、先頭と根本原因を含む末尾を保持する。

### 実Signal Sprint証跡

- Factory source: `shihuiarenjinba-png/AI-Game-Factory` / `codex/game-signal-sprint-undo-20261027` / `c058cbf7fe38e02d929c67d047d717ff74bd522e`
- request_id: `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e`
- Factory Artifact ZIP SHA-256: `e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412`
- Artifact内EXE SHA-256: `9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad`（provenanceと実バイト一致）
- ローカル再ビルドEXE: 11,387,518 bytes / SHA-256 `e8517df8cd31a40e5ce72afdd4e6a4d63626fb99f7ff8a4fa3296ff8deef05f4` / Authenticode `NOTSIGNED`
- DRY_RUN: `DRY_RUN`、副作用0。
- live結果: `HOLD` / `OBTAIN_AUTHENTICATED_OFFICIAL_IDENTITY`。packageは`INSPECTED`、kind=`exe`。GitHub返却`NOT_APPLIED`、Windows-all-auto recordは`null`。
- 実Factory書戻しcommit SHA、Store ID、PFN、Package SID、正式MSIX URL: **なし**。値は推測していない。

### 正確な再開地点

認証済みPartner Centerから、この同一製品のStore ID、Identity Name、Publisher、Version、PFN、Package SID、認証アカウント、時刻、公式evidence URLを安全なローカルファイルへ取得する。相関7項目とEXE証跡を再確認後、同じrequest_idで`--official-identity <secure-path> --apply`を実行し、Factory作業ブランチHEADのCASが成功した場合だけ次のMSIX再生成へ渡す。既存IdentityやHEADが異なる場合はCONFLICT。

## 旧判定

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
  "phase": "LOCAL_EXE_INSPECTED__PARTNER_CENTER_IDENTITY_HOLD",
  "last_completed_step": "Factory Artifact verified; Provisioner DRY_RUN passed; pinned Factory SHA rebuilt locally into a real unsigned PE EXE and inspected",
  "next_action": "Obtain authenticated Partner Center evidence for this exact product, then perform the reviewed CAS Identity return on the same pinned Factory work branch before any MSIX rebuild",
  "resume_repository": "shihuiarenjinba-png/Repository-Provisioner-game",
  "resume_branch": "codex/game-signal-sprint-exe-identity-stage-20261027",
  "source_sha": "c058cbf7fe38e02d929c67d047d717ff74bd522e",
  "blocked_by": [
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

**Local fixed-SHA EXE execution and inspection are verified. Official Identity, real MSIX, bridge receipt, GUI QA and Store submission have not occurred.**


## 2026-10-27 14:09 JST — GAME E2E safety gate correction

- **Active product remains** `signal-sprint`; `new_product_allowed=false`. Do not generate another game.
- **Factory source is immutable:** `AI-Game-Factory/codex/game-signal-sprint-undo-20261027@c058cbf7fe38e02d929c67d047d717ff74bd522e`. Request ID remains `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e` and slug remains `signal-sprint`.
- **Resume repository / branch:** `shihuiarenjinba-png/Repository-Provisioner-game` / `codex/game-signal-sprint-exe-identity-stage-20261027`; re-fetch latest HEAD, never reuse a stale Provisioner checkout. Source Factory SHA above is *not* changed by Provisioner code commits.
- **This cycle's implementation:** MSIX inspection now checks CRC for **all** ZIP members, not just the manifest; bounded total uncompressed size and member count. The Windows-all-auto adapter now carries the original request_id, product_type, source_factory, source_repository, source_branch and source_sha in addition to slug/expected_head_sha. Regression tests cover CRC-corrupted non-manifest payload and immutable receipt fields.
- **Phase:** `LOCAL_EXE_INSPECTED__PARTNER_CENTER_IDENTITY_HOLD`. Factory unsigned EXE Artifact verification、DRY_RUN、固定SHAのローカル再ビルドとPE/署名/SHA検査まで完了。
- **Next action:** 認証済みPartner Center証拠を取得し、同一相関キーを再確認後、同じFactory作業ブランチの`products/signal-sprint/store/approved-identity.json`へCAS返却する。commit SHA必須。Factory HEAD変更または同request_idでSHA/slug相違は`CONFLICT`。
- **Blocked by:** authenticated official Partner Center Identity、Factory safety PR #7とproduct PR #10の安全な統合、real MSIX、Windows-all-auto `type=game` receipt、Windows-checker/GUI QA。unsigned EXEをMSIXまたはE2E PASSとして扱わない。

## 2026-10-27 15:12 JST — Signal Sprint GAME MSIX package-safety checkpoint

- **Active product:** `signal-sprint`; `new_product_allowed=false`. This is a package gate improvement, **not** a new game or a claim of real MSIX delivery.
- **Source Factory:** `shihuiarenjinba-png/AI-Game-Factory`, `codex/game-signal-sprint-undo-20261027`, immutable `c058cbf7fe38e02d929c67d047d717ff74bd522e`. `request_id=game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e`.
- **Provisioner safety patch:** Draft [PR #8](https://github.com/shihuiarenjinba-png/Repository-Provisioner-game/pull/8), `codex/game-msix-package-safety-20261027-1510`, based on GAME integration [PR #7](https://github.com/shihuiarenjinba-png/Repository-Provisioner-game/pull/7) at `7ac69a43f3b06402a942b7f31ec3070f67c67688`. Patch commits: `c6de7c18a7182c500de7f7c32f0875fcb9c046a6`, `d9c6f5d61eeb2fe11d08d51d1280e317d43f78a6`.
- **Fixed code paths:** `package_identity_provisioner.py` and `tests/test_package_identity_pipeline.py`. MSIX now rejects symlinked/oversized input, unsafe/duplicate ZIP members, ZIP symlinks, excessive expansion, missing or malformed BlockMap/Content Types/manifest, CRC-corrupted payloads, and GAME MSIX lacking an executable. These are fail-closed local checks, not Microsoft certification.
- **Factory handoff fix already exists:** Factory [Draft PR #11](https://github.com/shihuiarenjinba-png/AI-Game-Factory/pull/11) at `6a0f69fa371e1a87a5247974a436f8a7e5816cac`, CI [#40456038174](https://github.com/shihuiarenjinba-png/AI-Game-Factory/actions/runs/40456038174) PASS. It separates immutable `source_sha` from `factory_head_sha`. **Do not integrate it into the fixed Factory source branch before official Identity CAS**.
- **Current phase:** `LOCAL_EXE_INSPECTED__PARTNER_CENTER_IDENTITY_HOLD`.
- **Last completed step:** Signal Sprint EXE artifact/DRY_RUN/local fixed-SHA PE build inspected; Factory PR #11 correlation fix implemented and CI green; Provisioner PR #8 MSIX safety code and regression tests committed.
- **Next action:** Obtain authenticated Partner Center Identity evidence for exact request, verify Factory source branch still equals pinned SHA, then CAS-return `products/signal-sprint/store/approved-identity.json` on that original Factory branch and capture actual return commit SHA. **Only after CAS** integrate reviewed Factory safety and PR #11 onto a separate `codex/*` build branch, produce and verify real MakeAppx MSIX, deliver `type=game` to Windows-all-auto, run Checker and real Windows GUI QA.
- **Resume repository/branch:** `shihuiarenjinba-png/Repository-Provisioner-game` / `codex/game-msix-package-safety-20261027-1510` for this safety patch; `codex/e2e-belt-connection-20261027` remains the live integration baseline until reviewed.
- **Blocked by:** authenticated official Partner Center Identity, Factory CAS return, post-CAS Factory safety integration, real MSIX, Windows-all-auto GAME receipt, Checker/GUI QA.
- **Status:** `HOLD` for official Identity / MSIX / bridge / local QA; no Store submission, merge, force push or main/release changes. Re-fetch current PR #7 and #8 HEAD before cherry-picking or running local work.
