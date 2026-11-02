# Signal Sprint — live GitHub evidence gate for a new GDK build lineage

Scope: Signal Sprint only. Partner Center selection: **GDK game**. No new product.

## Why this gate exists

The original Factory Artifact `12706862577` expired. Its ZIP SHA-256 was recorded as
`e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412`.
The original workflow log supports EXE SHA `9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad`;
an older central handoff instead says
`e8517df8cd31a40e5ce72afdd4e6a4d63626fb99f7ff8a4fa3296ff8deef05f4`.
Without the original ZIP these values **cannot** be reconciled by assertion.
The original request remains `ARTIFACT_EXACT_BYTES_HOLD`.

The existing `gdk_new_lineage_reissue_check.py` and
`gdk_new_lineage_cas_precheck.py` rehash the new ZIP and verify local receipts.
They cannot establish that a user-entered GitHub run/artifact ID really points
to the same successful Factory build.

`gdk_new_lineage_github_evidence.py` adds an independent **live GET** check:
- GitHub REST run ID, repository ID/name, head repository, successful conclusion,
  manually dispatched run, first attempt, dedicated reissue workflow and branch.
- Separate immutable `source_sha` and observed `github_build_head_sha`.
- GitHub REST artifact ID, parent run ID, non-expired status, name, positive size,
  official download URL, and GitHub artifact digest matching the **locally
  independently rehashed ZIP digest** in the prior CAS precheck receipt.
- Reject missing GitHub digest, wrong product, fork, old workflow, reused
  original source as build head, or mismatched run/artifact evidence.
- The live HTTP response is fetched from a fixed GitHub API host/path, not from
  an operator-controlled URL. No write endpoints or browser sessions are used.

## How to check (once a new lineage exists)

```sh
python gdk_new_lineage_github_evidence.py \
  --factory-source-checkout /read-only/factory-source \
  --reissue-proposal /outside-factory/new-proposal.json \
  --new-artifact-zip /outside-factory/new-artifact.zip \
  --reissue-receipt /outside-factory/new-reissue-receipt.json
```

Optional `GITHUB_TOKEN` supports GitHub REST API rate limits. Never place it in
the proposal or receipt. The CLI **always exits 2**, including on check-only,
because success is not CAS authorization.

## Current hard stops

1. There is no verified new-lineage ZIP, new request, dedicated Factory
   `.github/workflows/game-signal-sprint-reissue.yml`, or reviewed build head.
   The existing fixed-source workflow creates the **original** request ID;
   rerunning it does not create a distinct lineage.
2. A new workflow must be prepared on a **separate branch** without modifying
   `codex/game-signal-sprint-undo-20261027` or its immutable commit
   `c058cbf7fe38e02d929c67d047d717ff74bd522e`.
3. The observed new build head is **not** an approved head. A trusted, separately
   authenticated reviewer must approve the exact new build head, new request,
   build/run/artifact IDs, ZIP/EXE hashes, and lineage before any new-request CAS.
4. Package Version approval is a **different** later gate. GDK SDK validation,
   actual MSIXVC/MSIXVC2 generation, Windows E2E and Store submission remain HOLD.
5. Neither this check nor a future reissue clears the original artifact HOLD,
   replaces the old ZIP bytes, or resolves the old EXE SHA authority conflict.

No main/release changes, no merge, no force push, no Partner Center operations,
no CAS, and no Store submission are part of this gate.
