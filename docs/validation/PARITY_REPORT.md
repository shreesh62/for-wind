# Kernel vs Legacy — Parity Report

- Scenarios total: 18
- Ran: 18  |  Skipped (requires_live in DRY_RUN): 0
- Legacy pass: 17  |  Kernel pass: 17
- Paths agree: 14/14 dual-path scenarios  |  Parity rate: 1.0
- Fault-actuation probes: 4 (pass 4 | fail 0 | skipped 0) — excluded from the parity rate because a probe verdict is path-independent, not a two-path measurement

## Dual-path scenarios (goal text on both paths)

| Scenario | Legacy | Kernel | Agree | Kernel latency (ms) |
|---|---|---|---|---|
| browser.search_read | pass | pass | ✓ | 45111.4 |
| desktop.open_app | pass | pass | ✓ | 57710.1 |
| multi.research_to_doc | pass | pass | ✓ | 144412.1 |
| research.position_paper | pass | pass | ✓ | 338086.1 |
| file.generate_report | fail | fail | ✓ | 900003.3 |
| long.multistep_project | pass | pass | ✓ | 480032.0 |
| unknown.explore_app | pass | pass | ✓ | 81420.3 |
| concurrent.two_goals | pass | pass | ✓ | 122461.6 |
| replay.event_log | pass | pass | ✓ | 6357.6 |
| checkpoint.restore_state | pass | pass | ✓ | 65048.9 |
| memory.episode_consistency | pass | pass | ✓ | 85211.7 |
| world.belief_consistency | pass | pass | ✓ | 49659.5 |
| goalgraph.transitions | pass | pass | ✓ | 197604.3 |
| determinism.repeat_run | pass | pass | ✓ | 2433550.5 |

### Failure detail

- **file.generate_report**
  - legacy: timeout>900s
  - kernel: timeout>900s

## Fault-actuation probes (real fault / real gate)

| Scenario | Probe | Verdict | Latency (ms) |
|---|---|---|---|
| interrupt.pause_resume | interrupt.pause_resume | pass | 18.1 |
| crash.restart_restore | crash.restart_restore | pass | 540.0 |
| browser_fail.reconnect | browser_fail.reconnect | pass | 817.4 |
| human.confirm_send | human.confirm_send | pass | 21.8 |

### interrupt.pause_resume — pass

- goal is genuinely in flight: the operator entered run() on the submitting thread and is blocked there
- kernel goal states while in flight: ["3fcce1ad-d9df-452c-97cc-ac252ebdb139='created'"]
- in-flight goal id from the durable log: 3fcce1ad-d9df-452c-97cc-ac252ebdb139
- discovered suspension entry point: CognitiveKernel.interrupt_goal
- post-interrupt durable event types: ['kernel.runtime_registered', 'goal.created', 'goal.suspended']
- post-interrupt kernel goal states: ['suspended']
- suspension observed durably: events=['goal.suspended'], states=['suspended']
- discovered resume entry point: CognitiveKernel.resume_goal
- post-resume durable event types: ['kernel.runtime_registered', 'goal.created', 'goal.suspended', 'goal.resumed', 'goal.completed']
- suspension was honored: goal.completed was recorded only AFTER goal.resumed (order: ['kernel.runtime_registered', 'goal.created', 'goal.suspended', 'goal.resumed', 'goal.completed'])
- no duplicated work: operator.run was invoked exactly once across interrupt and resume

### crash.restart_restore — pass

- launched real child process pid 32672 over persisted log crash-ev.jsonl
- pre-kill log event types: ['kernel.runtime_registered', 'goal.created']
- pre-kill goal id from durable log: 45d6ef03-17ad-4f57-8669-96de112726c3
- child pid 32672 was still alive mid-goal (blocked inside goal execution) immediately before the kill
- child pid 32672 killed hard with no graceful shutdown; process gone (exit code 1)
- post-restore replayed event types: ['kernel.runtime_registered', 'goal.created']
- post-restore goal id matched pre-kill id: 45d6ef03-17ad-4f57-8669-96de112726c3
- restored goal state is legal: 'created' (of ['created'])
- restored goal text preserved: 'Begin a goal, simulate a process crash, restart, and resume from checkpoint.'

### browser_fail.reconnect — pass

- pre-kill connection_mode: 'fresh'
- pre-kill session worked: navigate(about:blank) ok, current_url='about:blank'
- attributed browser processes as descendants of this controller's own driver pid 25892: 18056:chrome.exe, 23700:chrome.exe, 32732:chrome.exe, 7412:chrome.exe, 15620:chrome.exe, 8352:chrome.exe, 22648:chrome.exe, 19696:chrome.exe, 31664:chrome.exe, 19800:chrome.exe, 8256:chrome.exe
- killed pids [18056, 23700, 32732, 7412, 15620, 8352, 22648, 19696, 31664, 19800, 8256] at OS level (psutil kill, not BrowserController.stop()); all 11 confirmed terminated
- post-kill attributable browser processes: <none>
- post-kill navigate(about:blank) returned ok=False, error='Page.goto: Target page, context or browser has been closed'
- failure was reported observably, not fabricated as success: falsy result with error='Page.goto: Target page, context or browser has been closed' (controller.last_error='TargetClosedError: Page.goto: Target page, context or browser has been closed')

### human.confirm_send — pass

- attached the real production PermissionManager (default SafetyPolicy, irreversible_confidence_floor=0.85)
- no-approval irreversible delivery was withheld: ['permission.denied'] with decisions ['confirm'] (no permission.granted emitted)
- real policy on a CONFIDENT irreversible send (MODIFICATION, trusted, confidence=0.95): notify — base decision for MODIFICATION
- gate discriminates rather than blanket-denying: safe reversible trusted action produced ['permission.granted']
- execution path with no approval: withheld=True (result='WITHHELD by permission gate (confirm): run_command -> an irreversible privileged operation — irreversible action below c')
- execution path with approval granted: proceeded=True (result='Command execution: an irreversible privileged operation (gated for safety)')
- the real execution chokepoint (GoalExecutor._execute_step) consults the gate: an irreversible step is withheld without approval and proceeds with it
