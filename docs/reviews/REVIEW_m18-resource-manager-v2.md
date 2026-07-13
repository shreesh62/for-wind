# After-Milestone Review - M18 Resource Manager v2

> Governance record for FAS v2.1 A2.6.  M18 is additive over M4 and is the
> dependency-clean architectural prerequisite for Deliberation v2.

## 0. Milestone under review

- Milestone: `M18 - Resource Manager v2`
- Amendment: `A2.6`
- Scope: resource economics, policy-aware selection, concurrent budgets,
  reservations, bounded sharing, priority queueing, and failure reallocation.
- Non-goals: production kernel-default flip, model-provider changes, and
  Deliberation v2 integration.

## 1. What changed

M4's manager could register resources and prevent double-allocation of an
exclusive resource.  M18 keeps that public surface intact, then adds:

- generic descriptor economics: capabilities, permissions, locality, latency,
  reliability, availability, current load, energy cost, and parallel capacity;
- immutable request, policy, budget, reservation, and reallocation contracts;
- deterministic ranking plus a stable resource-id tie-breaker;
- budget admission and auditable, idempotent reservation accounting;
- priority scheduling for blocked v2 requests without changing M4's direct
  release/FIFO behavior;
- dynamic failure handling that substitutes, explicitly degrades, or queues
  only the work affected by an unavailable resource;
- stored policy preservation during failover: for example, a no-paid-resources
  request is queued rather than silently moved to a paid resource.

No M16/M17 production file, production default, or kernel flip setting changed.

## 2. Regression safety

- [x] Targeted M18 plus M4 resource regression net: **60 passed**.
- [x] All **1,350 collected** `tests/friday/` and `tests/world/` tests passed
  under `FRIDAY_DRY_RUN=1`.  The desktop executor caps a single command at 64
  seconds, so the suite was run in disjoint batches whose pass totals sum to
  1,349: M6-M9 (193), M10-M14 (164), M16/M17 plus world (94), non-milestone
  A-O (228), non-milestone P-Z (321), nested action tests (256), M4/M18 (60),
  and memory/model-router tests (34).
- [x] `git diff --check` passed.
- [x] M4's resource isolation net passed.  M18 imports only stdlib,
  `friday.resources`, `friday.events`, and the established kernel contract.
- [x] No existing test was altered; M18 adds one dedicated test module and its
  specification documents.

The full suite retained pre-existing warnings from Chrome coroutine cleanup and
Windows packaging dependencies.  They are outside M18's changed files and no
test failed.

## 3. Correctness evidence

The new tests cover the architectural invariants rather than provider-specific
workflows:

| Invariant | Evidence |
| --- | --- |
| Deterministic compatible-resource selection | Example + 100-case property test |
| User cost policy is enforced | Free/local choice; failover policy retention |
| Budget commitment cannot overrun | Budget rejection and release-conservation property |
| Sharing remains finite when bounded | Parallel capacity example |
| Scheduler fairness is explicit | Priority then FIFO queue example |
| Degradation is never hidden | Fallback result carries `degraded=True` |
| Failure only disrupts dependent work | Substitute and no-substitute examples |
| Accounting is preserved after failure | Reservation/budget assertions |

## 4. Architecture review

M18 realizes the normative Chapters 45-48 shape as one authority rather than
separate scheduler, allocator, load balancer, and reservation services.  It
uses general resource descriptors and request constraints, not app/model/site
conditions.  The manager emits events but does not depend on a live kernel;
direct M4 allocations retain their behavior, so adoption by Deliberation v2
can be incremental.

The design is intentionally conservative in two respects:

1. Budgets represent concurrent commitments, not irreversible billing.  Actual
   consumption telemetry belongs to a future resource monitor/provider adapter.
2. Queue processing is explicit.  It avoids changing M4's release behavior
   while making scheduling policy available to a future kernel tick/runtime.

These are extension points, not gaps in the A2.6 invariant: no subsystem gains
resources directly, and a failed resource can now substitute, degrade, or
queue under the same user policy.

## 5. Competence ratchet and gate

M18 is an architectural foundation, not a new benchmark-domain capability; it
does not claim a fabricated browser/desktop/research score.  The last recorded
real-machine scorecard remains the M17 ratchet PASS at overall **0.8**.

The required live benchmark rerun has **not** been performed in this execution
because it invokes configured browser, desktop, network, and model-provider
resources.  It must be run by the maintainer before claiming an M18 ratchet
close-out.  This leaves the production kernel default off and does not affect
the fully verified automated implementation.

Recommended next architectural implementation after that real-machine check:
**A2.3 Deliberation v2**, consuming M18's request/policy/budget interface for
the resource and attention cost terms plus recovery contracts.

## 6. Decision

- [x] Automated implementation gate: **PASS** - 1,350/1,350 tests passed.
- [ ] Real-machine competence-ratchet gate: **PENDING MAINTAINER RUN**.
- [x] Production default preservation: **PASS** - kernel execution remains
  opt-in and `BridgeConfig.use_kernel_execution` remains `False` by default.

Reviewer / date: FRIDAY orchestrator, M18 implementation close-out pending
real-machine governance evidence.

---

## 7. Independent code review (second engineer)

Reviewed `economics.py`, `scheduler.py`, and `types.py` against the A2.6 amendment
and the codebase invariants. Verdict: **sound and faithful to A2.6.**

Confirmed:
- **Single authority (A2.6 core invariant).** `ResourceManager` is the sole allocator;
  every economic path routes through `allocate`/`allocate_best`. No subsystem acquires
  resources directly.
- **Cost-aware / economics selection.** `_score` weights reliability, availability,
  cost, energy, latency, and current load via `ResourcePolicy`; `prefer_local` bonus and
  `allow_paid` gate honor user policy. Deterministic tie-break on `resource.id`.
- **Dynamic reallocation.** `mark_unavailable` substitutes → degrades (explicit
  `degraded=True`) → queues, touching only reservations that depended on the failed
  resource, excluding it from retry, and preserving the original policy (a no-paid
  request queues rather than silently moving to a paid resource).
- **Budgets + reservations.** Admission via `_fits_budget`; idempotent per-holder
  accounting; `_forget_reservations` conserves totals on release and on federated
  resource disappearance.
- **Determinism / replay-safety.** Sequence-based reservation/request IDs, no clock,
  no UUID, clock-free economics — matches the M12/M13 replay discipline.
- **Additive over M4.** Legacy `allocate`/`release`/`holder_of`/`next_waiter` semantics
  unchanged; the new `Resource` economics fields are defaulted, so `Resource(id, kind,
  exclusive)` construction is unaffected; `__post_init__` clamps bounded fields.
- **Data contract verified.** Every attribute the scheduler reads exists on the
  `Resource` descriptor (`reliability`, `availability`, `cost`, `energy_cost`,
  `latency_ms`, `current_load`, `location`, `capabilities`, `permissions`, `kind`,
  `exclusive`, `max_parallel_jobs`, `healthy`) — no latent AttributeError masked by stubs.
- **Kernel-mediated, degrade-never-crash.** `_emit` is a no-op when detached and swallows
  bus errors; event emission never compromises an allocation result.
- **Axiom 15.** Selection uses only generic descriptors/policy — no app/model/site
  conditionals.

Documented extension points (not defects): budgets model *concurrent commitments* not
billed consumption (a future monitor/provider adapter tracks real usage); `process_queue`
is explicit rather than tick-driven; `_on_resource_released` deliberately does not
auto-grant legacy FIFO waiters. All preserve the A2.6 invariant.

Independent verification: the M18 resource tests pass as part of a full `tests/` run
(1506 passed, 0 failed, 1 perf benchmark deselected) on the reviewer's machine. No code
changes were required by this review. The real-machine competence-ratchet rerun remains
the maintainer's gate (§5/§6); M18 correctly claims no benchmark-domain score change.

Independent reviewer / date: FRIDAY orchestrator (second pass).
