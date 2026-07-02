"""Task monitoring routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from friday.api.schemas.tasks import TaskMonitorResponse, TaskStatusSchema, TaskStepSchema


def build_router(ctx, auth) -> APIRouter:
    """Build the tasks router."""
    router = APIRouter(prefix="/api", tags=["tasks"])

    @router.get("/tasks/current", response_model=TaskMonitorResponse, dependencies=[Depends(auth)])
    async def current_task() -> TaskMonitorResponse:
        """Get the currently executing task plan (if any).

        Returns active=false when idle. When a FRIDAY goal is running,
        returns the task plan with per-step status for live monitoring.
        """
        if not ctx.memory:
            return TaskMonitorResponse(active=False)

        goal = ctx.memory.working.active_goal
        if not goal:
            return TaskMonitorResponse(active=False)

        # Build status from the active goal in working memory
        task = TaskStatusSchema(
            goal=goal.text,
            total_steps=goal.steps_total,
            completed_steps=goal.steps_completed,
            progress=(goal.steps_completed / goal.steps_total) if goal.steps_total else 0.0,
            is_complete=goal.status == "completed",
            current_step=goal.steps_completed,
            steps=[],  # Detailed steps populated by executor when wired
        )
        return TaskMonitorResponse(active=True, task=task)

    return router
