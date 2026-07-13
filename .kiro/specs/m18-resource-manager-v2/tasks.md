# Implementation Plan

M18 - Resource Manager v2

## Overview

The implementation is additive and bottom-up: enrich the descriptor, add pure
economics contracts, extend the existing single manager, prove the behavioral
invariants, then run the full regression net.  No M16/M17 production file is
modified and no kernel default changes.

## Tasks

- [x] 1. Characterize M4 compatibility
  - Preserve `Resource`, `ResourceRegistry`, `Allocation`, and direct manager
    method signatures and baseline direct-allocation behavior.

- [x] 2. Enrich the generic resource model
  - Add defaulted cost, latency, reliability, availability, load, capability,
    permission, location, energy, and bounded-parallelism descriptors.
  - Add registry snapshot/update operations.
  - _Requirements: 1.1-1.4_

- [x] 3. Add pure economics contracts
  - Implement requests, policies, budgets, reservation records, and
    reallocation outcomes with no provider or clock dependency.
  - _Requirements: 2.1-2.6, 3.1-3.3, 4.7_

- [x] 4. Extend ResourceManager
  - Implement deterministic compatibility filtering, scoring, budget admission,
    idempotent reservation creation, and bounded non-exclusive sharing.
  - Implement priority queue processing while preserving legacy direct release.
  - _Requirements: 2.2-2.7, 3.1-3.6_

- [x] 5. Implement dynamic reallocation
  - Mark failures through the registry update boundary; substitute, explicitly
    degrade, or queue only affected reservations.
  - Retain stored policy/budget constraints and attach kernel event handling.
  - _Requirements: 4.1-4.8_

- [x] 6. Add deterministic tests
  - Add examples/property tests for selection, budgets, bounded sharing, queue
    priority, fallback, substitute reallocation, no-substitute queueing, policy
    preservation, replay determinism, and accounting conservation.
  - _Requirements: 5.4-5.5_

- [x] 7. Regression checkpoint
  - Targeted M18 plus M4 tests: `59 passed` under `FRIDAY_DRY_RUN=1`.
  - Run the full `tests/friday/ tests/world/` suite next and record the exact
    result in the after-milestone review.
  - _Requirements: 5.6_
