"""Cognitive control loop: The core perception-reasoning-action-verification cycle.

This module implements the self-repair loop that replaces static automation flows.
It operates purely on observed WorldState and never hallucinates success.
"""

from __future__ import annotations

import time
from typing import Optional

from awareness.world_state import WorldState
from awareness.perception_snapshot import PerceptionSnapshot
from .goal_schema import Goal
from .goal_parser import parse_goal
from .state_gap_analyzer import compute_missing_states, is_goal_satisfied, describe_missing_states
from .action_planner import build_action_plan, simplify_plan, validate_plan
from .error_models import classify_error, should_retry, get_recovery_action
from .ui_pattern_memory import get_ui_pattern_memory
from .task_graph import build_task_graph, TaskStatus
from core.self_repair import create_self_repair_engine


class CognitiveLoop:
    """Implements the closed-loop autonomous control system.
    
    This is the core of the new architecture:
    1. PERCEIVE  → Build WorldState snapshot
    2. UNDERSTAND → Convert user intent into Goal
    3. ANALYZE → Compute missing states
    4. PLAN → Create semantic actions
    5. EXECUTE → Perform one action
    6. VERIFY → Observe world again
    7. REPAIR → If mismatch, adapt
    8. REPEAT → Until Goal is satisfied
    """
    
    def __init__(self, automation_services, awareness_state):
        """Initialize the cognitive loop.
        
        Args:
            automation_services: AutomationServices instance for execution
            awareness_state: StateCache for perception
        """
        self.automation = automation_services
        self.awareness_state = awareness_state
        self.max_iterations = 15
        self.max_retries_per_action = 3
        self.ui_memory = get_ui_pattern_memory()
        self.self_repair = create_self_repair_engine()
        self.use_task_graph = True  # Enable task graph mode
    
    def execute_goal(self, command: str) -> str:
        """Execute a user command through the cognitive control loop.
        
        Args:
            command: Natural language command from user
            
        Returns:
            Final response message describing outcome
        """
        # HARD ROUTE: Visual Chrome opening
        if "open chrome" in command.lower():
            from automation.chrome_pipeline import open_chrome
            try:
                success = open_chrome()
                if not success:
                    raise RuntimeError("Chrome failed to open via taskbar anchor.")
                return "Chrome opened successfully."
            except Exception as e:
                raise RuntimeError(f"Chrome opening failed: {e}")
        
        # 1. UNDERSTAND: Parse command into formal Goal
        goal = parse_goal(command)
        
        # 2. PERCEIVE: Build initial WorldState
        world = self._perceive()
        if not world:
            return "I cannot perceive the current state. Awareness system may be unavailable."
        
        # Track execution
        iteration = 0
        action_history = []
        
        # Main control loop
        while iteration < self.max_iterations:
            iteration += 1
            
            # 3. ANALYZE: Check if goal is satisfied
            if is_goal_satisfied(goal, world):
                return self._build_success_message(goal, action_history)
            
            # 4. ANALYZE: Compute what's missing
            missing_states = compute_missing_states(goal, world)
            if not missing_states:
                # Goal should be satisfied but isn't - edge case
                return self._build_partial_success_message(goal, action_history)
            
            # 5. PLAN: Build action sequence (use task graph if enabled)
            if self.use_task_graph:
                # Convert WorldState to PerceptionSnapshot
                snapshot = PerceptionSnapshot.from_world_state(world)
                
                # PHASE 9: Check for cached UI patterns
                intent_hash = f"{goal.intent}_{goal.target_entity or command}"
                try:
                    cached_patterns = self.ui_memory.find_similar_patterns(
                        world_state=world,
                        goal_intent=goal.intent
                    )
                    if cached_patterns:
                        # Use learned pattern if available
                        pass  # Pattern will be used by action planner
                except Exception:
                    pass
                
                task_graph = build_task_graph(command, snapshot)
                
                # Execute task graph
                result = self._execute_task_graph(task_graph, goal, action_history)
                if result:
                    return result
                
                # If task graph execution completes, check goal
                world = self._perceive()
                if world and is_goal_satisfied(goal, world):
                    return self._build_success_message(goal, action_history)
                
                # Continue to legacy planner as fallback
            
            # Legacy planner (fallback)
            plan = build_action_plan(missing_states, world, goal_intent=goal.intent)
            plan = simplify_plan(plan)
            
            if not plan or not validate_plan(plan, world):
                return self._build_failure_message(
                    goal,
                    f"Cannot build valid action plan. Missing: {describe_missing_states(missing_states)}",
                    action_history
                )
            
            # 6. EXECUTE: Execute first action with REPAIR LOOP
            action = plan[0]
            MAX_REPAIR_ATTEMPTS = 3
            action_succeeded = False
            
            for attempt in range(MAX_REPAIR_ATTEMPTS):
                # Get before snapshot
                before_world = world
                before_snapshot = PerceptionSnapshot.from_world_state(before_world)
                
                # Execute action
                success, message, verification = self.automation.execute_semantic_action(
                    action, world, goal
                )
                
                # Get after snapshot
                after_world = self._perceive()
                if not after_world:
                    return self._build_failure_message(
                        goal,
                        "Lost perception after action execution.",
                        action_history
                    )
                after_snapshot = PerceptionSnapshot.from_world_state(after_world)
                
                # TRUTH ENFORCEMENT: Only accept success if semantically verified
                semantic_success = verification.get("semantic_success", False)
                if success and not semantic_success:
                    success = False
                    message = f"Verification failed: {message}"
                
                action_history.append({
                    "iteration": iteration,
                    "attempt": attempt + 1,
                    "action": action.type,
                    "target": action.target,
                    "success": success,
                    "semantic_success": semantic_success,
                    "message": message,
                })
                
                if success and semantic_success:
                    action_succeeded = True
                    
                    # PHASE 9: PERSIST VISUAL MEMORY
                    if action.target and verification.get("state_changed"):
                        try:
                            intent_hash = f"{goal.intent}_{goal.target_entity or action.target}"
                            self.ui_memory.record_success(
                                world_state=after_world,
                                goal_intent=goal.intent,
                                action_type=action.type,
                                element_text=action.target,
                                element_type="unknown",
                            )
                        except Exception:
                            pass
                    
                    break
                
                # PART 4: ATTEMPT REPAIR
                if attempt < MAX_REPAIR_ATTEMPTS - 1:
                    try:
                        repaired = self.self_repair.attempt_repair(
                            before_snapshot,
                            after_snapshot,
                            action,
                            self.automation
                        )
                        
                        if repaired:
                            # PART 5: LEARNING AFTER REPAIR
                            # Save repair success to memory
                            try:
                                if hasattr(self.self_repair, 'repair_history') and self.self_repair.repair_history:
                                    last_repair = self.self_repair.repair_history[-1]
                                    
                                    # Store in UI memory for future reference
                                    import json
                                    from pathlib import Path
                                    
                                    memory_file = Path("memory/ui_memory.json")
                                    if memory_file.exists():
                                        with open(memory_file, 'r') as f:
                                            memory_data = json.load(f)
                                    else:
                                        memory_data = {"version": "1.0", "patterns": [], "repairs": []}
                                    
                                    if "repairs" not in memory_data:
                                        memory_data["repairs"] = []
                                    
                                    memory_data["repairs"].append({
                                        "intent": goal.intent,
                                        "diagnosis": last_repair.get("diagnosis", {}),
                                        "strategy": last_repair.get("strategy", ""),
                                        "action_type": last_repair.get("action_type", ""),
                                        "success_pattern": after_snapshot.screen_hash,
                                    })
                                    
                                    # Keep only last 100 repairs
                                    memory_data["repairs"] = memory_data["repairs"][-100:]
                                    
                                    with open(memory_file, 'w') as f:
                                        json.dump(memory_data, f, indent=2)
                            except Exception:
                                pass
                            
                            # Repair succeeded, wait and retry
                            from .timing import wait_for_state_change
                            
                            def get_hash():
                                w = self._perceive()
                                return w.compute_hash() if w else ""
                            
                            wait_for_state_change(get_hash, timeout=1.5, poll_interval=0.2)
                            world = self._perceive()
                            if not world:
                                break
                            continue
                        else:
                            # Repair failed, break out
                            break
                    except Exception:
                        break
                
                # Update world for next attempt
                world = after_world
            
            # 2️⃣ REPAIR LOOP ASSERTION: Cannot skip verification
            if not action_succeeded:
                # Get last action result from history
                last_action = action_history[-1] if action_history else {}
                last_semantic_success = last_action.get("semantic_success", False)
                
                # HARD ASSERTION: If we're here, semantic_success MUST be False
                if last_semantic_success:
                    raise RuntimeError(
                        "CRITICAL: Repair loop exited with action_succeeded=False but semantic_success=True. "
                        "This should be impossible."
                    )
                
                # PART 7: HARD RULE - Honest failure reporting with diagnosis
                from core.repair_diagnostics import diagnose_failure
                from core.repair_strategies import describe_failure
                
                try:
                    # Get final snapshots for diagnosis
                    final_before = PerceptionSnapshot.from_world_state(before_world)
                    final_after = PerceptionSnapshot.from_world_state(world)
                    
                    # Diagnose why all repairs failed
                    final_diagnosis = diagnose_failure(final_before, final_after, action, action.target)
                    diagnosis_description = describe_failure(final_diagnosis)
                    
                    # Build honest failure message with diagnosis
                    return (
                        f"I failed to complete this because: {diagnosis_description}. "
                        f"I attempted {len(action_history)} actions including repairs, but verification failed. "
                        f"I cannot proceed without human intervention."
                    )
                except Exception:
                    # Fallback if diagnosis fails
                    return self._build_failure_message(
                        goal,
                        f"Action failed: {action.type}. {describe_missing_states(missing_states)}",
                        action_history
                    )
            
            # 8. VERIFY: Re-perceive the world (wait for state to settle)
            from .timing import wait_for_state_change
            
            def get_hash():
                w = self._perceive()
                return w.compute_hash() if w else ""
            
            wait_for_state_change(get_hash, timeout=1.0, poll_interval=0.2)
            world = self._perceive()
            if not world:
                return self._build_failure_message(
                    goal,
                    "Lost perception after action execution.",
                    action_history
                )
        
        # Max iterations reached
        return self._build_timeout_message(goal, action_history)
    
    def _execute_task_graph(self, task_graph, goal, action_history) -> Optional[str]:
        """Execute task graph with self-repair.
        
        Args:
            task_graph: TaskGraph to execute
            goal: Goal being pursued
            action_history: Action history list
            
        Returns:
            Result message or None to continue with legacy planner
        """
        from .cognitive_loop_task_graph import execute_task_graph
        return execute_task_graph(self, task_graph, goal, action_history)
    
    def _perceive(self) -> Optional[WorldState]:
        """Build current WorldState from awareness system."""
        if not self.awareness_state:
            return None
        try:
            return self.awareness_state.build_world_state()
        except Exception:
            return None
    
    def _build_success_message(self, goal: Goal, action_history: list) -> str:
        """Build success message."""
        action_count = len(action_history)
        if action_count == 0:
            return f"Goal already satisfied: {goal.desired_effect}"
        elif action_count == 1:
            return f"Completed: {goal.desired_effect}"
        else:
            return f"Completed: {goal.desired_effect} (took {action_count} actions)"
    
    def _build_partial_success_message(self, goal: Goal, action_history: list) -> str:
        """Build partial success message."""
        return f"Attempted: {goal.desired_effect}. Current state appears correct but verification is uncertain."
    
    def _build_failure_message(self, goal: Goal, reason: str, action_history: list) -> str:
        """Build failure message."""
        action_count = len(action_history)
        if action_count == 0:
            return f"Cannot achieve: {goal.desired_effect}. {reason}"
        else:
            return f"Failed after {action_count} actions: {reason}"
    
    def _build_timeout_message(self, goal: Goal, action_history: list) -> str:
        """Build timeout message."""
        return f"Goal not achieved within iteration limit: {goal.desired_effect}. Took {len(action_history)} actions."
