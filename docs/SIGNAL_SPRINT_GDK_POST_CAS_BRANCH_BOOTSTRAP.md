# Signal Sprint — post-CAS GDK build branch bootstrap

**Partner Center selection: GDK game.** The user's official GDK Identity is received. This helper never accesses Partner Center.

After authorized dedicated CAS return, invoke:

    python gdk_post_cas_branch_bootstrap.py --factory-checkout /path/to/AI-Game-Factory --cas-commit-sha ACTUAL_CAS_SHA

Default is check-only, no writes. It requires immutable source ref at c058cbf7fe38e02d929c67d047d717ff74bd522e; the dedicated CAS ref pointing to the declared commit; exactly one parent (the immutable source); exactly one changed file (products/signal-sprint/store/approved-identity.json); and complete reviewed GDK Identity, EXE digest, and provenance.

After independent authorization, add --create. It atomically creates only a **local** branch ref named codex/game-signal-sprint-gdk-build-<first-12-chars-of-CAS-SHA>. Re-running with the same CAS SHA is idempotent; a ref already pointing elsewhere is a conflict. It never checks out, pushes, force-updates, merges, packages, changes the immutable source branch, or edits the central ledger.

The returned factory_head_sha equals the CAS SHA only immediately after local creation. After separately reviewed build-only integration commits, supply their actual new build HEAD to gdk_build_branch_gate.py and Factory tools/gdk_post_cas_gate.py. Source SHA, CAS SHA, and build HEAD must remain separate.

**Current blocker:** No real CAS commit has been verified or created. Synthetic Git fixture tests do not establish CAS_RETURN_PASS, REAL_MSIX_PASS or E2E PASS.

Pinned original ZIP SHA-256: e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412
Pinned EXE SHA-256: 9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad

Do not rebuild the EXE, use ordinary MSIX/PWA, change Windows security policy, or submit to Store.
