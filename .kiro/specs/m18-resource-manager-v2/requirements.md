# Requirements Document

M18 - Resource Manager v2 (Economics, Scheduling, Dynamic Reallocation)

## Introduction

M18 completes Amendment A2.6 additively over the M4 `ResourceRegistry` and
`ResourceManager`.  M4 correctly prevented double-allocation of exclusive
resources, but it could not select among alternatives, account for finite
budgets, bound parallel jobs, or preserve a goal when an allocated resource
failed.  M18 adds those capabilities while retaining every M4 public method
and its default behavior.

The manager remains the one authority through which cognition acquires
resources.  It is deterministic, provider-agnostic, kernel-event compatible,
and introduces no production-default change.

## Glossary

- **Resource descriptor**: a domain-neutral description of a finite resource,
  including health, capability, location, latency, reliability, load, and cost.
- **Request**: a holder's required resource kind, capability, permissions,
  priority, latency bound, and explicit fallback kinds.
- **Policy**: user-directed trade-offs, including local preference and whether
  paid resources are permitted.
- **Budget**: the maximum concurrent financial and energy commitment a holder
  can reserve.
- **Reservation**: an auditable, deterministic record of a granted economic
  allocation.
- **Degradation**: an explicitly requested fallback to a different resource
  kind; it is never silent.
- **Reallocation**: substitute, degrade, or queue an interrupted reservation
  after a resource becomes unavailable.

## Requirements

### Requirement 1: Additive resource economics

**User Story:** As the scheduler, I need resource descriptors rich enough to
compare alternatives without knowing a provider implementation.

#### Acceptance Criteria

1. A Resource SHALL retain its existing constructor fields and behavior, then
   add defaulted capability, permission, location, latency, reliability,
   availability, load, energy, parallelism, owner, version, and confidence
   descriptors.
2. Bounded numeric descriptors SHALL be normalised deterministically and
   resource discovery SHALL not require application-specific data.
3. ResourceRegistry SHALL expose a stable snapshot of all resources and an
   update boundary returning `None` for an unknown resource.
4. All existing direct `allocate`, `release`, `holder_of`, and `next_waiter`
   behavior SHALL remain backward compatible.

### Requirement 2: Policy-aware allocation and reservations

**User Story:** As a planner, I need the manager to choose a compatible,
healthy resource with the best policy-adjusted economic score.

#### Acceptance Criteria

1. A request MAY constrain resource kind, capability, permissions, locality,
   maximum latency, priority, and explicit fallback kinds.
2. A policy SHALL score compatible resources from reliability, availability,
   cost, energy, latency, load, and optional local preference.
3. A policy that forbids paid resources SHALL reject resources with positive
   cost before allocating them.
4. Candidate ranking SHALL be deterministic: equal scores resolve by stable
   resource id and SHALL never depend on wall-clock time or randomness.
5. A granted economic allocation SHALL create exactly one reservation for its
   holder/resource pair and SHALL expose its reservation id and score.
6. Repeating the same holder's allocation SHALL be idempotent and SHALL NOT
   double-count a reservation.
7. A non-exclusive resource with a `max_parallel_jobs` limit SHALL deny new
   holders once its limit is reached.

### Requirement 3: Budgets and priority queue

**User Story:** As the runtime, I need to avoid overcommitting a goal's finite
resource budget and let higher-priority blocked work run first.

#### Acceptance Criteria

1. A holder MAY have independent maximum cost and energy commitments.
2. The manager SHALL not grant an allocation whose additional commitment would
   exceed either applicable budget.
3. Releasing a reservation SHALL remove exactly its committed cost and energy.
4. Failed economic allocation SHALL queue a request exactly once when queueing
   is enabled; it SHALL not fabricate a resource id or allocation.
5. Queue processing SHALL consider higher priority requests before lower
   priority requests and preserve arrival order for equal priorities.
6. A legacy direct resource release SHALL not auto-grant a legacy FIFO waiter;
   explicit scheduler processing is required.

### Requirement 4: Dynamic reallocation

**User Story:** As a goal owner, I need work to survive an allocated resource
failure by using a compatible substitute, explicit fallback, or queue.

#### Acceptance Criteria

1. Marking a known resource unavailable SHALL make it unhealthy and unavailable
   to all subsequent selection.
2. Only reservations bound to that resource SHALL be interrupted; unrelated
   allocations and reservations SHALL remain unchanged.
3. The manager SHALL first attempt a compatible same-kind substitute, then
   explicitly configured fallback kinds, and finally queue the request.
4. A fallback-kind allocation SHALL be reported as `degraded`; a same-kind
   substitute SHALL be reported as `reallocated`.
5. The failed resource SHALL be excluded from every retry in that failover pass.
6. The initial reservation's policy and budget constraints SHALL be preserved
   during failover; policy MUST NOT be silently relaxed.
7. Each outcome SHALL be auditable and SHALL identify the interrupted
   reservation, original resource, holder, outcome, and optional replacement.
8. A `resource.unavailable` kernel event SHALL trigger the same failover path
   and no event handler SHALL raise into the kernel tick loop.

### Requirement 5: Safety, isolation, and regression

**User Story:** As the maintainer, I need A2.6 to be safe to adopt before
Deliberation v2 depends on it.

#### Acceptance Criteria

1. The feature SHALL be additive and SHALL not change a production default.
2. Resource modules SHALL import only standard library modules, resource
   modules, kernel resource contracts, and the event contract.
3. All contracts SHALL be generic: no app, site, model vendor, or hardcoded
   workflow branching is permitted.
4. Allocation, accounting, queueing, and reallocation SHALL be deterministic
   from their explicit descriptors and inputs.
5. New tests SHALL cover selection, policy, budgets, bounded sharing, queue
   priority, degradation, substitute reallocation, no-substitute queueing,
   policy preservation, determinism, and accounting conservation.
6. Existing M4 resource tests and the full FRIDAY/world regression suite SHALL
   pass under `FRIDAY_DRY_RUN=1`.
