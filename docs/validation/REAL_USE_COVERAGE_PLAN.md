# Real-Use Coverage Plan (M18-audit Medium)

**Purpose.** The automated suite runs entirely under `FRIDAY_DRY_RUN=1` (see
`tests/conftest.py`), so the product's *live* action paths — real browser control,
desktop control, input (keyboard/mouse), and message/email send — are never exercised
against anything real. This is deliberate CI safety (no test may open a window, drive
input, or send a message), but it leaves a real-use coverage gap. This document converts
that gap into an actionable, evidence-based checklist the maintainer runs on a real
machine.

> The `desktop_app` Playwright suite (six tests against `playwright.dev`) is a Playwright
> *availability* smoke test, not a test of this product's browser path. Product browser
> coverage is the L2/L3 checks below, run on a real machine.

---

## What IS covered automatically (CI-safe, no real machine)

- **Network/gather transport (real sockets):** `tests/friday/test_real_socket_gather.py`
  stands up a localhost HTTP server and lets `web_search.gather` perform genuine `httpx`
  GETs — real HTTP, real 200/403 handling, real HTML→text extraction, real evidence +
  beliefs. This is the one live-transport path that is safe to exercise hermetically.
- **All action LOGIC under dry-run:** planning, requirements, evidence law, executor
  dispatch, safety gates, and the actuators' dry-run branches (e.g.
  `SystemActions.launch_app` now returns a simulated success and spawns nothing under
  `FRIDAY_DRY_RUN=1`).
- **Kernel behavior** (parity, fail-safe, determinism/replay, isolation) per the M12/M13
  harness.

## What REQUIRES a real machine (this runbook)

Real browser (Chrome/CDP), desktop control, input devices, model providers, and network.
Run each check with `FRIDAY_DRY_RUN` **unset**, on a machine with a display, a real Chrome,
and provider keys in `.env`. Record the evidence column; a check passes only when its
required evidence artifact is actually produced (Evidence Law is the judge).

### Precheck
- [ ] `Remove-Item Env:\FRIDAY_DRY_RUN` (ensure dry-run is OFF for this session only).
- [ ] `.env` has valid `NVIDIA_API_KEY` (and any others used); `python scripts/kernel_validation/run_capability_benchmarks.py` connects to providers.
- [ ] A real Chrome is installed; `FRIDAY_REQUIRE_REAL_CHROME=1`.

### L1 — Browser operation
| # | Action | Expected evidence | Pass? |
|---|---|---|---|
| B1 | Navigate to a public page and read it | `NAVIGATION` (real landed URL) + `GATHERED_INFO` (real page text) | ☐ |
| B2 | Search a topic, open two independent sources | `GATHERED_INFO` + ≥1 `SOURCE_URL` | ☐ |
| B3 | Hit a login/captcha wall | run halts honestly (blocked), `SCREENSHOT` evidence, no tab-spam | ☐ |

### L2 — Desktop operation
| # | Action | Expected evidence | Pass? |
|---|---|---|---|
| D1 | Launch a local app and confirm it is foreground | confirmed environment reach (`NAVIGATION`: launched/focused) | ☐ |
| D2 | Produce a saved file via a local app | `FILE_ARTIFACT` (byte size > 0 on disk) | ☐ |

### L3 — Input (keyboard/mouse)
| # | Action | Expected evidence | Pass? |
|---|---|---|---|
| I1 | Type text into a focused field | observed post-state matches typed text (verification) | ☐ |
| I2 | Click a labeled control | observed state change | ☐ |

### L4 — Delivery / send (safety-gated, irreversible)
| # | Action | Expected evidence | Pass? |
|---|---|---|---|
| S1 | Send a message/email through the open surface | human-confirmation gate fires FIRST; `DELIVERY_CONFIRMATION` only on observed success | ☐ |
| S2 | Attempt send, then DECLINE at the gate | no send occurs; no `DELIVERY_CONFIRMATION` recorded | ☐ |

### L5 — Recovery
| # | Action | Expected evidence | Pass? |
|---|---|---|---|
| R1 | Kill the browser mid-goal | recovery/reallocation observed; goal fails or recovers honestly (no fabricated evidence) | ☐ |
| R2 | Interrupt then resume a long goal | goal state resumes from the durable event log | ☐ |

### Capability benchmark (measured competence, real machine)
- [ ] `python scripts/kernel_validation/run_capability_benchmarks.py --record`
- [ ] Ratchet PASS; scores recorded to `baseline.local.json` (committed seed stays all-unmeasured).

---

## Honesty rules

- Never fabricate a live result. If a check cannot be run (no display, no key, no device),
  mark it **N/A — not run**, not pass.
- A check passes only when its **evidence artifact** is produced — generated text never
  satisfies a gather/deliver/navigate check.
- These live results are the maintainer's to record; the sandbox cannot produce them.

## Status
- CI real-transport coverage: **added** (`test_real_socket_gather.py`).
- L1–L5 live coverage: **pending maintainer run** on a real machine (this runbook).
- Playwright product-path tests: currently absent (the six existing tests target
  `playwright.dev`); L1 above is the product browser check until a product-targeted
  Playwright suite is added.
