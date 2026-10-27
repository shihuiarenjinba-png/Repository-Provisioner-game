# Repository-Provisioner-game

`AI-Game-Factory` で確定したGAMEを、SHA固定でWindowsビルド／MSIX検査し、認証済みPartner Centerの公式Identityと一致した場合だけFactory作業ブランチへ返す中間工程です。新規GitHubリポジトリ作成、Store ID推測、Store提出、main/releaseへの書込みは行いません。

## 実行

Python 3.12以降とGit/GitHub CLIを使用します。DRY_RUNは外部読取・ビルド・GitHub書込みを行いません。

```powershell
python provisioner.py --input examples/job.dry-run.json --output test-results/dry-run.json
```

実処理ではFactory作業ブランチの現在HEADと同じ `source_sha`、認証済みPartner Centerセッションから人間が照合した証跡JSON、Windowsビルド環境が必要です。GitHub返却は明示的な `--apply` のときだけ行います。

```powershell
python provisioner.py --input job.json --output result.json `
  --official-identity C:\secure\partner-center-evidence.json --apply
```

返却先リポジトリは `shihuiarenjinba-png/AI-Game-Factory` に固定し、ブランチは入力 `source_branch` と同じ安全な `codex/*` 作業ブランチを使用します。`main`、`release`、不正なブランチ名は拒否します。返却パスは `products/<slug>/store/approved-identity.json` です。入力・出力契約は `schemas/`、運用とHOLD項目は `docs/LOCAL_PROVISIONER_HANDOFF.md` を参照してください。
