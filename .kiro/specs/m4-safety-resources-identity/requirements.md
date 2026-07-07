# Requirements Document

## Introduction

This milestone closes the four binding FAS subsystems that earlier milestones (M1–M9) left unbuilt
as dedicated packages: **Safety & Permission** (Ch 35), the **Resource Model** (Ch 45–48),
**Cognitive Identity** (Ch 51), and the **Cognitive State Manager** (Ch 67). M1–M9 delivered and
verified (995 passing tests) the kernel, world model, goals, deliberation, environments,
verification, and the M8/M9 reflection-through-background loops. What is still missing is the safety
boundary that gates risky actions (a hard constitutional requirement), the resource authority that
allocates finite resources rather than assuming them, the identity that carries continuity across
sessions, and the explicit model of the operator's own mind.

Every subsystem communicates only through kernel-published events (Ch 52); subsystems never call one
another directly. Safety proposes no autonomous crossing of hard boundaries; resources are allocated,
never assumed; identity reuses existing checkpoint/restore and Goal serialization rather than
rewriting them. All new modules carry `"""Ch NN — ..."""` docstrings, contain no hardcoded
application or site names or URLs (Axiom 15), and run deterministically under `FRIDAY_DRY_RUN=1` so
the existing test suite stays green.

These requirements are derived from the approved design document and are traceable to its seven
components, its M4 Gate, and its ten correctness properties.

## Glossary

- **Kernel**: The M1 `CognitiveKernel`, owning the event bus, clock, event store, and
  checkpoint/restore.
- **Kernel_Event**: A dot-namespaced `Event` delivered through the Kernel event bus carrying
  `logical_time` and `wall_time`.
- **Permission_Manager**: `friday/safety/permission.py` `PermissionManager` — classifies actions and
  decides autonomy vs confirmation.
- **Permission_Level**: One of nine ascending levels (OBSERVATION, INTERACTION, MODIFICATION,
  DELETION, FINANCIAL, IDENTITY, ADMINISTRATIVE, KERNEL, HARDWARE).
- **Trust_Zone**: One of TRUSTED, VERIFIED, RESTRICTED, UNTRUSTED, HOSTILE.
- **Decision**: One of ALLOW, NOTIFY, CONFIRM, DENY.
- **Safety_Policy**: `friday/safety/policy.py` `SafetyPolicy` — immutable hard boundaries plus
  confirmation-rule table, with an `irreversible_confidence_floor`.
- **Secret_Vault**: `friday/safety/vault.py` `SecretVault` — keyring-backed (encrypted-file fallback)
  secret store addressed by key name; never echoes values.
- **Resource**: `friday/resources/types.py` `Resource` — a finite resource with kind, exclusivity,
  cost, and health.
- **Resource_Registry**: `friday/resources/registry.py` `ResourceRegistry` — discovers/registers
  resources.
- **Resource_Manager**: `friday/resources/scheduler.py` `ResourceManager` — allocates/releases
  resources; prevents double-allocation of exclusive resources.
- **Exclusive_Resource**: A resource that may have at most one holder at a time (browser session,
  input device, human attention).
- **Cognitive_Identity**: `friday/identity/identity.py` `CognitiveIdentity` — persistent continuity
  (identity id, preferences, goal states, last checkpoint) across sessions.
- **Cognitive_State_Manager**: `friday/cognition/state.py` `CognitiveStateManager` — the operator's
  own mind-state (focus, attention, interruptibility, thinking depth, reasoning budget, urgency,
  mode).
- **DRY_RUN**: The `FRIDAY_DRY_RUN=1` mode in which no real filesystem, LLM, OS, or credential store
  is touched.

## Requirements

### Requirement 1: Permission Management

**User Story:** As a FRIDAY platform maintainer, I want every action classified by permission level
and trust zone and gated accordingly, so that risky or irreversible actions never proceed
autonomously.

#### Acceptance Criteria

1. WHEN the Permission_Manager evaluates a request whose Permission_Level is in the Safety_Policy
   forbidden set, THE Permission_Manager SHALL return a Decision that is neither ALLOW nor NOTIFY.
2. WHEN the Permission_Manager evaluates a request whose Permission_Level is in the Safety_Policy
   confirm set, THE Permission_Manager SHALL return the CONFIRM Decision or the DENY Decision and
   SHALL NOT return ALLOW or NOTIFY.
3. IF an action is irreversible AND its confidence is below the Safety_Policy
   irreversible_confidence_floor, THEN THE Permission_Manager SHALL NOT return ALLOW.
4. WHEN the Permission_Manager evaluates a request whose Permission_Level is OBSERVATION or
   INTERACTION AND the Trust_Zone is TRUSTED or VERIFIED, THE Permission_Manager SHALL return ALLOW.
5. WHEN the Permission_Manager attaches to the Kernel, THE Permission_Manager SHALL subscribe to
   `action.requested` and SHALL publish `permission.granted` on an allowing verdict and
   `permission.denied` on a denying verdict.
6. IF an incoming Kernel_Event lacks a field the Permission_Manager requires, THEN THE
   Permission_Manager SHALL skip processing for that event and SHALL NOT raise into the Kernel tick
   loop.

### Requirement 2: Secret Vault

**User Story:** As a FRIDAY platform maintainer, I want secrets addressed by key name through a
vault rather than plaintext, so that credentials never appear in logs or source.

#### Acceptance Criteria

1. WHEN a secret is stored via `set(key, value)` and later retrieved via `get(key)`, THE Secret_Vault
   SHALL return the identical value, SHALL report `has(key)` true, and after `delete(key)` SHALL
   return `None` from `get(key)`.
2. THE Secret_Vault string and repr forms SHALL NOT contain any stored secret value.
3. WHEN `keys()` is called, THE Secret_Vault SHALL return secret key names only and SHALL NOT return
   secret values.
4. WHILE running under DRY_RUN, THE Secret_Vault SHALL operate on an in-memory store and SHALL NOT
   touch a real operating-system credential store.
5. IF the keyring backend is unavailable, THEN THE Secret_Vault SHALL fall back to an encrypted-file
   store without raising on import.

### Requirement 3: Resource Model

**User Story:** As a FRIDAY cognitive architect, I want finite resources registered and allocated
through a single authority, so that exclusive resources are never double-allocated and cognition
never assumes availability.

#### Acceptance Criteria

1. WHEN a Resource is registered with the Resource_Registry, THE Resource_Registry SHALL return its
   id and SHALL make it retrievable by id and by kind.
2. WHEN the Resource_Manager allocates an Exclusive_Resource that currently has no holder, THE
   Resource_Manager SHALL grant the allocation and record the holder.
3. WHEN the Resource_Manager allocates an Exclusive_Resource that is already held by a different
   holder, THE Resource_Manager SHALL deny the allocation and SHALL leave the existing holder
   unchanged.
4. WHEN the Resource_Manager releases a resource by its current holder, THE Resource_Manager SHALL
   free the resource, and WHEN a non-holder attempts release, THE Resource_Manager SHALL NOT free it.
5. IF a resource is unhealthy or unknown, THEN THE Resource_Manager SHALL deny allocation.
6. WHEN the Resource_Manager attaches to the Kernel, THE Resource_Manager SHALL subscribe to
   `resource.requested` and `resource.released` and SHALL publish `resource.allocated`,
   `resource.released`, or `resource.denied`, and SHALL NOT raise into the Kernel tick loop.

### Requirement 4: Cognitive Identity

**User Story:** As a FRIDAY cognitive architect, I want one continuous identity across sessions and
restarts, so that the operator resumes its goals and preferences rather than starting over.

#### Acceptance Criteria

1. THE Cognitive_Identity SHALL maintain a stable identity id, a preferences mapping, and a mapping
   of goal ids to goal states.
2. WHEN the Cognitive_Identity attaches to the Kernel, THE Cognitive_Identity SHALL subscribe to
   `goal.state_changed` and `kernel.checkpoint` Kernel_Events.
3. WHEN a `goal.state_changed` Kernel_Event is received, THE Cognitive_Identity SHALL record the
   goal id and its new state.
4. WHEN a `kernel.checkpoint` Kernel_Event is received, THE Cognitive_Identity SHALL record the
   checkpoint path.
5. WHEN the Cognitive_Identity checkpoints, THE Cognitive_Identity SHALL produce a JSON-serializable
   state containing the identity id, preferences, and goal states.
6. WHEN the Cognitive_Identity restores from a checkpoint, THE Cognitive_Identity SHALL reproduce the
   identical identity id, preferences, and goal states, and IF the state is partial or truncated THEN
   THE Cognitive_Identity SHALL default missing fields and SHALL NOT invent goal ids.

### Requirement 5: Cognitive State Manager

**User Story:** As a FRIDAY cognitive architect, I want an explicit model of the operator's own mind
state, so that other subsystems can reason about focus, interruptibility, and reasoning budget rather
than inferring them implicitly.

#### Acceptance Criteria

1. THE Cognitive_State_Manager SHALL expose a snapshot containing mode, focus, attention,
   interruptibility, thinking depth, reasoning budget, urgency, and active goal.
2. WHEN the Cognitive_State_Manager receives an `action.executed` Kernel_Event, THE
   Cognitive_State_Manager SHALL enter EXECUTION mode.
3. WHEN the Cognitive_State_Manager receives a `goal.state_changed` Kernel_Event whose state is
   `active`, THE Cognitive_State_Manager SHALL set the focus and active goal to that goal id.
4. WHEN reasoning budget is consumed, THE Cognitive_State_Manager SHALL keep the remaining budget
   within the closed interval `[0, 1]` and SHALL NOT allow it to become negative.
5. IF an incoming Kernel_Event lacks a field the Cognitive_State_Manager requires, THEN THE
   Cognitive_State_Manager SHALL skip processing for that event and SHALL NOT raise into the Kernel
   tick loop.

### Requirement 6: Kernel-Event Isolation and the M4 Gate

**User Story:** As a FRIDAY platform maintainer, I want the M4-gap subsystems to communicate only
through kernel events and to be provable end-to-end, so that the architecture stays decoupled and
regression-safe.

#### Acceptance Criteria

1. THE Permission_Manager, Resource_Manager, Cognitive_Identity, and Cognitive_State_Manager SHALL
   exchange information only through Kernel_Events and SHALL NOT call one another directly.
2. THE Safety modules SHALL import only `friday.events`, standard-library modules, and an optional
   guarded `keyring` import; THE Resource modules SHALL import only `friday.events`,
   `friday.kernel.contracts`, and standard-library modules; THE Identity and Cognitive_State modules
   SHALL import only `friday.events` and standard-library modules.
3. THE M4-gap subsystem modules SHALL contain no hardcoded application names, site names, or URLs and
   SHALL each carry a `"""Ch NN — ..."""` module docstring.
4. WHILE running under DRY_RUN, WHEN the same ordered event log is replayed through freshly
   constructed M4-gap subsystems, THE subsystems SHALL produce identical emitted Kernel_Event types
   and payloads modulo event id and wall time and identical internal state.
5. WHEN the M4 Gate scenario runs, THE Kernel SHALL show a risky action gated to CONFIRM or DENY, an
   exclusive resource contended by two holders granted to exactly one, and a Cognitive_Identity that
   survives a checkpoint and restore across a fresh Kernel.

### Requirement 7: Non-Regression and Module Hygiene

**User Story:** As a FRIDAY platform maintainer, I want the gap-closing subsystems to preserve all
existing tests and follow module conventions, so that they integrate without breaking M1–M9.

#### Acceptance Criteria

1. WHILE running the full FRIDAY test suite, THE M4-gap subsystems SHALL keep the existing test count
   of at least 995 tests passing.
2. WHILE any M4-gap test module runs, THE test suite SHALL execute under DRY_RUN so that no real
   filesystem, LLM, OS, or credential surface is touched.
3. THE M4-gap subsystem modules SHALL each carry a module docstring in the `"""Ch NN — ..."""` form.

## Property-to-Requirement Mapping

- **Property 1** (Forbidden never auto-allowed) → **Requirement 1.1, 1.4**
- **Property 2** (Confirm levels require confirmation) → **Requirement 1.2**
- **Property 3** (Irreversible low-confidence never auto-allowed) → **Requirement 1.3**
- **Property 4** (Vault never leaks values) → **Requirement 2.2, 2.3**
- **Property 5** (Vault round-trips) → **Requirement 2.1**
- **Property 6** (Exclusive never double-allocated) → **Requirement 3.2, 3.3**
- **Property 7** (Release frees exactly the holder) → **Requirement 3.4**
- **Property 8** (Identity survives restart) → **Requirement 4.5, 4.6**
- **Property 9** (Reasoning budget in [0,1]) → **Requirement 5.4**
- **Property 10** (Determinism) → **Requirement 6.4, 6.5**
