# Requirements Document

## Introduction

Milestone 6 turns FRIDAY's applications-as-environments axiom (FAS Axiom 7) into working code. It introduces a uniform `EnvironmentContract` that every digital environment implements, wraps the existing `BrowserController` in a `BrowserEnvironment` adapter without rewriting it, merges the two historical verification systems into a `UnifiedVerificationEngine`, and persists all evidence in a queryable, signed `EvidenceRepository`. The binding constraint is isolation: the Kernel and Deliberation layers must never import Playwright and must never know which environment backend they are talking to. FRIDAY is a General Computer Operator (GCO) — applications are environments, capabilities are universal, and no component hardcodes knowledge of any specific site or application.

## Glossary

- **EnvironmentContract**: The single abstract base class (ABC) defining the uniform interface every digital environment must implement (FAS Ch 23.22).
- **BrowserEnvironment**: The Playwright adapter that wraps the existing `BrowserController` and exposes it through `EnvironmentContract` (FAS Ch 29).
- **StubEnvironment**: A deterministic, Playwright-free fake environment used for gate tests and CI to prove Kernel/Deliberation independence from any specific backend.
- **UnifiedVerificationEngine**: The single verification façade that merges artifact-based (`EvidenceVerifier`) and diff-based (`ActionVerifier`) verification (FAS Ch 32).
- **EvidenceVerifier**: The crown-jewel verifier that maps `RequirementKind` to `ExecutionEvidence` artifacts; its semantics are preserved unchanged (FAS Ch 33).
- **ActionVerifier**: The diff-based verifier that checks whether a single action visibly changed the world as predicted.
- **EvidenceRepository**: The queryable, indexed, signed store of evidence artifacts and verdicts (FAS Ch 33).
- **Action**: An abstract interaction request carrying a capability verb and a semantic target — never app-specific (FAS Ch 24).
- **ActionResult**: The universal return contract for all environment interactions; every `interact()` call returns one.
- **Observation**: The uniform sensor reading every environment produces (FAS Ch 12).
- **WorldObject**: An object the operator believes exists within an environment (window, button, file, etc.).
- **DecisionRecord**: The immutable, auditable record of one deliberation decision.
- **RuntimeContract**: The kernel-level interface every runtime implements for lifecycle management (FAS Ch 52).
- **Kernel**: The CognitiveKernel — pure infrastructure that owns the clock, event bus, and registered runtimes; contains no cognition, no Playwright.
- **Deliberation**: The layer that ranks candidate actions by utility; it consumes abstract capabilities and is environment-agnostic.
- **Evidence_Law**: The invariant that a requirement may be marked satisfied ONLY when a matching evidence artifact exists; generated text can NEVER satisfy a GATHER or DELIVER requirement.
- **Capability**: An abstract verb (e.g. "click", "type", "navigate") that an environment affords; never names a site or application.
- **ObjectQuery**: A generic, site-agnostic query over the objects an environment currently exposes.
- **GCO**: General Computer Operator — the FAS architectural philosophy that FRIDAY operates any application as an environment with universal capabilities.

## Requirements

### Requirement 1: Environment Contract Uniformity

**User Story:** As the Kernel runtime manager, I want every environment to implement a single uniform interface, so that the system can perceive, interact with, and verify any digital environment without backend-specific code.

#### Acceptance Criteria

1. THE EnvironmentContract SHALL expose the methods `name`, `observe`, `interact`, `verify`, `query_objects`, `query_capabilities`, `pause`, `resume`, `shutdown`, and `health` as its complete public interface (FAS Ch 23.22)
2. WHEN `interact(action)` is called on any environment where `action.capability` is in that environment's `query_capabilities()` result, THEN THE environment SHALL return an ActionResult and SHALL NOT raise an exception
3. WHEN `observe()` is called on any environment, THEN THE environment SHALL return a list where every element is an Observation with a non-empty `environment` field and a non-empty `object_type` field
4. WHEN `query_objects(query)` is called with `query.object_type` set to a value `t`, THEN THE environment SHALL return only WorldObject instances whose `object_type` equals `t`
5. WHEN `query_capabilities()` is called on any environment, THEN THE environment SHALL return a list of abstract capability strings that contains no URLs, no application names, and no site-specific identifiers
6. WHEN `health()` is called on any environment, THEN THE environment SHALL return a dictionary containing at minimum a `status` field with value `"ok"` or `"degraded"`

### Requirement 2: Site-Agnosticism

**User Story:** As the system architect, I want all environment code to be free of hardcoded URLs and application names, so that FRIDAY operates as a true General Computer Operator that handles any application uniformly.

#### Acceptance Criteria

1. THE source code under `friday/environments/` SHALL contain no hardcoded URL scheme literals (http://, https://, file://) and no known-application name constants (Axiom 15)
2. WHEN an Action is constructed, THE Action SHALL carry URLs only via `params` supplied at runtime by the goal/plan and SHALL NOT embed any URL in its source definition
3. THE BrowserEnvironment `name` property SHALL return a generic backend identifier (e.g. `"browser.chrome.dedicated"`) and SHALL NOT reference any website or application name
4. WHEN `query_capabilities()` is called on BrowserEnvironment, THEN THE BrowserEnvironment SHALL return only abstract verbs (observe, read, navigate, click, type, scroll, press, upload, download) with no site-specific strings

### Requirement 3: Unified Verification Engine

**User Story:** As a verification consumer, I want a single engine that merges artifact-based and diff-based verification, so that all verification needs are served by one coherent interface without duplicated or divergent logic.

#### Acceptance Criteria

1. THE UnifiedVerificationEngine SHALL expose `verify_action`, `verify_requirement`, and `verify_goal` as its public interface, merging the capabilities of EvidenceVerifier and ActionVerifier
2. WHEN `verify_requirement(requirement, evidence)` is called, THEN THE UnifiedVerificationEngine SHALL delegate to `EvidenceVerifier.verify_one()` and SHALL return a result whose satisfied status is identical to the EvidenceVerifier's verdict
3. WHEN `verify_goal(goal, evidence)` is called, THEN THE UnifiedVerificationEngine SHALL evaluate every requirement in the goal via `EvidenceVerifier.verify_one()` and SHALL report the goal as satisfied if and only if all requirement verdicts are satisfied
4. WHEN `verify_goal(goal, evidence)` is called on a goal with zero requirements, THEN THE UnifiedVerificationEngine SHALL report the goal as NOT satisfied (a goal with no requirements is never trivially complete)
5. WHEN `verify_action(action_type, predicted, observed, evidence)` is called, THEN THE UnifiedVerificationEngine SHALL use ActionVerifier for the diff verdict and use artifact presence for corroboration, and SHALL NOT downgrade an artifact-backed truth

### Requirement 4: Evidence Law Preservation

**User Story:** As the system integrity guardian, I want the Evidence Law to remain inviolate in the unified engine, so that false completion remains architecturally impossible and no heuristic can paper over missing work.

#### Acceptance Criteria

1. WHEN the UnifiedVerificationEngine evaluates any requirement of kind GATHER or DELIVER against evidence containing only GENERATED_CONTENT artifacts, THEN THE UnifiedVerificationEngine SHALL report that requirement as UNMET
2. THE UnifiedVerificationEngine SHALL NOT add any heuristic, override, or relaxation that could satisfy a GATHER or DELIVER requirement from generated content alone
3. WHEN a verdict is produced by the UnifiedVerificationEngine, THEN THE verdict's satisfied status SHALL be identical to the value returned by `EvidenceVerifier.verify_one()` for the same requirement and evidence inputs (the engine may only tighten, never loosen)
4. THE existing 802 tests SHALL pass without modification after the UnifiedVerificationEngine is introduced, confirming that EvidenceVerifier semantics are preserved byte-for-byte

### Requirement 5: Evidence Integrity and Repository

**User Story:** As an auditor, I want all evidence to be stored in a queryable, signed, append-only repository, so that verdicts are tamper-evident and evidence can be reconstructed after the fact.

#### Acceptance Criteria

1. THE EvidenceRepository SHALL sign each EvidenceRecord with HMAC-SHA256 over the canonical JSON payload, and SHALL verify signatures on read
2. WHEN any field of a stored EvidenceRecord is mutated, THEN THE EvidenceRepository `verify_integrity()` method SHALL detect the tampering and report the record as invalid
3. THE EvidenceRepository SHALL be append-only with no update or delete API, preserving full audit history
4. WHEN `query(goal_id, kind)` is called on the EvidenceRepository, THEN THE EvidenceRepository SHALL return all matching records indexed by goal and by EvidenceKind
5. WHEN `for_goal(goal_id)` is called, THEN THE EvidenceRepository SHALL reconstruct an ExecutionEvidence bundle from all valid stored artifacts for that goal
6. WHEN the UnifiedVerificationEngine produces a verdict, THEN THE UnifiedVerificationEngine SHALL persist both the verdict and associated evidence artifacts into the EvidenceRepository

### Requirement 6: Backend Independence and Kernel Isolation

**User Story:** As the kernel architect, I want to prove that neither the Kernel nor Deliberation depends on any specific environment backend, so that the system can operate with any environment implementation including a Playwright-free stub.

#### Acceptance Criteria

1. WHEN the active environment is swapped from BrowserEnvironment to StubEnvironment, THEN THE Deliberation layer SHALL produce a DecisionRecord with the same structure (same fields, same considered-tuple shape) for the same goal and candidate set
2. THE source code under `friday/kernel/` and `friday/deliberation/` SHALL NOT import `playwright`, `friday.actions.browser_controller`, or `friday.environments.browser` (Ch 52 isolation)
3. WHEN `checkpoint()` is called on any EnvironmentRuntime, THEN THE runtime SHALL return only JSON-serializable primitives containing no live Playwright or browser handle objects
4. THE StubEnvironment SHALL implement the full EnvironmentContract with deterministic, scripted responses and zero external dependencies
5. WHEN StubEnvironment's `interact()` is called with any Action, THEN THE StubEnvironment SHALL return a successful ActionResult without performing I/O or requiring Playwright

### Requirement 7: Browser Adapter Wrapping Strategy

**User Story:** As a developer maintaining the browser integration, I want the BrowserEnvironment to wrap the existing BrowserController without rewriting it, so that the proven 710-line controller remains intact and regression-free.

#### Acceptance Criteria

1. THE BrowserEnvironment SHALL delegate all interactions to the existing `BrowserController` methods without modifying `browser_controller.py`
2. WHEN `BrowserEnvironment.observe()` is called, THEN THE BrowserEnvironment SHALL call `browser_controller.observe_interactive()` and SHALL map the returned element dictionaries into Observation objects with `environment="browser"`
3. WHEN `BrowserEnvironment.interact(Action("navigate"))` is called, THEN THE BrowserEnvironment SHALL delegate to `browser_controller.navigate(params["url"])`
4. WHEN the backend is unavailable (`browser_controller.available` is False), THEN THE BrowserEnvironment SHALL return `ActionResult.blocked(reason=...)` from `interact()` and SHALL return an empty list from `observe()`
5. THE BrowserEnvironment SHALL implement both EnvironmentContract and RuntimeContract so the Kernel can register, tick, checkpoint, and shutdown it as a standard runtime
6. WHEN converting controller results to ActionResult, THEN THE BrowserEnvironment SHALL populate ActionEvidence with url_changed and state_changed signals derived from the controller response, ensuring no Playwright types escape the adapter boundary

### Requirement 8: Non-Forcing Migration and FAS Traceability

**User Story:** As a developer working on M6, I want the migration to be additive and traceable, so that legacy code keeps working and every new module is auditable back to the FAS.

#### Acceptance Criteria

1. THE legacy `perception/world_state.py` snapshot system SHALL continue to function without modification after M6 is deployed
2. WHEN a new module is created under `friday/environments/` or `friday/verification/`, THEN THE module SHALL carry a docstring in the format `"""Ch NN — description"""` referencing the relevant FAS chapter
3. THE existing `EnvironmentContract` stub in `friday/kernel/contracts/environment.py` SHALL remain a valid base class, with the full contract in `friday/environments/contract.py` subclassing it (extend, not fork)
4. WHEN the UnifiedVerificationEngine is introduced, THEN THE existing 802 tests SHALL pass before the old orphaned verifier wiring is retired (regression oracle)
