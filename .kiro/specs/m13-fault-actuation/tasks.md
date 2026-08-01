# Implementation Plan — M13 Fault Actuation

- [x] 1. Add the fault probe protocol, verdict value, and registry
  - Create `scripts/kernel_validation/faults.py` with `ProbeVerdict` (frozen, JSON-safe `to_dict`),
    a `ProbeContext` value carrying `scenario`, `operator_factory`, `browser_controller`, `workdir`,
    a `FaultProbe` Protocol exposing `probe_id` and `actuate(context) -> ProbeVerdict`, and
    `register_probe` / `get_probe` registry functions.
  - A `pass` verdict with an empty `assertions` tuple must be rejected at construction (a pass with
    no observations is not evidence).
  - No app-specific logic; no silent `except Exception: pass`.
  - _Requirements: 1.1, 1.3, 1.4, 6.1, 8.4_

- [x] 2. Extend scenario and evidence models additively
  - Add `probe_id: str = ""` to `ValidationScenario` and set it on `crash.restart_restore`,
    `browser_fail.reconnect`, `interrupt.pause_resume`, `human.confirm_send` only.
  - Add `probe_id: str = ""` and `assertions: Tuple[str, ...] = ()` to `ValidationEvidence`; keep all
    existing fields and every existing `to_dict()` key present and unchanged in meaning.
  - _Requirements: 6.1, 6.3, 1.2_

- [x] 3. Wire generic probe dispatch into the runner
  - In `ValidationRunner.run_scenario`, when `scenario.probe_id` is set, dispatch through
    `get_probe(...)` and build the evidence pair from the verdict; otherwise keep the existing
    goal-text path byte-for-byte in behavior.
  - Unknown probe id must produce a `fail` (never a pass, never an exception escaping).
  - Preserve `FRIDAY_DRY_RUN` skip semantics for `requires_live` probe scenarios, and preserve the
    `FRIDAY_USE_KERNEL_EXECUTION` restore in `finally`.
  - No `if scenario.id == ...` branching anywhere.
  - The 7 existing `ValidationRunner` tests must pass unmodified.
  - _Requirements: 1.1, 1.2, 1.3, 8.2_

- [x] 4. Add the separate-process kernel child module
  - Create `scripts/kernel_validation/child.py`: argv-driven (`--store PATH --goal TEXT`), bootstraps
    `sys.path` like `runner.py`, builds a real `CognitiveKernel` over the persisted `EventStore`,
    submits the goal, then idles so it can be killed. No side effects on import.
  - Read `friday/kernel/kernel.py` and `friday/events/store.py` first and use their real APIs.
  - _Requirements: 2.1_

- [x] 5. Implement the crash-restore probe (C3)
  - Create `scripts/kernel_validation/probes/crash_restore.py`. Launch the child against a persisted
    event log, poll until a goal-lifecycle event appears (bounded timeout), then `kill()` the process
    hard and confirm it is gone.
  - Build a fresh kernel over the same log, run the real restore/replay path, and assert the goal id
    and a legal state are restored. Record pre-kill and post-restore event types in `assertions`.
  - If no pre-kill events appeared, return `fail` with that reason — never pass.
  - Clean up child process and temp files in `finally`.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 6. Implement the browser-kill probe (C3)
  - Create `scripts/kernel_validation/probes/browser_kill.py`. Return `skipped` with a reason when no
    controller is available (never pass).
  - Resolve only the process the controller itself launched and kill it at OS level (not via graceful
    `stop()`), then attempt further use.
  - Pass when the session is re-established or the failure is observably reported; `fail` when an
    operation reports success while the browser is dead.
  - Read `friday/actions/browser_controller.py` and `browser_session.py` first to find the real
    process handle; if none is reachable, say so in the verdict rather than faking a kill.
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 7. Implement the interrupt-resume probe (C3)
  - Create `scripts/kernel_validation/probes/interrupt_resume.py`. Submit a goal with a slow injected
    operator so it is genuinely in flight, then submit a real interrupt through the kernel's own
    public mechanism.
  - Assert from the event log that a suspension/state change occurred and progress then continued,
    and that no work-unit identifier appears twice.
  - If the kernel exposes no such mechanism, return `fail` naming the missing capability.
  - _Requirements: 4.1, 4.2, 4.3_

- [x] 8. Implement the confirmation-gate probe (C7)
  - Create `scripts/kernel_validation/probes/confirmation_gate.py` exercising the real production
    permission/irreversibility path (no test double).
  - Attempt the irreversible action with no approval → assert no delivery/completion evidence exists.
  - Attempt with an approval record → assert it proceeds (proving a gate, not a blanket denial).
  - Fail on either violation.
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 9. Render probe evidence in the parity report
  - Update `scripts/kernel_validation/report.py` so probe-backed rows are visibly distinguished and
    their `assertions` are printed.
  - Ensure `skipped` is never counted toward any pass total in the summary arithmetic.
  - Keep ASCII-safe or UTF-8-forced output consistent with the existing runner behavior.
  - _Requirements: 6.2, 6.4_

- [x] 10. Write the offline test suite for fault actuation
  - Create `tests/friday/test_m13_fault_actuation.py`: registry registration/lookup, unknown id →
    fail, `ProbeVerdict` JSON round-trip, pass-with-empty-assertions rejected, runner dispatch for
    probe vs non-probe scenarios, `skipped` excluded from pass totals, `ValidationEvidence.to_dict()`
    backward compatibility.
  - Include a real-subprocess, real-kill, real-event-log crash-probe test using a stub operator (no
    LLM), plus the empty-log fail case.
  - No skips, xfails, or tolerances added to force green.
  - Run the full offline suite and confirm zero failures (floor: 1707 passed) plus the 7 existing
    `ValidationRunner` tests unmodified.
  - _Requirements: 8.1, 8.2, 8.3_

- [x] 11. Re-run the harness and re-derive the readiness verdict
  - Run the extended harness on the real machine and regenerate
    `docs/validation/PARITY_REPORT.md` from that run only.
  - Update `docs/validation/KERNEL_READINESS_VERDICT.md` from the actual outcome: cite the specific
    assertions for C3 and C7 if they pass; if any probe fails or is skipped, keep the verdict
    PARTIALLY QUALIFIED and name the unproven criterion.
  - Do NOT apply the `BridgeConfig.use_kernel_execution` flip commit under any outcome.
  - _Requirements: 7.1, 7.2, 7.3, 7.4_
