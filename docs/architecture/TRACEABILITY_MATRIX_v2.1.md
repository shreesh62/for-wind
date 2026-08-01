# Architecture v2.1 — Traceability Matrix

Maps each v2.1 concept → FAS chapter(s) → current code state → owning milestone. Code state:
**Built** (implemented + tested on the kernel substrate), **Partial** (pieces exist, not fully
normative/wired), **Absent** (not yet built). No implementation occurs in M13; "owning milestone" is
the recommended future home.

| # | v2.1 Concept (amendment) | FAS Ch | Current code | State | Owning milestone |
|---|---|---|---|---|---|
| A2.1 | World Model belief freshness/TTL/refresh | Ch 9.22 | M15 `world/belief.py` (`freshness`/`half_life_seconds`/`ttl_seconds`/`refresh_policy`/`refresh_cost`), M9 `temporal/aging.py` | **Built** | M15 (World Model v2) |
| A2.1 | Belief provenance / evidence graph | Ch 9.24 | M15 `world/provenance.py` (`BeliefProvenance`: supporting/contradicting observations, derivation chain, verification status) | **Built** | M15 |
| A2.1 | Staleness handling | Ch 9.22 | M15 `world/world_model.py::stale_beliefs` (+ `Belief.is_stale`) | **Built** | M15 |
| A2.2 | Environment fingerprints | Ch 23/9.23 | M15 `perception/fingerprint.py` (`compute_fingerprint`, `EnvironmentFingerprint`) | **Built** | M15 (Environment Intelligence) |
| A2.2 | UI fingerprints | Ch 23 | M15 `perception/fingerprint.py::compute_ui_fingerprint` | **Built** | M15 |
| A2.2 | Capability invalidation on fingerprint change | Ch 23/25 | M15 `perception/fingerprint_monitor.py` (`FingerprintMonitor`, wired `kernel.fingerprint_monitor`) | **Built** | M15 |
| A2.2 | Version-aware adaptation | Ch 16/28 | M15 `perception/fingerprint.py::version_confidence_factor` | **Built** | M15 |
| A2.3 | Expanded deliberation utility | Ch 10 | M16 `deliberation/expanded_utility.py` (`ExpandedUtilityFunction`, nine terms) | **Built** | M16 (Deliberation v2) |
| A2.3 | Action safety term | Ch 10/35 | M16 `deliberation/expanded_utility.py` (safety penalty), M4 `safety/permission.py` | **Built** | M16 |
| A2.3 | Recovery contracts (undo/rollback/compensation) | Ch 34 | M16 `deliberation/recovery_contract.py` (`RecoveryContract`) + `deliberation/candidate.py` | **Built** | M16 |
| A2.4 | Capability lifecycle | Ch 16.21/27 | M11 `evolution/lifecycle.py` | **Built** | M11 (done) — make normative |
| A2.4 | Capability profile (version/success/deps/failures/benchmarks) | Ch 16 | M11 registry + benchmarks | **Built** | M11 (done) |
| A2.4 | Statistical competence | Ch 28 | M8 `competence/model.py` | **Built** | M8 (done) |
| A2.5 | Skill evolution pipeline | Ch 15/27 | M17 `learning/skill_pipeline.py` (`SkillEvolutionPipeline` + `attach_skill_pipeline`, + `learning/skill_stage.py`; consumes `learning.validated`/`reflection.skill`, offers `skill.candidate`) | **Built** | M17 (done) |
| A2.6 | Resource Manager (unified) | Ch 45-48 | M18 `resources/scheduler.py` (`ResourceManager.allocate_best`, budgets, single allocation authority) | **Built** | M18 (Resource Manager v2) |
| A2.6 | Cost-aware selection / economics | Ch 48 | M18 `resources/economics.py` (`ResourceBudget`/`ResourcePolicy`/`ResourceReservation`) + `scheduler.py` scoring | **Built** | M18 |
| A2.6 | Dynamic reallocation | Ch 46 | M18 `resources/scheduler.py::mark_unavailable` (substitute/degrade/queue failover) | **Built** | M18 |
| A2.7 | Retrieval Router | Ch 14.13 | M19 `memory/retrieval_router.py` (`RetrievalRouter`, factory `memory/controller.py::build_retrieval_router`, FAILURE tier via `memory/failure_memory.py`) | **Built** | M19 (done) |
| A2.8 | Exploration Engine | Ch 25/66 | M7 `environments/unknown/` | **Built** | M7 (done) — make normative |
| A2.9 | Statistical evaluation / scoring | Ch 28 | M8/M11 competence | **Built** | M8/M11 (done) |
| A2.10 | Layered reflection (5 layers) | Ch 13 | M20 `cognition/reflection_layers.py` (`LongTermReflector`/`SkillReflector`/`ArchitecturalReflector` + `attach_reflection_layers`, consuming `reflection.completed`; `ReflectionLayer` taxonomy in `cognition/reflection.py`) | **Built** | M20 (done) |
| A2.11 | Seven-tier memory | Ch 14/50 | M8 (Working/Episodic/Semantic/Procedural) + M21 failure (`memory/failure_memory.py`) + M21 slice 2 Capability (`memory/capability_memory.py::CapabilityMemory`, view from `competence.updated`) + Preference (`memory/preference_memory.py::PreferenceMemory`, upsert-by-key), all registered in `memory/controller.py::build_retrieval_router` | **Built** | M21 (done — slice 2) |
| A2.11 | Failure memory | Ch 14 | M21 `memory/failure_memory.py` (consumes M24 loop) | **Built** | M21 (done — slice 1) |
| A2.12 | Cognitive State Manager | Ch 67 | M22 `cognition/state.py` (`CognitiveStateManager`: `cognitive_load`/`background_active`, full mode coverage from events, `should_interrupt`/`suggested_thinking_depth`; wired `kernel.cognitive_state`) | **Built** | M22 (done) |
| A2.13 | Web Environment Runtime (browser as generic desktop env) | Ch 23/29/30 | M23 `perception/active_window.py`, `actions/desktop_browser.py` | **Built** | M23 (done) |
| A2.14 | Structured failure model (FailureDomain/Severity/StructuredFailure) | Ch 21/34 | M24 `verification/failure.py` | **Built** | M24 (done) |
| A2.14 | Verification-event producer (recovery-loop activation) | Ch 34/52 | M24 `verification/publisher.py` — activates dormant `verification.completed` loop | **Built** | M24 (done) |
| A2.14 | Observability as an event consumer | Ch 21 | M24 `observability/failure_log.py` | **Built** | M24 (done) |
| A2.15 | Learned Choice & Preference Resolution | Ch 10/14/36 | M25 deliberation/decision_point.py + deliberation/preference_resolver.py (DecisionPoint + PreferenceResolver + attach_preference_resolver; wired kernel.preference_resolver) | **Built** | M25 (done) |

## Summary by state

- **Built:** every v2.1 concept is now implemented and tested on the kernel substrate —
  **nothing remains Partial or Absent; the entire Architecture v2.1 (A2.1–A2.14) is Built,
  and the first post-v2.1 amendment (A2.15) is also Built.**
  A2.1 (World Model v2 — freshness/TTL/provenance/staleness, M15), A2.2 (Environment
  Intelligence — fingerprints + capability invalidation + version-aware adaptation, M15),
  A2.3 (Deliberation v2 — expanded utility + safety term + recovery contracts, M16),
  A2.4/A2.9 (capability lifecycle + statistical competence, M8/M11), A2.5 (skill pipeline,
  M17), A2.6 (Resource Manager v2 — unified allocation + economics + dynamic reallocation,
  M18), A2.7 (retrieval router, M19), A2.8 (exploration, M7), A2.10 (layered reflection,
  M20), A2.11 **seven-tier memory** — all seven tiers built: Working/Episodic/Semantic/
  Procedural (M8) + Failure (M21 slice 1) + Capability + Preference (M21 slice 2) —
  A2.12 (Cognitive State Manager, M22), A2.13 (Web Environment Runtime, M23), A2.14
  (structured failure + recovery-loop activation, M24), and **A2.15** (Learned Choice &
  Preference Resolution, M25 — first post-v2.1 milestone) are all Built.
- **Partial (remaining expansion):** none — the last Partial row (A2.11 seven-tier memory)
  is now Built.
- **Absent (new build):** none.
