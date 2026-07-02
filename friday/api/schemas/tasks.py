"""Task monitoring schemas."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class TaskStepSchema(BaseModel):
    """A single step in a task plan."""

    order: int
    action_type: str
    target: str
    description: str
    status: str = Field(..., description="pending, running, completed, failed, skipped")
    result: Optional[str] = None


class TaskStatusSchema(BaseModel):
    """Status of an executing task plan."""

    goal: str
    total_steps: int
    completed_steps: int
    progress: float = Field(..., description="0.0 to 1.0")
    is_complete: bool
    current_step: Optional[int] = None
    steps: List[TaskStepSchema] = Field(default_factory=list)


class TaskMonitorResponse(BaseModel):
    """Response for task monitoring endpoint."""

    active: bool = Field(..., description="Whether a task is currently executing")
    task: Optional[TaskStatusSchema] = None
