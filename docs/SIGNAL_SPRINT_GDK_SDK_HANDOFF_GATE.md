# Signal Sprint — GDK dual gate → SDK pack plan (check-only)

**Partner Center selection: GDK game.** This runner is restricted to Signal Sprint's immutable source SHA `c058cbf7fe38e02d929c67d047d717ff74bd522e` and request ID `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e`. It never creates a new game, changes a source ref, executes CAS, runs the GDK SDK, uploads to Partner Center, or writes the central Windows/E2E ledger.

## Purpose and trust boundary

`gdk_sdk_handoff_gate.py` binds the independently reviewed Factory + Provisioner post-CAS checks (`gdk_dual_gate.py`) to the actual, freshly reverified GDK staging pack plan (`gdk_sdk_pack_plan.py`) **on the same checkout**. It runs dual gate → pack plan → dual gate → pack plan and rejects any receipt or staging differences. The Factory tool's SHA-256 must be supplied from an independently trusted review, not copied from untrusted inputs. The original GitHub Actions ZIP must match `e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412`, and its EXE must match `9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad`.

The GDK Package Version and reviewed Reserved Display Name are **build-gate inputs**, not assumed from the Partner Center Identity. Store ID, Name, Publisher, Publisher Display Name, PFN, Package SID, Xbox Title ID, SCID and MSA App ID were supplied by the user already; do not request them again.

## Prerequisites

- Real, authorized Identity-only CAS commit and dedicated post-CAS build branch `codex/game-signal-sprint-gdk-build-*`. Do not move `codex/game-signal-sprint-undo-20261027` from its immutable SHA.
- A clean, full Git checkout at the exact build HEAD, with original source ancestry and reviewed approved Identity; original ZIP bytes, not a rebuild.
- Separate reviewed Factory tooling checkout containing `tools/gdk_post_cas_gate.py`, with independently pinned SHA-256.
- A previously generated GDK staging directory containing exactly the approved EXE, MicrosoftGame.config and four approved PNGs, plus a saved staging preflight JSON receipt **outside** the checkout.
- An existing, empty output directory separate from staging and source.

## Example

```bash
python gdk_sdk_handoff_gate.py \
  --factory-checkout /path/to/post-cas-gdk-build \
  --pinned-artifact-zip /path/to/original-pinned.zip \
  --cas-commit-sha ACTUAL_CAS_SHA \
  --build-head-sha ACTUAL_BUILD_SHA \
  --factory-gate-script /path/to/reviewed-factory-tool/gdk_post_cas_gate.py \
  --trusted-factory-gate-sha256 INDEPENDENTLY_REVIEWED_SHA256 \
  --staging-dir /path/to/gdk-staging \
  --package-version REVIEWED_A_B_C_0 \
  --reviewed-display-name REVIEWED_PARTNER_CENTER_NAME \
  --preflight-receipt /path/to/preflight.json \
  --output-dir /path/to/empty-sdk-output
```

A successful receipt has `status=GDK_SDK_HANDOFF_CHECK_ONLY`, the immutable source, real CAS/build SHAs, independently pinned Factory gate SHA, SHA-256 digests for both gates' canonical receipts, actual staged-file hashes, the reviewed Package Version and display name, and **a non-executed** `makepkg.exe pack /msixvc2` command plan. SDK, package, Store and Windows E2E success flags remain false. No actual package is generated.

A failure is `HOLD` with a nonzero exit. Do not treat this as `CAS_RETURN_PASS`, `REAL_MSIX_PASS` or `E2E PASS`. A future Windows GDK builder **must re-run** the real Git/CAS/Identity/staging and pinned-binary gates immediately before invoking the SDK; this check-only snapshot does not prevent changes after it returns. The SDK output must be separately validated, hashed, and transferred through the existing trusted-manifest-hash receiver before the Windows/E2E owner updates its ledger.

The 12-minute GAME owner is limited to Factory and Provisioner. The 36-minute Windows/E2E owner owns the central queue and ledger. No Store submission without user authorization.
