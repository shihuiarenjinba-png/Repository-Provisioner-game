# Signal Sprint — remote post-CAS GDK build branch bootstrap

**Partner Center selection: GDK game.** This is a Signal Sprint-only
GitHub remote-ref step, not an Identity retrieval or a package build.

The existing `gdk_post_cas_branch_bootstrap.py` creates a **local** build
branch only. The new `gdk_remote_build_branch_bootstrap.py` closes the
remote handoff gap without changing the immutable source branch.

## Prerequisites

1. Official user-provided GDK Identity is already recorded (Store ID
   `9N21MJM7S57P`). No Partner Center login or Identity re-request.
2. An **authorized, actual** CAS return has already created
   `codex/game-signal-sprint-gdk-cas-c058cbf7fe38` in
   `shihuiarenjinba-png/AI-Game-Factory`. This helper does **not**
   perform that CAS and cannot infer its commit SHA.
3. The original source ref remains exactly
   `c058cbf7fe38e02d929c67d047d717ff74bd522e`.
4. The GitHub CLI `gh` is authenticated with repository read access;
   creating the new branch additionally requires write permission.

## Commands

From the Provisioner-game checkout, after the real CAS SHA is known:

```bash
python gdk_remote_build_branch_bootstrap.py --cas-commit-sha ACTUAL_40_HEX_CAS_SHA
```

Default is **read-only** and produces
`GDK_REMOTE_BUILD_BRANCH_CHECK_ONLY`. After separate authorization:

```bash
python gdk_remote_build_branch_bootstrap.py --cas-commit-sha ACTUAL_40_HEX_CAS_SHA --create
```

The optional `--create` uses only GitHub's **create-ref** endpoint, never
an update-ref or force push. It creates
`codex/game-signal-sprint-gdk-build-<first-12-of-CAS-SHA>`
at the reviewed CAS commit. Repeating it while the branch still points
at the same CAS SHA is idempotent. If the branch already points elsewhere,
the operation refuses to overwrite it. Once build-only integration commits
advance that branch, do not rerun this bootstrap to reset it.

Both modes verify the live source and CAS refs, CAS single-parent ancestry,
the exact single added `approved-identity.json`, all pinned GDK Identity
fields, the immutable original EXE digest, the unsigned provenance claim,
and the existing timestamp (without inventing one). Recheck source/CAS refs
before/after the operation and confirm the remote build ref.

## Next gate

After a reviewed build-only integration, check out the actual remote build
branch and run both the Provisioner `gdk_build_intake.py` and Factory
`tools/gdk_post_cas_gate.py` against the same immutable original ZIP.
Their check-only PASS is not `REAL_MSIX_PASS`. An independently approved
October 2026 GDK SDK, real MSIXVC2 packaging, Windows QA and the separate
Windows-all-auto handoff remain required.

No new GAME, generic MSIX/PWA route, source branch mutation, main/release
write, CAS execution, SDK install, merge, Store upload or central ledger edit
is performed by this bootstrap. The branch creation path was exercised only
with synthetic GitHub API fixtures in CI; **no real CAS or remote build branch
was created by adding this code**.
