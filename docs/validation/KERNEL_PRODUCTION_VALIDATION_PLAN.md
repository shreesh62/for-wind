# Kernel Production Validation Plan

**Milestone:** M13 — Production Validation & Architecture v2.1 (Part 1)
**Status:** Ready to execute on a real machine. **No production default is changed by this plan.**
**Question this plan answers:** *Is the Cognitive Kernel production-ready?*

---

## 1. Scope & Non-Goals

**In scope:** exercising the kernel execution path (`FRIDAY_USE_KERNEL_EXECUTION=1`) against realistic
end-to-end goals, collecting evidence, comparing to the legacy path on identical workloads, and
deciding readiness against explicit criteria.

**Non-goals / hard rules:**
- The production default (`BridgeConfig.use_kernel_execution=False`) is **NOT** changed by this plan.
- No new subsystem is implemented.
- No real-world result is fabricated. Scenarios needing a live browser/desktop/network/GPU are marked
  `requires_live` and are **skipped** in the sandbox (`FRIDAY_DRY_RUN=1`); they must be run by the
  maintainer on a real machine.

## 2. How to run the harness (real machine)

```bash
# 1. Ensure a real environment (NOT dry-run) with credentials + Chrome available.
#    (Leave FRIDAY_DRY_RUN unset.)
set NVIDIA_API_KEY=...        # or via the SecretVault
set GROQ_API_KEY=...

# 2. Drive the runner with a REAL Operator factory (edit the __main__ block or a wrapper):
python -c "from scripts.kernel_validation.runner import ValidationRunner; \
from friday.operator import Operator; \
from friday.models.router import ModelRouter; \
r = ModelRouter();  # register providers as in api/server.py \
runner = ValidationRunner(lambda g: Operator(model_router=r)); \
pairs = runner.run_all(); \
from scripts.kernel_validation.report import render_markdown; \
open('docs/validation/PARITY_REPORT.md','w',encoding='utf-8').write(render_markdown(pairs))"
```

The runner constructs a local kernel + `GoalExecutionRuntime` per scenario and never mutates a global
default (it restores `FRIDAY_USE_KERNEL_EXECUTION` after each run).

## 3. Scenario Suite (18 categories)

Defined in `scripts/kernel_validation/scenarios.py`. Categories:

| # | Category | requires_live | What it proves |
|---|---|---|---|
| 1 | browser_automation | yes | real search + page read, evidence recorded |
| 2 | desktop_automation | yes | app launch + focus verification |
| 3 | multi_environment | yes | browser → file, evidence spans environments |
| 4 | research | yes | gather + source URLs + citations |
| 5 | file_generation | no | FILE_ARTIFACT with real byte size |
| 6 | long_running | yes | goal persists across many steps |
| 7 | interruption_resume | yes | suspend + resume, no lost/dup work |
| 8 | crash_recovery | yes | restart → restore from checkpoint |
| 9 | browser_failure_recovery | yes | recover after browser death |
| 10 | unknown_application | yes | exploration, no app-specific logic |
| 11 | concurrent_goals | yes | two goals progress, no deadlock |
| 12 | human_confirmation | yes | irreversible action gated on approval |
| 13 | event_replay | no | replay yields same lifecycle events |
| 14 | checkpoint_restore | no | restored state matches pre-checkpoint |
| 15 | memory_consistency | no | exactly one episode per completed goal |
| 16 | world_model_consistency | yes | no unresolved contradictory beliefs |
| 17 | goal_graph_consistency | yes | valid node transitions |
| 18 | deterministic_replay | no | identical runs → identical ordered events |

## 4. Evidence Collected

Per scenario, per path (`ValidationEvidence`): result (pass/fail/skipped), output summary, ordered
`goal.*` event types, latency (ms), error. In a real run, additionally capture from the kernel bus and
runtimes: full event logs, goal transitions, decision/verification artifacts, resource allocation +
scheduler behavior, recovery behavior, and performance metrics (latency, throughput, memory).

## 5. Explicit Promotion Criteria (ALL must pass)

The kernel becomes the default **only if every criterion below is satisfied on a real machine.**

**C1 — Correctness parity.** For every non-live and live scenario, the kernel path's success/failure
result matches the legacy path (parity_rate = 1.0 over ran scenarios), OR every divergence is
explained and accepted as an improvement (kernel correct, legacy wrong).

**C2 — Evidence integrity.** Every "completed" goal on the kernel path carries the same class of
Evidence-Law artifacts the legacy path produced (GATHERED_INFO/SOURCE_URL/FILE_ARTIFACT/
DELIVERY_CONFIRMATION as applicable). No false completions.

**C3 — Recovery.** Crash recovery, browser-failure recovery, and interruption/resume scenarios each
complete or degrade honestly on the kernel path, with checkpoint→restore reproducing goal state.

**C4 — Determinism.** The deterministic_replay and event_replay scenarios produce identical ordered
`goal.*` event types across repeated runs.

**C5 — Consistency.** memory/world-model/goal-graph consistency scenarios leave no unresolved
contradictions, no duplicate/absent episodes, and only legal goal-graph transitions.

**C6 — Performance.** Kernel-path latency is within an accepted budget of the legacy path
(recommended: ≤ 1.25× median legacy latency per scenario), with no unbounded memory growth over a
long-running scenario.

**C7 — Safety.** The human_confirmation scenario never performs the irreversible action without
approval on either path.

**C8 — Stability.** A full run of the suite produces zero unhandled exceptions escaping the runner;
all failures are captured as evidence.

## 6. Decision & Output

After a real-machine run:
- Populate `docs/validation/PARITY_REPORT.md` (generated) and review against C1–C8.
- Record the verdict in `docs/validation/KERNEL_READINESS_VERDICT.md`.
- If **any** criterion fails → verdict = NOT production-ready; the verdict names the failing criteria.
- If **all** pass → verdict = production-ready; proceed with the rollback strategy + single isolated
  default-flip commit described in the verdict document.
