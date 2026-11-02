# Signal Sprint — consumer-grade QA contract (frozen source)

This is a **future-revision acceptance fixture**, not a claim that the pinned game was play-tested. Immutable source `c058cbf7fe38e02d929c67d047d717ff74bd522e` remains untouched. Registration: **GDK_GAME**.

## First 30 seconds — observable checks

| Elapsed | Consumer observation | Pass condition | Current evidence |
| --- | --- | --- | --- |
| 0–5 s | Initial screen | Clear primary Play action and game objective visible at 1024×768, 125%/150% DPI | Static UI indication only; live Windows QA missing |
| 5–10 s | Input discovery | Mouse and keyboard guidance visible without reading a manual | Static indication; live input QA missing |
| 10–20 s | First move | User understands goal, move budget and effect of one action | Not human-tested |
| 20–30 s | Failure/retry | Failure explains what went wrong, Retry is one obvious action, no hidden debug text | Static failure/retry UI indicated; timing not verified |

## Replay and localization gates

- **JP/EN**: every gameplay string, including failure, retry, victory, help, move budget, and score/feedback, must switch consistently and persist after restart. Any English gameplay message after JP selection fails.
- **Replay**: at least one meaningful variation beyond the current single fixed board (e.g. deterministic seeded boards with verified solvability) or a measurable progression/score challenge. A single repeatable board without progression fails consumer value.
- **Gameplay**: repeat the scenario with mouse/keyboard, observe response latency, visible state changes, no unresponsive controls, and no crash.
- **Accessibility**: all critical elements readable at 1024×768 and 125%/150% DPI; colors are not the only failure/success signal.
- **Store listing**: first screenshot should show objective, interaction and gameplay, not a developer/debug screen; no misleading features.

## Acceptance fixture fields

```json
{
  "schema_version": 1,
  "product": "Signal Sprint",
  "source_sha": "c058cbf7fe38e02d929c67d047d717ff74bd522e",
  "partner_center_selection": "GDK_GAME",
  "first_30s_live_windows_pass": false,
  "jp_en_all_gameplay_strings_pass": false,
  "replay_value_verified": false,
  "input_and_dpi_qa_pass": false,
  "store_screenshot_value_pass": false,
  "consumer_sale_ready": false,
  "status": "HOLD_UNTIL_OBSERVED"
}
```

All `false` values mean **not proven**, not necessarily broken. This fixture must not be turned green by CI alone. Future quality improvements require an explicitly authorized new product-source revision/lineage; they must not silently replace the fixed-source Artifact or mutate the existing CAS request. Store submission remains prohibited.
