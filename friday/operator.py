"""Operator — the closed-loop General Operator engine.

Per ADR-021: ties together the full cycle for ARBITRARY goals:

    Goal
      ↓
    Requirements Discovery   (what must be true?)
      ↓
    Capability Planning      (compose capabilities)
      ↓
    Execution                (data flows between steps)
      ↓
    Verification             (are requirements satisfied?)
      ↓
    Repair / Replan          (unmet requirements → new plan)
      ↓
    Completion

This is NOT a workflow. The same loop handles any goal because it reasons
about requirements and verifies completion, then self-corrects.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class OperatorOutcome:
    """Final outcome of operating toward a goal."""

    goal: str
    completed: bool
    summary: str
    requirements_total: int = 0
    requirements_met: int = 0
    iterations: int = 0
    created_files: List[str] = field(default_factory=list)
    final_content: str = ""
    trace: List[str] = field(default_factory=list)
    # M14: the ExecutionEvidence bundle from the final execution, exposed so
    # capability benchmarks can score against the Evidence Law. Optional and
    # defaulted so all existing construction sites/behavior are unchanged.
    evidence: Any = None

    @property
    def completion_ratio(self) -> float:
        if self.requirements_total == 0:
            return 1.0 if self.completed else 0.0
        return self.requirements_met / self.requirements_total


class Operator:
    """Closed-loop General Operator.

    Usage:
        operator = Operator(
            model_router=router,
            browser_controller=controller,
        )
        outcome = operator.run("Research X, write a report, save it")

        if outcome.completed:
            print(outcome.summary)
        else:
            print(f"Partial: {outcome.requirements_met}/{outcome.requirements_total}")
    """

    def __init__(
        self,
        model_router=None,
        browser_controller=None,
        max_iterations: int = 3,
        browser_strategy=None,
        state_cache=None,
    ) -> None:
        self._model_router = model_router
        self._browser = browser_controller
        self._max_iterations = max_iterations
        self._browser_strategy = browser_strategy
        # Awareness UIA state cache (production path). When present, the executor's
        # Universal Perception fills the Accessibility/UIA tier from it; when absent
        # (e.g. the standalone benchmark runner) perception degrades to OCR+pixels.
        self._state_cache = state_cache

        # Lazy imports to keep construction light
        from friday.planner.requirements import RequirementsDiscovery
        from friday.planner.operator_planner import OperatorPlanner
        from friday.tools.registry import build_default_registry
        from friday.executor import GoalExecutor
        from friday.perception.environment import EnvironmentObserver

        self._discovery = RequirementsDiscovery(model_router=model_router)
        self._registry = build_default_registry()

        # M1: make the Universal Action Layer LIVE (was orphaned per audit).
        # Initialize primitives with the real browser controller and register
        # them in the registry so they are discoverable + usable.
        try:
            from friday.actions import primitives as _primitives
            _primitives.init_primitives(browser_controller=browser_controller)
            _primitives.register_primitives(self._registry)
            self._primitives_ready = True
        except Exception:
            self._primitives_ready = False

        self._planner = OperatorPlanner(registry=self._registry, model_router=model_router)
        self._executor = GoalExecutor(
            model_router=model_router,
            browser_controller=browser_controller,
            state_cache=state_cache,
        )
        self._observer = EnvironmentObserver()

    def run(self, goal: str) -> OperatorOutcome:
        """Run the full operator cycle toward a goal.

        Returns OperatorOutcome describing what was accomplished.
        """
        trace: List[str] = []
        t_start = time.time()

        if self._browser_strategy is not None:
            trace.append(f"Browser strategy: {self._browser_strategy.mode.value} "
                         f"({self._browser_strategy.reason})")

        # LATENCY OPT: requirements discovery and the first capability plan are
        # independent LLM calls (both only need the goal text). On the free-tier
        # NVIDIA endpoint each can cold-start ~20-30s; running them sequentially
        # is the 60-90s bottleneck. Fire both in parallel for the first iteration.
        import concurrent.futures as _cf
        env_state_pre = self._observer.snapshot()
        with _cf.ThreadPoolExecutor(max_workers=2) as _pool:
            _fut_req = _pool.submit(self._discovery.discover, goal)
            _fut_plan = _pool.submit(self._planner.plan, goal, env_state_pre)
            req_set = _fut_req.result()
            _prefetched_plan = _fut_plan.result()

        trace.append(f"Discovered {len(req_set.requirements)} requirements "
                     f"({'LLM' if req_set.from_llm else 'fallback'}) "
                     f"[discovery+plan ran in parallel]")
        for r in req_set.requirements:
            trace.append(f"  - {r.description}")

        all_created_files: List[str] = []
        final_content = ""
        iterations = 0
        prev_met = -1

        # 2-5. PLAN → EXECUTE → VERIFY → REPLAN loop
        for iteration in range(self._max_iterations):
            iterations = iteration + 1

            # OBSERVE environment (reuse existing state)
            env_state = self._observer.snapshot()

            # PLAN capabilities (LLM-decomposed, requirements-aware).
            # First iteration reuses the plan prefetched in parallel with
            # discovery (avoids a second sequential cold-start LLM call).
            if iteration == 0 and _prefetched_plan is not None:
                plan = _prefetched_plan
            else:
                plan = self._planner.plan(goal, env_state=env_state)
            trace.append(f"Iteration {iterations}: planned {plan.total_steps} steps "
                         f"({plan.skipped_steps} skipped)")

            # EXECUTE with data flow
            exec_result = self._executor.execute_plan(plan, goal)
            all_created_files.extend(exec_result.created_files)
            if exec_result.final_content:
                final_content = exec_result.final_content
            trace.extend(exec_result.step_log)

            # BLOCKED STATE: a captcha/verification wall was hit. Do NOT keep
            # re-running the same path (that caused the captcha tab-spam loop).
            # Stop, surface it honestly, let a higher layer/human intervene.
            if getattr(exec_result, "blocked", False):
                trace.append("BLOCKED: verification/captcha wall encountered — "
                             "halting retries to avoid a tab-spam loop")
                self._verify_requirements(req_set, exec_result)
                break

            # VERIFY requirements against what was produced
            self._verify_requirements(req_set, exec_result)
            met = sum(1 for r in req_set.requirements if r.satisfied and r.blocking)
            total = sum(1 for r in req_set.requirements if r.blocking)
            trace.append(f"Iteration {iterations}: {met}/{total} requirements met")

            # COMPLETE if all requirements satisfied
            if req_set.all_satisfied:
                trace.append("All requirements satisfied — goal complete")
                break

            # PER-REQUIREMENT REPAIR (M4): instead of re-running the whole plan,
            # diagnose each unmet requirement and run a TARGETED repair for it.
            unmet = [r for r in req_set.requirements if not r.satisfied and r.blocking]
            if unmet and iteration < self._max_iterations - 1:
                repaired_any = self._repair_unmet(unmet, exec_result, goal, trace)
                if repaired_any:
                    # Re-verify after the targeted repair.
                    self._verify_requirements(req_set, exec_result)
                    met = sum(1 for r in req_set.requirements if r.satisfied and r.blocking)
                    trace.append(f"Iteration {iterations}: after repair {met}/{total} met")
                    if req_set.all_satisfied:
                        trace.append("All requirements satisfied after repair")
                        if exec_result.final_content:
                            final_content = exec_result.final_content
                        all_created_files.extend(exec_result.created_files)
                        break

            # Accept partial success ONLY on the final iteration. Earlier
            # iterations must keep trying to satisfy MORE requirements via
            # repair/replan. Previously `steps_executed > 0` was always true,
            # so the loop broke after iteration 1 and self-correction was dead.
            is_last_iteration = iteration >= self._max_iterations - 1
            made_real_artifact = (
                bool(exec_result.created_files) or bool(exec_result.final_content)
            )
            improved = met > prev_met  # satisfied more requirements than before

            if is_last_iteration:
                if made_real_artifact or met > 0:
                    trace.append(f"Iteration {iterations}: final iteration, accepting "
                                 f"partial success ({met}/{total} requirements)")
                else:
                    trace.append("Max iterations reached")
                break

            if improved:
                # Real progress was made — keep iterating to satisfy the rest.
                trace.append(f"Iteration {iterations}: progress "
                             f"({met}/{total} met), continuing to repair the rest")
                prev_met = met
                continue

            # No improvement this iteration. If we at least produced an
            # artifact, accept it; otherwise replan once more.
            if made_real_artifact:
                trace.append(f"Iteration {iterations}: no new requirements met but "
                             f"artifact produced, accepting ({met}/{total})")
                break
            trace.append("No progress — replanning")
            prev_met = met

        met = sum(1 for r in req_set.requirements if r.satisfied and r.blocking)
        total = sum(1 for r in req_set.requirements if r.blocking)

        # Deduplicate created files (iterations may recreate the same file)
        unique_files = list(dict.fromkeys(all_created_files))

        return OperatorOutcome(
            goal=goal,
            completed=req_set.all_satisfied,
            summary=self._build_summary(goal, req_set, unique_files, final_content),
            requirements_total=total,
            requirements_met=met,
            iterations=iterations,
            created_files=unique_files,
            final_content=final_content,
            trace=trace,
            evidence=getattr(exec_result, "evidence", None),
        )

    def _repair_unmet(self, unmet, exec_result, goal, trace) -> bool:
        """Diagnose each unmet requirement and run a TARGETED repair (M4).

        Returns True if any repair action was executed. Repairs reuse the
        existing execution evidence so we don't redo satisfied work.
        """
        from friday.planner.repair import RepairDiagnoser

        diagnoser = RepairDiagnoser()
        evidence = getattr(exec_result, "evidence", None)
        if evidence is None:
            return False

        repaired_any = False
        for req in unmet:
            diagnosis = diagnoser.diagnose(
                req.description, evidence,
                blocked=getattr(exec_result, "blocked", False),
            )
            if not diagnosis.repairable or not diagnosis.actions:
                trace.append(f"Repair skipped for '{req.description[:40]}': {diagnosis.note}")
                continue

            trace.append(f"Repairing '{req.description[:40]}' "
                         f"(cause={diagnosis.cause.value}): {diagnosis.note}")
            ran = self._executor.execute_repair(diagnosis.actions, goal, exec_result)
            if ran:
                repaired_any = True
                trace.append(f"  repair ran {len(diagnosis.actions)} action(s)")

        return repaired_any

    def _verify_requirements(self, req_set, exec_result) -> None:
        """Mark requirements satisfied using the EVIDENCE LAW (M0).

        A requirement is satisfied ONLY when a matching evidence artifact
        exists in exec_result.evidence. Generated text can satisfy a
        "produce content" requirement but NEVER a "gather/research/deliver"
        requirement. No evidence ⇒ requirement stays UNMET.

        This replaces the previous heuristic that marked research satisfied
        whenever any content was generated (the false-positive engine).
        """
        from friday.verification.evidence_law import (
            EvidenceVerifier, RequirementKind, classify_requirement,
        )

        evidence = getattr(exec_result, "evidence", None)
        if evidence is None:
            from friday.verification.evidence_law import ExecutionEvidence
            evidence = ExecutionEvidence()

        verifier = EvidenceVerifier()

        for req in req_set.requirements:
            verdict = verifier.verify_one(req.description, evidence)

            # Delivery requirements remain non-blocking (send is safety-gated),
            # but they are NEVER marked satisfied without a real confirmation.
            if verdict.kind == RequirementKind.DELIVER:
                req.blocking = False

            req.satisfied = verdict.satisfied
            req.evidence = verdict.evidence_detail if verdict.satisfied else ""
            if not verdict.satisfied:
                # Record the honest reason for being unmet.
                req.evidence = f"UNMET: {verdict.reason}"

    def _build_summary(self, goal, req_set, files, content) -> str:
        """Build a human-readable outcome summary."""
        met = sum(1 for r in req_set.requirements if r.satisfied)
        total = len(req_set.requirements)
        parts = [f"Requirements: {met}/{total} met"]

        if files:
            parts.append(f"Files: {', '.join(files)}")
        if content:
            parts.append(f"Content:\n{content[:500]}")

        # List unmet requirements
        unmet = [r.description for r in req_set.requirements if not r.satisfied and r.blocking]
        if unmet:
            parts.append(f"Unmet: {'; '.join(unmet[:3])}")

        return " | ".join(parts)
