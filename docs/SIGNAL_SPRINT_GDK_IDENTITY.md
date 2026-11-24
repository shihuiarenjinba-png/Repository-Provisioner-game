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

## Current frozen-source Identity-only return preview

The current 1a349faa lineage has a machine-readable, check-only handoff receipt at:

evidence/signal-sprint-gdk-identity-return-preview.json

Receipt schema: signal-sprint-gdk-identity-return-preview-v1.

The receipt binds:
- Request game-signal-sprint-1a349faa41663c417c40710140a4d50c79b62b78
- Factory repository shihuiarenjinba-png/AI-Game-Factory
- Branch codex/signal-sprint-frozen-source-ref-20261124
- Source SHA 1a349faa41663c417c40710140a4d50c79b62b78
- Registration family GDK
- The already user-provided Partner Center Identity reference, its provided_at timestamp and canonical SHA-256 fingerprint
- Exact return target products/signal-sprint/store/approved-identity.json
- Completed Windows build run, EXE Artifact ID, measured EXE SHA-256, exact workflow head, and downloaded attestation Artifact digest
- Read-only GDK readiness Artifact and derived request-payload fingerprint

The receipt is not a CAS approval or an applied return. It must report dry_run=true, request_submitted=false, cas_status=NOT_APPLIED, zero GitHub API/write calls, and no central-ledger modification. The return target is add-only and expects the frozen source SHA as its head; any later branch movement requires a fresh review rather than an overwrite.

The receipt intentionally omits package Version. Physical GUI, GDK SDK/MakePkg, approved Version/assets, CAS, post-CAS build, MSIXVC2, signing and Store submission remain separate gates. ordinary_msix_allowed=false remains invariant. The historical c058cbf7 lineage remains historical and cannot be paired with the current 1a349faa tuple.

