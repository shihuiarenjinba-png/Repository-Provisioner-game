# Signal Sprint: GDK retail config and Xbox services decision

Partner Center selection: **GDK game**. This change applies only to Signal Sprint and does not change the immutable source, pinned executable, received Identity contract, or package route.

## Why the MicrosoftGame.config omits two fields

Microsoft's *Create a game package and upload it in Partner Center* guide states that GDK games **not using Xbox services must omit MSAAppId, TitleId and ExtendedAttributeList** from the retail MicrosoftGame.config; otherwise players can encounter Xbox sign-in errors at launch. The same guide requires a real GDK package and Store certification. See https://learn.microsoft.com/en-us/gaming/game-publishing/tutorial-xbox-managed/how-to-create-a-package .

The pinned SignalSprint.exe in `signal-sprint-factory-exe-c058cbf7.zip` was independently rehashed during this change. Its SHA-256 is `9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad`, and the ZIP SHA-256 is `e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412`. Static PE import inspection found USER32.dll, COMCTL32.dll, KERNEL32.dll, ADVAPI32.dll and GDI32.dll, but no Xbox service imports or recognizable Xbox Live initialization strings. **This is static evidence, not a runtime certification**. The current product is treated as a standalone Win32 game without Xbox services.

Accordingly the generated retail `MicrosoftGame.config` retains the reviewed `Identity`, `StoreId`, `ExecutableList` and `ShellVisuals`, but omits `MSAAppId` and `TitleId`. The already received Xbox Title ID, SCID and MSA App ID are **still required and verified** in the upstream user-provided GDK Identity contract. Omitting unused runtime elements is not discarding or inventing Identity values.

## Release gate

- Keep the Factory source ref at `c058cbf7fe38e02d929c67d047d717ff74bd522e`. Never rebuild the pinned executable as a substitute.
- Verify on the eventual Windows test machine that Signal Sprint truly does not call Xbox services. If it does, **HOLD** this config choice and review the GDK services integration; do not silently add elements based solely on the availability of Partner Center IDs.
- Verify the reviewed reserved display name and choose package version at the later build gate. No guessed values.
- Run the real October 2026 or later GDK `makepkg pack /msixvc2`, Submission Validator, independent package/sidecar hash checks, install/launch/GUI QA, then certification steps. The existing CI is synthetic contract validation only.
- No Partner Center login, upload, Store submission, local registry or security policy modification in this change.

Current stage: Identity received, **CAS pending**; REAL_MSIX_PASS and E2E PASS are not achieved.
