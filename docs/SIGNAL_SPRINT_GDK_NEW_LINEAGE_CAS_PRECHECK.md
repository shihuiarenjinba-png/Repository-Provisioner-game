# Signal Sprint: new-lineage CAS precheck (read-only)

This contract is for **Signal Sprint only**, Partner Center selection **GDK game**.
It does **not** recover original Artifact `12706862577`, resolve the historical
EXE digest authority conflict, perform CAS, build MSIXVC2, or authorize Store.

## Required evidence

- Original Factory source checkout at immutable
  `c058cbf7fe38e02d929c67d047d717ff74bd522e`, with a clean Git working tree.
- A **new** lineage proposal and its independently archived new ZIP (not a
  renamed or recompressed original ZIP), verified by
  `gdk_new_lineage_reissue_check.py`.
- A saved receipt from that checker, stored outside the Factory checkout.
  The precheck re-executes the original checker against the current ZIP and
  proposal and requires an exact receipt match. All input paths must be outside
  Factory checkout, including symlink aliases.

Run without writing to the Factory checkout:

```bash
python gdk_new_lineage_reissue_check.py \
  --reissue-proposal /safe/new-proposal.json \
  --new-artifact-zip /safe/new-lineage.zip > /safe/new-reissue-receipt.json

python gdk_new_lineage_cas_precheck.py \
  --factory-source-checkout /safe/factory-source \
  --reissue-proposal /safe/new-proposal.json \
  --new-artifact-zip /safe/new-lineage.zip \
  --reissue-receipt /safe/new-reissue-receipt.json
```

Both commands intentionally exit **2** even for a successful check-only
receipt. This is not a workflow failure to bypass. Check the JSON status:
`NEW_LINEAGE_CAS_PREFLIGHT_CHECK_ONLY` means the submitted files are
internally consistent and the source checkout was unchanged. It **never**
sets `ready_for_cas` or `cas_return_pass` to true.

## What is still required

A separately reviewed **new-request CAS contract** must bind a trustworthy
GitHub run/artifact identity and authenticated operator authorization to the
new request; it must not silently reuse the original approved Identity CAS
or the old `gdk_build_intake.py` pins. Existing self-reported JSON is not
cryptographic proof of a GitHub run or a human review.

After that, a separate dedicated build branch, an independently approved
Package Version, GDK SDK validation, real MSIXVC2 creation and Windows E2E
are required. Keep `ARTIFACT_EXACT_BYTES_HOLD` and
`EXPECTED_DIGEST_AUTHORITY_CONFLICT` on the original lineage. The fixed
source branch, main/release, Partner Center and central Windows-all-auto ledger
are out of scope.
