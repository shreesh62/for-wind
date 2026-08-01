"""M13 — the validation scenario catalog (18 realistic goal categories).

Each :class:`ValidationScenario` is a realistic end-to-end goal, not a synthetic
unit test. Scenarios needing real browser/desktop/network/GPU are flagged
``requires_live=True`` so the runner SKIPS them under ``FRIDAY_DRY_RUN`` (never
fabricating pass/fail). The catalog covers all 18 required categories from the
M13 milestone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ValidationScenario:
    """One realistic end-to-end validation goal."""

    id: str
    category: str
    goal_text: str
    expectations: str = ""
    risk: str = "low"
    requires_live: bool = False
    probe_id: str = ""


# The 18 required validation categories (Requirement 1.5).
CATEGORIES: Tuple[str, ...] = (
    "browser_automation",
    "desktop_automation",
    "multi_environment",
    "research",
    "file_generation",
    "long_running",
    "interruption_resume",
    "crash_recovery",
    "browser_failure_recovery",
    "unknown_application",
    "concurrent_goals",
    "human_confirmation",
    "event_replay",
    "checkpoint_restore",
    "memory_consistency",
    "world_model_consistency",
    "goal_graph_consistency",
    "deterministic_replay",
    "realistic_interaction",
)


_SCENARIOS: Tuple[ValidationScenario, ...] = (
    ValidationScenario(
        "browser.search_read", "browser_automation",
        "Search the web for the latest stable Python release and read the announcement page.",
        expectations="Real search + at least one source page read; SOURCE_URL evidence recorded.",
        requires_live=True,
    ),
    ValidationScenario(
        "desktop.open_app", "desktop_automation",
        "Open the system calculator and confirm it is in the foreground.",
        expectations="App launched; window focus verified.",
        requires_live=True,
    ),
    ValidationScenario(
        "multi.research_to_doc", "multi_environment",
        "Research a topic in the browser, then generate a summary document on disk.",
        expectations="Browser gather → file artifact; evidence spans both environments.",
        requires_live=True,
    ),
    ValidationScenario(
        "research.position_paper", "research",
        "Research a current-events topic using official sources and produce a cited summary.",
        expectations="GATHERED_INFO + SOURCE_URL evidence; citations map to real sources.",
        requires_live=True,
    ),
    ValidationScenario(
        "file.generate_report", "file_generation",
        "Generate a short report file about a given topic and save it.",
        expectations="FILE_ARTIFACT with byte size > 0; GENERATED_CONTENT recorded.",
        requires_live=False,
    ),
    ValidationScenario(
        "long.multistep_project", "long_running",
        "Run a multi-stage project (research, draft, revise, export) to completion.",
        expectations="Goal persists across many steps; completes or reports partial honestly.",
        requires_live=True,
    ),
    ValidationScenario(
        "interrupt.pause_resume", "interruption_resume",
        "Start a long research goal, interrupt it midway, then resume it.",
        expectations="Goal suspends and resumes; no lost/duplicated work.",
        requires_live=True,
        probe_id="interrupt.pause_resume",
    ),
    ValidationScenario(
        "crash.restart_restore", "crash_recovery",
        "Begin a goal, simulate a process crash, restart, and resume from checkpoint.",
        expectations="Kernel restore replays the event log; goal state survives.",
        requires_live=True,
        probe_id="crash.restart_restore",
    ),
    ValidationScenario(
        "browser_fail.reconnect", "browser_failure_recovery",
        "Run a browser goal, kill the browser mid-task, and recover.",
        expectations="Recovery re-establishes a controller or degrades honestly.",
        requires_live=True,
        probe_id="browser_fail.reconnect",
    ),
    ValidationScenario(
        "unknown.explore_app", "unknown_application",
        "Operate an application never seen before to complete a simple goal.",
        expectations="Exploration builds an object graph; no app-specific logic used.",
        requires_live=True,
    ),
    ValidationScenario(
        "concurrent.two_goals", "concurrent_goals",
        "Run two independent goals concurrently and complete both.",
        expectations="Both goals progress; resources scheduled without deadlock.",
        requires_live=True,
    ),
    ValidationScenario(
        "human.confirm_send", "human_confirmation",
        "Attempt an irreversible action (send) that requires human confirmation.",
        expectations="Action gated pending confirmation; no send without approval.",
        requires_live=True,
        probe_id="human.confirm_send",
    ),
    ValidationScenario(
        "replay.event_log", "event_replay",
        "Execute a goal, then replay the durable event log.",
        expectations="Replay yields the same goal lifecycle events in order.",
        requires_live=False,
        probe_id="replay.event_log",
    ),
    ValidationScenario(
        "checkpoint.restore_state", "checkpoint_restore",
        "Checkpoint the kernel mid-goal, restore into a fresh kernel, and continue.",
        expectations="Restored goal ids/states match pre-checkpoint.",
        requires_live=False,
        probe_id="checkpoint.restore_state",
    ),
    ValidationScenario(
        "memory.episode_consistency", "memory_consistency",
        "Complete a goal and confirm exactly one episode is recorded.",
        expectations="Memory sink records one episode; no duplicates/omissions.",
        requires_live=False,
    ),
    ValidationScenario(
        "world.belief_consistency", "world_model_consistency",
        "Run a goal that updates beliefs and confirm the World Model stays consistent.",
        expectations="No contradictory active beliefs left unresolved.",
        requires_live=True,
    ),
    ValidationScenario(
        "goalgraph.transitions", "goal_graph_consistency",
        "Run a goal with sub-goals and confirm the Goal Graph transitions are valid.",
        expectations="Every node reaches a terminal or waiting state legally.",
        requires_live=True,
    ),
    ValidationScenario(
        "determinism.repeat_run", "deterministic_replay",
        "Run an identical goal twice and confirm identical ordered lifecycle events.",
        expectations="Two runs produce identical ordered goal.* event types.",
        requires_live=False,
    ),
    # ---- Realistic human-like interaction scenarios ----
    # These exercise clicks, typing, scrolling, and navigation against the user's
    # REAL Chrome profile (CDP). They represent what FRIDAY actually does for a user:
    # operate signed-in sessions, compose messages, interact with UI elements.
    # Require --cdp (real Chrome with logins) to produce meaningful evidence.
    ValidationScenario(
        "interact.search_click_read", "realistic_interaction",
        "Open Google in my browser, type a search query about machine learning, "
        "click the first result, and read the article content.",
        expectations="Search typed, result clicked (via DOM element), page content read. "
        "Evidence: navigation to google.com, typed text, click on a link, content gathered.",
        requires_live=True,
    ),
    ValidationScenario(
        "interact.scroll_and_extract", "realistic_interaction",
        "Open my browser to a news site, scroll down to find more articles, "
        "and extract the headlines of at least 3 articles.",
        expectations="Page scrolled, headlines extracted from DOM after scroll. "
        "Evidence: scroll action, gathered text with multiple headlines.",
        requires_live=True,
    ),
    ValidationScenario(
        "interact.form_fill", "realistic_interaction",
        "Open a web page with a form, fill in a name and email field, "
        "then confirm the fields are populated.",
        expectations="Fields located via DOM, text typed into each, values confirmed. "
        "Evidence: type_text actions on specific elements, verification of field values.",
        requires_live=True,
    ),
    ValidationScenario(
        "interact.tab_switch_compose", "realistic_interaction",
        "Open two browser tabs — one with a reference page, one with a text editor "
        "or compose window — switch between them and type a short note referencing "
        "content from the first tab.",
        expectations="Multiple tabs opened, switched, content from tab 1 used in tab 2. "
        "Evidence: navigation to 2 URLs, tab switch, typed content.",
        requires_live=True,
    ),
)


def all_scenarios() -> Tuple[ValidationScenario, ...]:
    """Return the full validation scenario catalog."""
    return _SCENARIOS


def categories() -> Tuple[str, ...]:
    """Return the 18 required validation category names."""
    return CATEGORIES
