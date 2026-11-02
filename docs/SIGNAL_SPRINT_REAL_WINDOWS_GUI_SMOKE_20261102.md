# Signal Sprint — real Windows EXE GUI smoke (CHECK-ONLY)

- **Product:** Signal Sprint; **Partner Center selection:** GDK game (`GDK_GAME`).
- **Immutable game source:** `c058cbf7fe38e02d929c67d047d717ff74bd522e` (never modified).
- **New Factory lineage:** run `41361263698`, Artifact `13105352227`, control/build SHA `a1af3448cd2edeae5bd54cbaca486a53fd991944`.
- **New request:** `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e-reissue-sprint-41361263698-41361263698`.
- **Actual EXE:** 11,344,389 bytes, SHA-256 `beb683b61b4fa4b2ec90fe1d413363c8a535bd4cb72b41b54b03a9685f516ee0`.
- **Historical old Artifact #12706862577:** remains `ARTIFACT_EXACT_BYTES_HOLD`, never substituted.

## Execution

The Factory PR #15 workflow has an explicit `[signal-sprint-gui-smoke]` trigger. Its Windows job downloads the **existing** run/artifact (no new build), checks GitHub artifact ID/digest, immutable source, request, control HEAD, inner ZIP digest and actual EXE bytes, then executes this repo's pinned `qa/signal_sprint_windows_gui_smoke.ps1`. The QA script is **not** game source and does not change gameplay.

The script starts the real executable and attempts to observe a real Windows top-level window and UI Automation text. It checks objective/instructions, sends a real RIGHT key, requires the move counter to decrease, sends alternating LEFT/RIGHT until the loss state, requires a visible failure reason, sends R, and requires the counter to reset. It records time to first observed move and optionally captures a screenshot of the application window, not the whole desktop. It terminates the launched process and emits JSON even on HOLD. `gdk_signal_sprint_gui_receipt.py` independently rejects incomplete or forged authority claims. Negative fixture tests run on Windows and Ubuntu in the normal Provisioner CI.

If GitHub-hosted Windows is non-interactive, Code Integrity blocks the EXE, Tk controls are inaccessible to UI Automation, input does not reach the window, or screenshot is unavailable, record the exact reason. **No simulated GUI success** is permitted. Screenshot absence alone does not prove GUI failure, and screenshot presence does not prove gameplay. A green automated check is not a human usability verdict.

## Acceptance and non-claims

- A genuine `WINDOWS_GUI_AUTOMATED_CHECK_ONLY` receipt requires observed window, initial objective, real input/state change within 30 seconds, loss reason, and retry reset. If any is missing, `WINDOWS_GUI_CHECK_ONLY_HOLD`.
- The workflow job may be red on an uninteractive runner. Do not hide that failure or label it consumer QA PASS.
- `human_qa_pass=false`, `consumer_sale_ready=false`, `cas_return_pass=false`, `gdk_sdk_executed=false`, `real_msixvc_built=false`, `store_submitted=false` in all receipts.
- Real human 30-second comprehension, Japanese localization, visual quality at 1024×768 and 125%/150% DPI, scoring and replay value remain separate SALE_READY gates.
- Official Identity is already received. New-request authenticated CAS, Package Version, four approved GDK images, MSIXVC2 SDK package, and Windows E2E remain HOLD. Never invent missing approval values or modify the 36-minute central ledger.

No main/release change, force push, merge, CAS, SDK execution or Store operation is authorized by this test.
