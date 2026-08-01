# Kernel vs Legacy — Parity Report

- Scenarios total: 4
- Ran: 4  |  Skipped (requires_live in DRY_RUN): 0
- Legacy pass: 4  |  Kernel pass: 4
- Paths agree: 4/4 dual-path scenarios  |  Parity rate: 1.0

## Dual-path scenarios (goal text on both paths)

| Scenario | Legacy | Kernel | Agree | Kernel latency (ms) |
|---|---|---|---|---|
| interact.search_click_read | pass | pass | ✓ | 62097.9 |
| interact.scroll_and_extract | pass | pass | ✓ | 147629.5 |
| interact.form_fill | pass | pass | ✓ | 27105.7 |
| interact.tab_switch_compose | pass | pass | ✓ | 56524.3 |
