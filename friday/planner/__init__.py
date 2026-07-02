"""Planner layer — goal decomposition and task graph execution.

The planner NEVER directly controls devices. It outputs task plans
that the action layer executes. The planner observes outcomes and
replans when actions fail.

Components:
- GoalParser: NL → structured Goal (intent, target, parameters)
- TaskDecomposer: Goal → TaskPlan (ordered steps with postconditions)
- Future: Replanner (failure → revised plan using LLM)

Cycle: Observe → Plan → Act → Verify → Repair/Replan
"""

from friday.planner.goal_parser import Goal, GoalIntent, GoalParser
from friday.planner.decomposer import TaskDecomposer, TaskPlan, TaskStep, TaskStatus
from friday.planner.replanner import Replanner, ReplanContext, ReplanResult
from friday.planner.operator_planner import OperatorPlanner, OperatorPlan, OperatorStep
from friday.planner.requirements import RequirementsDiscovery, Requirement, RequirementSet

__all__ = [
    "Goal",
    "GoalIntent",
    "GoalParser",
    "TaskDecomposer",
    "TaskPlan",
    "TaskStep",
    "TaskStatus",
    "Replanner",
    "ReplanContext",
    "ReplanResult",
    "OperatorPlanner",
    "OperatorPlan",
    "OperatorStep",
    "RequirementsDiscovery",
    "Requirement",
    "RequirementSet",
]
