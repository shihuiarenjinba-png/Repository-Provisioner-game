# Signal Sprint — Factory-v1 new-lineage evidence adapter (check-only)

Partner Center selection: **GDK game**. The official Identity is already user-provided; no additional Identity retrieval or Partner Center access is required.

## Actual evidence / reason for this adapter

AI-Game-Factory Draft PR #15 emitted a real Windows EXE through GitHub run [41361263698](https://github.com/shihuiarenjinba-png/AI-Game-Factory/actions/runs/41361263698) (PR-body one-shot, `pull_request`, not `workflow_dispatch`), Artifact **13105352227**. Factory v1 emits an **outer GitHub artifact ZIP** containing `new-lineage.zip` and `lineage-receipt.json`. The inner ZIP contains `SignalSprint.exe`, `provenance.json`, `provisioner-request.json`.

The older `gdk_new_lineage_reissue_check.py` requires a different proposal/request schema, Artifact ID already inside the inner provenance, and a different manual-workflow event. Do **not** rewrite Factory history, mutate the receipt after upload, or weaken the legacy validator to make that old contract appear to pass. This adapter is a separate, fail-closed bridge for the observed Factory-v1 format. It reuses the existing allowlisted, read-only GitHub API GET client.

Actual separately observed SHA-256 values:

| Layer | SHA-256 |
|---|---|
| GitHub outer ZIP | `843496682662e871fc6e1b5df83ace2c6b01ef314cfc466b5072290890b70a8f` |
| Factory inner `new-lineage.zip` | `46aff1ee7570459235c9e7ca7fb1faf6f494dc8100e62b6e132c6d07a6291b71` |
| `SignalSprint.exe` | `beb683b61b4fa4b2ec90fe1d413363c8a535bd4cb72b41b54b03a9685f516ee0` |

These are **new lineage** digests. They do not replace expired old Artifact #12706862577 or reconcile its EXE SHA authority conflict.

## Read-only check

Download the **original outer GitHub Actions artifact ZIP** without repacking, then run:

```sh
python gdk_factory_lineage_adapter.py \
  --outer-artifact-zip /outside-factory/github-actions-artifact-13105352227.zip \
  --run-id 41361263698 \
  --artifact-id 13105352227
```

`GITHUB_TOKEN` is optional for GitHub REST rate limits; never include it in a receipt. The tool performs only two allowlisted GET requests to the official GitHub API. It verifies run/repository/PR #15/branch/build HEAD, artifact metadata/digest/size, both ZIP layers, EXE SHA, provenance/request, fixed source SHA, old/new request separation and legacy HOLD flags. GitHub Artifact ID is resolved **after** upload through the API and is not trusted from Factory's pre-upload receipt.

The output may report `FACTORY_NEW_LINEAGE_GITHUB_CHECK_ONLY`, but the CLI **always exits 2** because check-only is not CAS authorization. Untrusted approval/foreign Identity claims, unsigned Version/asset approval, wrong product, old request, rehashed ZIP, wrong event/run/artifact or missing evidence are rejected.

## Separate gates that remain closed

- Original immutable source: `c058cbf7fe38e02d929c67d047d717ff74bd522e`; never modify its branch.
- Old request: `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e`; original ZIP still `ARTIFACT_EXACT_BYTES_HOLD`.
- New request: `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e-reissue-sprint-41361263698-41361263698`; distinct lineage only.
- Human approver authentication and explicit new-request CAS authorization: **HOLD**.
- Package Version and GDK assets: **unapproved**, not inferred from Identity or EXE.
- GDK SDK build, real MSIXVC2, Windows E2E, Store submission: **NOT EXECUTED**.

This is an adapter for evidence, not a replacement for post-CAS GDK package intake. Do not update Windows-all-auto's central ledger here; that is owned by the Windows/E2E track.
