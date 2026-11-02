# Signal Sprint — actual Windows EXE screenshot evidence (2026-11-02 JST)

## Scope and immutable lineage

Factory **run #41361263698**, Artifact **#13105352227**, immutable source `c058cbf7fe38e02d929c67d047d717ff74bd522e`, new request `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e-reissue-sprint-41361263698-41361263698`, EXE SHA-256 `beb683b61b4fa4b2ec90fe1d413363c8a535bd4cb72b41b54b03a9685f516ee0`. Partner Center selection **GDK game**.

Windows CI [run #41398642854](https://github.com/shihuiarenjinba-png/AI-Game-Factory/actions/runs/41398642854) downloaded the existing GitHub artifact, verified run/artifact ID, inner ZIP, receipt, source, request and EXE SHA, then started the **real** `SignalSprint.exe`. A PyInstaller child process owned the visible Tk window. This is neither a fake GUI nor a rebuild.

## Actual screenshots

Evidence artifact: [#13120481943](https://github.com/shihuiarenjinba-png/AI-Game-Factory/actions/runs/41398642854/artifacts/13120481943).

| Image | Dimensions | SHA-256 | Observed |
| --- | --- | --- | --- |
| `signal-sprint-gui.png` | 1024×768 | `78fbe24464731765268e9268a024293d83a361bcbe038d706b3993daf5e38422` | Starting player marker at upper-left tile; Moves left **30**; Cells **0/3**; objective, arrows/WASD, Restart, Undo, Save, Load, JP button visible |
| `signal-sprint-gui.after-right.png` | 1024×768 | `c536fceb77ec6a510f88782ac4afe969d8d11ef36c8ed7998d16c9d2c879b3c5` | Player marker visibly moves one tile right; Moves left **29**; Cells **0/3**; message changes to “Find the shortest safe route.” |

The screenshot pair demonstrates **one real keyboard move and a visible counter update**. The CI JSON conservatively reports `first_move_ui_observed=false` because Windows UIAutomation did not expose the Tk label text; visual inspection of screenshots is separate evidence, not a machine-verifiable counter assertion.

**Consumer issue:** at the tested 1024×768 Windows desktop, the taskbar visibly overlaps the lower portion of the game's nominal 1024×768 window. The bottom of the board/control area is at risk of clipping, and the game uses a single fixed board. This fails the intended consumer-grade 1024×768 layout goal until a future source revision is authorized and verified. JP toggle exists but the underlying status/message strings remain English in the pinned source.

## Honest outcome

CI receipt status: `WINDOWS_GUI_CHECK_ONLY_HOLD`; reason: `TK_GAME_TEXT_NOT_EXPOSED_TO_UIAUTOMATION_SCREENSHOT_ONLY`. Actual process/window and screenshot capture **PASS**; real RIGHT input and visible move/counter change **observed in screenshots**. Failure explanation, loss/retry, timing to first move, 125%/150% DPI, human 30-second comprehension, and replay value **not verified**. The Windows GUI job intentionally fails closed. Normal Windows/Ubuntu Provisioner unit CI remains separate.

Original expired Artifact #12706862577 and EXE authority conflict remain historical HOLD. New-request authenticated CAS, Package Version and four approved assets, GDK SDK, real MSIXVC2, Windows E2E, and SALE_READY all remain HOLD. Official Identity is already received; no further Identity request. No central ledger, source branch, main/release, CAS or Store mutation was performed.

**Future source revision acceptance:** use a responsive window constrained to the Windows work area at 1024×768 and 125%/150% DPI, show all game controls without taskbar occlusion, translate all gameplay messages on JP selection, add meaningful replay/progression, and run a real loss/retry + first-30-second human QA. Such changes must be a separately authorized lineage, never an overwrite of the immutable artifact.
