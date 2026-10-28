# Signal Sprint — independent GDK dual-gate runner (check-only)

**Partner Center selection: GDK game.** This runner does not perform CAS, SDK packaging, Store submission, Windows E2E, or any GitHub write. It never generates a new game.

## Why this is needed

The Provisioner `gdk_build_intake.py` and Factory `tools/gdk_post_cas_gate.py` must verify the **same post-CAS build checkout**. Both programs have independent checks for the immutable source, CAS ancestry, GDK Identity, original EXE bytes, and dedicated branch naming. The runner invokes both, checks their receipt fields, and reruns the Provisioner gate to detect intervening checkout mutations.

The Factory gate is **tooling**, not a source product file. It may be executed from a separate, reviewed checkout of Factory Draft PR #14 (or a later reviewed descendant). The actual build checkout must be rooted at the immutable source SHA, with an explicitly authorized Identity-only CAS commit and dedicated `codex/game-signal-sprint-gdk-build-*` branch. **Do not move the immutable source branch or cherry-pick product changes to obtain tooling.**

## Before execution

1. Obtain the original pinned GitHub Actions artifact ZIP **with identical bytes**. Artifact ID `12706862577`, SHA-256 `e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412`, internal EXE SHA-256 `9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad`. The GitHub artifact was reported to expire on **2026-11-01 03:18:51 UTC**; use the already-preserved byte-identical copy if necessary. Never substitute a rebuild.
2. Only after explicit authorization, obtain the **real** CAS SHA and build HEAD SHA. The CAS must be a single-parent child of `c058cbf7fe38e02d929c67d047d717ff74bd522e`, modifying only `products/signal-sprint/store/approved-identity.json`. No guessed CAS.
3. Review the Factory gate script in a **separate trusted tooling checkout** of Factory PR #14. Record its SHA-256 independently from the run inputs. Never accept a digest supplied alongside an untrusted script as proof of trust.
4. Ensure the Factory build checkout is clean, non-shallow, and has the original source ref pinned at the immutable SHA. Keep all receipts outside that checkout.

## Command

```bash
python gdk_dual_gate.py \
  --factory-checkout /path/to/signal-sprint-post-cas-build \
  --pinned-artifact-zip /path/to/pinned-original.zip \
  --cas-commit-sha ACTUAL_CAS_SHA \
  --build-head-sha ACTUAL_BUILD_HEAD_SHA \
  --factory-gate-script /path/to/reviewed-factory-tools/gdk_post_cas_gate.py \
  --trusted-factory-gate-sha256 INDEPENDENTLY_REVIEWED_64_HEX_SHA256
```

Successful stdout is a single JSON object with `status=GDK_DUAL_GATE_CHECK_ONLY`, `partner_center_selection=GDK_GAME`, the original source SHA, real CAS/build SHAs, hashes of the two check-only receipts, and `next_stage=GDK_SDK_PREFLIGHT_PENDING`. All real-package, SDK validation, E2E and Store flags remain **false**. The temporary Provisioner receipt is deleted after use.

Any gate rejection, untrusted script SHA, modified ZIP, inconsistent receipts, changed checkout, malformed JSON, or missing prerequisite produces **HOLD**, not a synthetic success. This runner must not be used to mark `POST_IDENTITY_READY`, `CAS_RETURN_PASS`, `REAL_MSIX_PASS`, or `E2E PASS` before the actual evidence exists.

## Remaining work

- Real Signal Sprint CAS return has **not** been executed. User-provided GDK Identity is received, but a committed CAS result is separate.
- Windows GDK SDK must generate a **real MSIXVC/MSIXVC2** using the pinned EXE, with separately reviewed Package Version and Reserved Display Name.
- Re-run staging/SDK pack plan and result-intake, then use the trusted-manifest-hash receiver before the 36-minute Windows/E2E owner updates the central ledger.
- The user does **not** need to re-supply Store ID, Identity Name, Publisher, Publisher Display Name, PFN, Package SID, Xbox Title ID, SCID, or MSA App ID.
