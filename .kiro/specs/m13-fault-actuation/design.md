# Design — M13 Fault Actuation

## Overview

Add a **fault probe** layer to `scripts/kernel_validation` so the four scenarios named after faults
and gates actually actuate them. The existing `ValidationRunner` contract and the 14 goal-text
scenarios are untouched; probes are additive and dispatched generically.

```
scenarios.py      ValidationScenario gains  probe_id: str = ""
faults.py   (new) FaultProbe protocol + ProbeVerdict + registry
probes/     (new) crash_restore.py | browser_kill.py | interrupt_resume.py | confirmation_gate.py
child.py    (new) separate-process kernel goal submitter (crash probe target)
runner.py         run_scenario(): if scenario.probe_id -> dispatch probe; else current behavior
evidence.py       ValidationEvidence gains probe_id + assertions (additive, defaulted)
report.py         renders probe id + assertions for probe-backed rows
```

## Investigate before implementing

The probes must use the **real** kernel/controller/permission APIs. Do not guess names. Before
writing each probe, read the actual source and confirm:

- `friday/kernel/kernel.py` — event store persistence, restore/replay entry point, goal state
  enumeration, interrupt/suspend surface, `submit_goal` semantics.
- `friday/events/store.py` — durable log format, append/read API.
- `friday/actions/browser_controller.py` and `friday/actions/browser_session.py` — how the browser
  process is launched, whether a PID/process handle is reachable, `connection_mode`, `last_error`.
- The permission / irreversibility path (A2.3 and the M25 reversibility gating already integrated in
  `friday/deliberation/preference_resolver.py`) plus whatever gate the executor consults before an
  irreversible action.

If a required capability genuinely does not exist, the probe returns **fail naming the gap**. Do not
invent a shim that makes the probe pass.

## Components

### `ProbeVerdict`

Frozen dataclass, JSON-safe:

```python
@dataclass(frozen=True)
class ProbeVerdict:
    probe_id: str
    result: str                      # "pass" | "fail" | "skipped"
    assertions: Tuple[str, ...] = () # ordered human-readable observations
    error: str = ""
    def to_dict(self) -> Dict[str, Any]: ...
```

`assertions` entries are observation strings such as
`"pre-kill log contained goal.created"` / `"post-restore goal id matched: g-3"`.
They are the audit trail; a pass with an empty `assertions` tuple is a defect.

### `FaultProbe` protocol

```python
class FaultProbe(Protocol):
    probe_id: str
    def actuate(self, context: ProbeContext) -> ProbeVerdict: ...
```

`ProbeContext` carries what a probe may need without coupling probes to the runner:
`scenario`, `operator_factory`, `browser_controller`, `workdir` (a temp dir the runner owns).

### Registry

`register_probe(probe)` / `get_probe(probe_id) -> Optional[FaultProbe]`. Built-ins registered at
import. The runner does `probe = get_probe(scenario.probe_id)`; unknown id → fail (never silent pass).

### Runner integration

```python
def run_scenario(self, scenario):
    if scenario.probe_id:
        return self._run_probe(scenario)     # returns (legacy_ev, kernel_ev)
    ...existing path unchanged...
```

Probe-backed scenarios are inherently kernel-path assertions (crash restore, interrupt, gate). To
keep the report shape stable, `_run_probe` records the verdict on the **kernel** evidence and emits a
legacy evidence with the same result and an assertion noting the probe is path-independent. This
keeps parity arithmetic honest: it does not claim a legacy-path measurement that was not taken —
the assertion string says so explicitly.

DRY_RUN behavior is preserved: a `requires_live` probe scenario under `FRIDAY_DRY_RUN` is **skipped**.

### Probe: crash restore (`crash.restart_restore`)

1. Create `workdir/ev.jsonl`.
2. `subprocess.Popen([sys.executable, "-m", "scripts.kernel_validation.child", "--store", path,
   "--goal", text])` — the child builds a real `CognitiveKernel` over that store, submits the goal,
   then idles.
3. Poll the store file until at least one goal-lifecycle event is present, bounded by a timeout.
4. `proc.kill()` — hard, no graceful shutdown. Assert the process is gone.
5. Build a fresh kernel over the same store, run its restore/replay, assert the goal id and a legal
   state are present.
6. Fail if step 3 timed out (no events ⇒ nothing was proven).
7. `finally`: kill the child if alive, remove the temp dir.

### Probe: browser kill (`browser_fail.reconnect`)

1. Skip if no controller. Record the pre-kill `connection_mode`.
2. Resolve the controller's own launched process (PID/handle/child tree) — **only** that one.
3. Kill it at the OS level.
4. Attempt a further operation.
5. Pass if the session is re-established **or** the failure is observably reported. Fail if the
   operation reports success while the browser is dead (that would be fabricated evidence).

### Probe: interrupt resume (`interrupt.pause_resume`)

1. Kernel over a temp store; submit a goal via a slow operator so the goal is genuinely in flight.
2. Submit a real interrupt through the kernel's public mechanism.
3. Assert from the event log: a suspension/state-change event occurred, then progress continued.
4. Assert no duplicated work: no work-unit identifier appears twice in the log.

### Probe: confirmation gate (`human.confirm_send`)

1. Attempt the irreversible action with **no** approval → assert it did not execute (no delivery /
   completion evidence for it).
2. Attempt with an approval record → assert it proceeds.
3. Fail if (1) executed, or if (2) is blocked (a blanket denial is not a gate).

### Child process module

`scripts/kernel_validation/child.py` — minimal, argv-driven, no side effects on import. Bootstraps
`sys.path` the same way `runner.py` does. Exists so the crash probe can kill a real process.

## Testing strategy

`tests/friday/test_m13_fault_actuation.py`, offline and deterministic:

- Protocol/registry: registration, lookup, unknown id → fail not pass.
- `ProbeVerdict` JSON round-trip; pass-with-empty-assertions is rejected by construction check.
- Runner dispatch: scenario with `probe_id` routes to the probe; scenario without it uses the
  existing path (guards Requirement 1.2).
- Skipped never counts as pass in report totals.
- Crash probe against a **stub operator** (real subprocess, real kill, real event log — no LLM):
  asserts restore happened, and asserts fail when the log is empty.
- Backward compatibility: existing `ValidationEvidence.to_dict()` keys still present.

Live probes (browser kill, and the real-LLM paths) are exercised in the manual real-machine run, not
in the offline suite. Offline tests cover their pure logic via injected fakes only where the fake
does not defeat the point of the probe.

## Constraints honored

- No production default changes; no flip commit.
- No app/site-specific logic.
- No silent `except Exception: pass`.
- Existing 7 `ValidationRunner` tests untouched and passing.
- Skipped ≠ pass, anywhere.
