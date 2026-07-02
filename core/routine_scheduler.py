"""Background scheduler for Jarvis proactive routines."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, time as time_cls
from typing import Callable, Optional, List


Callback = Callable[[], None]


@dataclass
class ScheduledTask:
    name: str
    callback: Callback
    next_run: datetime
    interval: Optional[timedelta] = None
    daily_time: Optional[time_cls] = None


class RoutineScheduler:
    """Simple thread-based scheduler supporting interval and daily tasks."""

    def __init__(self) -> None:
        self._tasks: List[ScheduledTask] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def add_interval_task(self, name: str, interval_seconds: int, callback: Callback) -> None:
        interval = timedelta(seconds=max(1, interval_seconds))
        next_run = datetime.now() + interval
        task = ScheduledTask(name=name, callback=callback, next_run=next_run, interval=interval)
        with self._lock:
            self._tasks.append(task)

    def add_daily_task(self, name: str, hour: int, minute: int, callback: Callback) -> None:
        daily_time = time_cls(hour=hour % 24, minute=minute % 60)
        next_run = self._next_daily_occurrence(daily_time)
        task = ScheduledTask(name=name, callback=callback, next_run=next_run, daily_time=daily_time)
        with self._lock:
            self._tasks.append(task)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            task = self._get_next_task()
            if task is None:
                # No tasks registered yet
                self._stop_event.wait(1.0)
                continue

            now = datetime.now()
            wait_seconds = max(0.0, (task.next_run - now).total_seconds())
            if self._stop_event.wait(wait_seconds):
                break

            # Execute due tasks
            due_tasks = self._collect_due_tasks()
            for due in due_tasks:
                try:
                    due.callback()
                except Exception as exc:  # pragma: no cover - defensive logging
                    print(f"[Scheduler] Task '{due.name}' failed: {exc}")
                finally:
                    self._reschedule(due)

    def _get_next_task(self) -> Optional[ScheduledTask]:
        with self._lock:
            if not self._tasks:
                return None
            return min(self._tasks, key=lambda t: t.next_run)

    def _collect_due_tasks(self) -> List[ScheduledTask]:
        now = datetime.now()
        due: List[ScheduledTask] = []
        with self._lock:
            for task in self._tasks:
                if task.next_run <= now:
                    due.append(task)
        return due

    def _reschedule(self, task: ScheduledTask) -> None:
        with self._lock:
            if task.interval:
                task.next_run = datetime.now() + task.interval
            elif task.daily_time:
                task.next_run = self._next_daily_occurrence(task.daily_time)
            else:
                # One-shot task; remove from schedule
                self._tasks = [t for t in self._tasks if t is not task]

    @staticmethod
    def _next_daily_occurrence(target_time: time_cls) -> datetime:
        now = datetime.now()
        today_target = datetime.combine(now.date(), target_time)
        if today_target > now:
            return today_target
        return today_target + timedelta(days=1)
