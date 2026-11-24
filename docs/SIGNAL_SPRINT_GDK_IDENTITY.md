# Signal Sprint GDK Identity contract

Signal Sprint is registered as a **GDK game**. The Provisioner therefore supports a second, reviewable Identity input schema in addition to the legacy authenticated-export schema.

The GDK schema binds the user-provided Partner Center identifiers to the immutable Signal Sprint request/source SHA. It carries Store ID, Package Identity Name/Publisher, Publisher Display Name, PFN, Package SID, Xbox Title ID, SCID and MSA App ID.

It deliberately does **not** treat package Version as a Store Identity field. Version is a later GDK package-build gate. After an explicit CAS, the next stage is `BUILD_GDK_MSIXVC_FROM_PINNED_EXE`, not the legacy generic MSIX path.

The resulting `approved-identity.json` records `source=partner_center_user_provided` and `packaging_family=GDK`. No browser authentication material, token, cookie, password, session, PFX/private key or Store submission is introduced.

The Identity is currently allowlisted against two **separate immutable request lineages**. The legacy lineage remains available only for its original tuple; the current lineage is separately bound to the current Factory ref:

| Lineage | Request ID | Factory branch | Source SHA |
|---|---|---|---|
| Historical | `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e` | `codex/game-signal-sprint-undo-20261027` | `c058cbf7fe38e02d929c67d047d717ff74bd522e` |
| Current frozen source | `game-signal-sprint-1a349faa41663c417c40710140a4d50c79b62b78` | `codex/signal-sprint-frozen-source-ref-20261124` | `1a349faa41663c417c40710140a4d50c79b62b78` |

Both tuples reuse the same already user-provided GDK Identity identifiers, but the evidence file's request ID and source SHA must match the job exactly. A c058 Identity cannot be paired with the 1a349 request, nor vice versa. A matching slug, self-consistent alternate SHA, or unreviewed branch/request is insufficient.

The current Factory branch was independently observed at the exact frozen source SHA when this contract was prepared. This contract does not modify that branch or the game source.

The new tests exercise the current lineage with `dry_run=true` and `apply=false`; they assert `NOT_APPLIED` and zero GitHub API calls. They prove local Identity/request binding only. They do **not** perform CAS, approve a return, verify a live Partner Center session, or authorize package creation. A real return still requires a separate explicit review and apply decision.
