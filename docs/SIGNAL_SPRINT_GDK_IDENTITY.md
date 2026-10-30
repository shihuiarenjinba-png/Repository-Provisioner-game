# Signal Sprint GDK Identity contract

Signal Sprint is registered as a **GDK game**. The Provisioner therefore supports a second, reviewable Identity input schema in addition to the legacy authenticated-export schema.

The GDK schema binds the user-provided Partner Center identifiers to the immutable Signal Sprint request/source SHA. It carries Store ID, Package Identity Name/Publisher, Publisher Display Name, PFN, Package SID, Xbox Title ID, SCID and MSA App ID.

It deliberately does **not** treat package Version as a Store Identity field. Version is a later GDK package-build gate. After an explicit CAS, the next stage is `BUILD_GDK_MSIXVC_FROM_PINNED_EXE`, not the legacy generic MSIX path.

The resulting `approved-identity.json` records `source=partner_center_user_provided` and `packaging_family=GDK`. No browser authentication material, token, cookie, password, session, PFX/private key or Store submission is introduced.

The immutable Factory source SHA remains:
`c058cbf7fe38e02d929c67d047d717ff74bd522e`.

## Dedicated CAS branch (source preservation)

The Signal Sprint GDK return MUST target `codex/game-signal-sprint-gdk-cas-c058cbf7fe38`, never `codex/game-signal-sprint-undo-20261027`. The immutable source branch must remain at `c058cbf7fe38e02d929c67d047d717ff74bd522e` before and after CAS. With explicit `--apply`, the Provisioner creates the CAS branch at that source SHA if absent, then uses GitHub's expected-head atomic commit to add only `products/signal-sprint/store/approved-identity.json`. An interrupted run may leave an empty CAS branch at the source SHA; retry can safely complete it. An existing Identity is accepted only if the CAS commit has the immutable source as its sole parent, changes only the Identity file, matches reviewed evidence, and both source and CAS refs remain unchanged during verification. No real CAS is authorized by this documentation alone.

After a confirmed CAS, create the separate `codex/game-signal-sprint-gdk-build-*` branch from the actual CAS commit and run both independent Factory/Provisioner post-CAS gates before packaging. The original EXE SHA must not change.
