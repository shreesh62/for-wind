"""Task graph execution methods for cognitive loop.

Separated to keep cognitive_loop.py focused on the main control flow.
"""

from __future__ import annotations

from typing import Optional

from awareness.perception_snapshot import PerceptionSnapshot
from automation.task_graph import TaskGraph, TaskStatus, TaskNode
from automation.goal_schema import Goal


def execute_task_graph(
    cognitive_loop,
    task_graph: TaskGraph,
    goal: Goal,
    action_history: list
) -> Optional[str]:
    """Execute a task graph with self-repair.
    
    Args:
        cognitive_loop: CognitiveLoop instance
        task_graph: Task graph to execute
        goal: Goal being pursued
        action_history: Action history list to append to
        
    Returns:
        Result message if execution completes, None to continue with legacy planner
    """
    max_task_iterations = 20
    iteration = 0
    
    while not task_graph.is_complete() and iteration < max_task_iterations:
        iteration += 1
        
        # Get executable tasks
        executable = task_graph.get_executable_tasks()
        
        if not executable:
            # No tasks ready - check if we're stuck
            if task_graph.get_failed_tasks():
                # Try self-repair on failed tasks
                for failed_task in task_graph.get_failed_tasks():
                    if failed_task.should_retry():
                        # Get current perception
                        world = cognitive_loop._perceive()
                        if not world:
                            return "Lost perception during task graph execution."
                        
                        # Convert to snapshot for self-repair
                        before_snapshot = PerceptionSnapshot.from_world_state(world)
                        
                        # Execute and get after snapshot
                        success, message, verification = cognitive_loop.automation.execute_semantic_action(
                            failed_task.action, world, goal
                        )
                        
                        after_world = cognitive_loop._perceive()
                        if not after_world:
                            return "Lost perception after action execution."
                        
                        after_snapshot = PerceptionSnapshot.from_world_state(after_world)
                        
                        # TRUTH ENFORCEMENT
                        semantic_success = verification.get("semantic_success", False)
                        if success and not semantic_success:
                            success = False
                            message = "Verification failed"
                        
                        if success and semantic_success:
                            task_graph.mark_completed(failed_task.task_id)
                        else:
                            # Analyze failure and apply repair
                            strategy = cognitive_loop.self_repair.analyze_failure(
                                failed_task,
                                before_snapshot,
                                after_snapshot
                            )
                            
                            if strategy:
                                cognitive_loop.self_repair.apply_repair_to_graph(
                                    task_graph,
                                    failed_task,
                                    strategy
                                )
                            else:
                                task_graph.mark_failed(failed_task.task_id, message)
            else:
                # No executable and no failed - graph is stuck
                return None
        else:
            # Execute first ready task
            task = executable[0]
            
            # Get current perception
            world = cognitive_loop._perceive()
            if not world:
                return "Lost perception during task execution."
            
            # Execute action
            success, message, verification = cognitive_loop.automation.execute_semantic_action(
                task.action, world, goal
            )
            
            # TRUTH ENFORCEMENT
            semantic_success = verification.get("semantic_success", False)
            if success and not semantic_success:
                success = False
                message = "Action verification failed"
            
            action_history.append({
                "task_id": task.task_id,
                "action": task.action.type,
                "target": task.action.target,
                "success": success,
                "semantic_success": semantic_success,
                "message": message,
            })
            
            if success and semantic_success:
                task_graph.mark_completed(task.task_id)
                
                # Record success for learning
                if task.action.target and verification.get("state_changed"):
                    try:
                        cognitive_loop.ui_memory.record_success(
                            world_state=world,
                            goal_intent=goal.intent,
                            action_type=task.action.type,
                            element_text=task.action.target,
                            element_type="unknown",
                        )
                    except Exception:
                        pass
            else:
                task_graph.mark_failed(task.task_id, message)
    
    # Check if goal is satisfied
    world = cognitive_loop._perceive()
    if world:
        from automation.state_gap_analyzer import is_goal_satisfied
        if is_goal_satisfied(goal, world):
            return cognitive_loop._build_success_message(goal, action_history)
    
    # Task graph execution complete but goal not satisfied - return None to try legacy planner
    return None
