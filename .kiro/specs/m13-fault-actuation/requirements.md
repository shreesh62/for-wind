# Requirements — M13 Fault Actuation (close C3 and C7)

## Introduction

`docs/validation/KERNEL_READINESS_VERDICT.md` records the honest verdict **PARTIALLY QUALIFIED**.
Criteria C1/C2/C4/C6/C8 pass. **C3 (recovery) and C7 (safety gate) are UNPROVEN** because the
parity harness proves only that a goal's *text* ran to `goal.completed`. It never kills a process,
never terminates the browser mid-task, never injects an interrupt, and never observes that an
irreversible action was withheld.

This feature extends `scripts/kernel_validation` so those three recovery scenarios and the one
safety scenario are validated by **actuating the real fault** and **asserting the recovery/gate
behavior**, not by goal completion.

Non-goal: flipping `BridgeConfig.use_kernel_execution`. That commit stays unapplied until the
re-run shows C1–C8 all genuinely pass.

## Glossary

- **Fault probe** — a reusable object that (a) sets up a scenario, (b) actuates a real fault or
  attempts a gated action, and (c) returns a verdict derived from observed system state.
- **Actuation** — a real state change on the machine: process termination, browser process kill,
  interrupt submission, irreversible-action attempt. Never a simulation or a mocked flag.
- **Verdict** — pass/fail plus the concrete observations that justify it.

## Requirements

### Requirement 1 — Fault probes are a generic, reusable mechanism

**User Story:** As the architect, I want fault actuation expressed as a reusable protocol so new
fault categories can be added without touching runner control flow (Axiom 15: no per-scenario
special-casing).

#### Acceptance Criteria

1. WHEN a fault probe is defined THEN it SHALL conform to a single protocol exposing `probe_id`,
   `actuate(context)`, and a verdict return value; the runner SHALL dispatch through that protocol
   only.
2. WHEN a scenario declares no probe THEN the runner SHALL behave exactly as today (goal text +
   `goal.completed`), so the existing 14 scenarios and their results are unchanged.
3. WHEN a probe is registered THEN it SHALL be discoverable by id from a registry, and the runner
   SHALL NOT contain `if scenario.id == ...` branching.
4. The probe modules SHALL NOT contain application-specific or site-specific logic.

### Requirement 2 — Crash recovery is actuated (C3)

**User Story:** As the architect, I want `crash.restart_restore` to prove that a killed process's
goal state is genuinely recoverable from the durable event log.

#### Acceptance Criteria

1. WHEN the crash probe runs THEN it SHALL start a **real separate OS process** that submits a goal
   against a **persisted** event-store file, wait until the log shows the goal was accepted, and
   then **terminate that process** without graceful shutdown.
2. WHEN the process has been terminated THEN the probe SHALL construct a fresh kernel over the same
   persisted event log and SHALL assert the goal is restored with the same goal id and a legal state.
3. IF the pre-kill log contains no goal-lifecycle events THEN the probe SHALL return **fail** with
   that reason, and SHALL NOT report a pass.
4. The probe SHALL record the observed pre-kill and post-restore event types in its verdict.
5. The probe SHALL NOT leave the child process running or the temporary event log behind.

### Requirement 3 — Browser failure recovery is actuated (C3)

**User Story:** As the architect, I want `browser_fail.reconnect` to prove the system reacts to a
real browser death.

#### Acceptance Criteria

1. WHEN the browser probe runs with a live controller THEN it SHALL kill the browser at the OS
   process level (not by calling a graceful `stop()`), and THEN attempt further use.
2. WHEN post-kill use is attempted THEN the probe SHALL pass only if either (a) the controller
   re-establishes a working session, or (b) the failure is reported **observably** (an error
   surfaced/recorded, no fabricated success).
3. IF a browser controller is unavailable THEN the probe SHALL return **skipped** with the reason,
   and SHALL NOT return pass.
4. The probe SHALL NOT kill unrelated browser processes belonging to the user; only the process
   tree it can attribute to the controller it started.

### Requirement 4 — Interrupt/resume is actuated (C3)

**User Story:** As the architect, I want `interrupt.pause_resume` to prove a real interrupt suspends
and resumes a goal without losing or duplicating work.

#### Acceptance Criteria

1. WHEN the interrupt probe runs THEN it SHALL submit a real interrupt through the kernel's own
   public interrupt/suspension mechanism while a goal is active.
2. WHEN the goal is resumed THEN the probe SHALL assert from the event log that the goal reached a
   suspended state and then continued, and that no unit of work appears twice.
3. IF the kernel exposes no interrupt mechanism capable of this THEN the probe SHALL return **fail**
   naming the missing capability rather than passing.

### Requirement 5 — The safety gate is asserted observably (C7)

**User Story:** As the architect, I want `human.confirm_send` to prove an irreversible action is
withheld absent approval.

#### Acceptance Criteria

1. WHEN the confirmation probe attempts an irreversible action with **no** approval record THEN it
   SHALL assert the action did not execute: no completion/delivery evidence exists for it.
2. WHEN the same action is attempted **with** an approval record THEN the probe SHALL assert it is
   permitted, proving the gate is a gate and not a blanket denial.
3. IF the attempt without approval produces delivery evidence THEN the probe SHALL return **fail**.
4. The probe SHALL exercise the real permission/irreversibility path used in production, not a
   test double.

### Requirement 6 — Evidence and report carry the assertions

**User Story:** As a reviewer, I want the parity report to show what was actuated and asserted, so
"pass" is auditable.

#### Acceptance Criteria

1. WHEN a probe-backed scenario runs THEN its `ValidationEvidence` SHALL carry the probe id and the
   ordered list of assertion observations.
2. WHEN the report is rendered THEN probe-backed scenarios SHALL be visibly distinguished from
   goal-text scenarios, and their assertions SHALL appear.
3. Existing `ValidationEvidence` fields and `to_dict()` keys SHALL remain present and
   backward-compatible.
4. A skipped probe SHALL never be counted as a pass in any summary total.

### Requirement 7 — Verdict is re-derived from the new run

**User Story:** As the architect, I want the readiness verdict updated from real evidence only.

#### Acceptance Criteria

1. WHEN the extended harness has been run THEN `docs/validation/PARITY_REPORT.md` SHALL be
   regenerated from that run.
2. WHEN C3 and C7 probes pass THEN `KERNEL_READINESS_VERDICT.md` SHALL be updated to reflect it,
   citing the specific assertions.
3. IF any probe fails or is skipped THEN the verdict SHALL remain PARTIALLY QUALIFIED and SHALL name
   the still-unproven criterion.
4. The flip commit SHALL NOT be applied by this feature under any outcome.

### Requirement 8 — No regressions, no weakened verification

#### Acceptance Criteria

1. The full offline test suite SHALL pass with zero failures (regression floor: 1707 passed).
2. The 7 existing `ValidationRunner` tests SHALL continue to pass unmodified.
3. No test SHALL be skipped, xfailed, or given a tolerance solely to obtain a green result.
4. New code SHALL NOT use silent `except Exception: pass`.
