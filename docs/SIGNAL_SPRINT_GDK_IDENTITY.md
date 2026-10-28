# Signal Sprint GDK Identity contract

Signal Sprint is registered as a **GDK game**. The Provisioner therefore supports a second, reviewable Identity input schema in addition to the legacy authenticated-export schema.

The GDK schema binds the user-provided Partner Center identifiers to the immutable Signal Sprint request/source SHA. It carries Store ID, Package Identity Name/Publisher, Publisher Display Name, PFN, Package SID, Xbox Title ID, SCID and MSA App ID.

It deliberately does **not** treat package Version as a Store Identity field. Version is a later GDK package-build gate. After an explicit CAS, the next stage is `BUILD_GDK_MSIXVC_FROM_PINNED_EXE`, not the legacy generic MSIX path.

The resulting `approved-identity.json` records `source=partner_center_user_provided` and `packaging_family=GDK`. No browser authentication material, token, cookie, password, session, PFX/private key or Store submission is introduced.

The immutable Factory source SHA remains:
`c058cbf7fe38e02d929c67d047d717ff74bd522e`.
