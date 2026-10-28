# Signal Sprint — dedicated GDK post-CAS build branch gate

**Partner Center selection: GDK game**. This is a read-only, no-SDK gate
for the one pinned Signal Sprint product. It does not perform CAS, makepkg,
Windows install, GUI QA, Store submission, or change any Git refs.

## Why this gate exists

The existing `gdk_build_intake.py` proves that the actual CAS commit is a
direct child of the immutable source SHA, that CAS changes only the reviewed
Identity, and that the build HEAD descends from CAS. That does **not** by itself
prove the checkout is on a dedicated build branch, clean, or that post-CAS
integration commits left the product tree untouched.

`gdk_build_branch_gate.py` reuses the actual CAS verifier and additionally
requires all of the following:

- Checked-out named branch matching `codex/game-signal-sprint-gdk-build-*`;
  the immutable source branch, detached HEAD and ordinary MSIX branches fail.
- Clean Git checkout (no tracked edits or untracked files). Keep staging,
  artifact ZIP and receipts **outside** the Factory checkout.
- No changed files under `products/signal-sprint` between the CAS commit
  and build HEAD, including the approved Identity and product sources.
- Actual CAS Identity Git blob ID recorded in the check-only receipt.
- Separate immutable `source_sha`, actual `cas_commit_sha`, and actual
  `factory_head_sha`. Do not reuse the original EXE from a new build.

## Invocation — only after authorized CAS

```bash
python gdk_build_branch_gate.py \
  --factory-checkout /path/to/AI-Game-Factory-post-cas \
  --cas-commit-sha ACTUAL_CAS_SHA \
  --build-head-sha ACTUAL_BUILD_SHA
```

A successful response is `GDK_BUILD_BRANCH_CHECK_ONLY` with
`gdk_sdk_validated=false`, `real_msixvc_built=false`, and
`store_submitted=false`. It does **not** establish `CAS_RETURN_PASS`,
`REAL_MSIX_PASS` or `E2E PASS`. An absent authorized CAS is a legitimate
blocker, not a reason to fabricate a receipt or move the fixed source branch.

## Integration with Windows GDK build

After this gate, execute `gdk_msixvc2_preflight.py` and
`gdk_msixvc2_recheck.py` against the same checkout and the preserved original
artifact ZIP. The Windows build owner must independently validate the
MicrosoftGame.config with the installed GDK SDK, rehash all six staging files
immediately before makepkg, and only then attempt the GDK MSIXVC2 package.
A Git branch policy check cannot replace SDK validation or protect against
concurrent filesystem mutation.

The current product is **GDK_GAME**, not generic MSIX/PWA. The user's
Partner Center Identity (Store ID 9N21MJM7S57P and the Xbox identifiers) has
already been received; do not ask for it again. Package Version and independently
reviewed display name are later build-gate inputs, not Identity guesses.

Source SHA: `c058cbf7fe38e02d929c67d047d717ff74bd522e`.
Request ID: `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e`.
No new GAME generation, main/release write, force push, merge or Store upload.
