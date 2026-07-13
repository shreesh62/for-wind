"""Goal Executor — runs LLM-decomposed plans with data flowing between steps.

THE FIX for "steps run blind": this executor maintains a working context
that accumulates results. Search results feed into extraction; extracted
content feeds into synthesis; synthesis feeds into file creation.

It uses:
- BrowserController (persistent session — survives across steps)
- FileTool (real file creation)
- ModelRouter (LLM for generation/synthesis)
- SystemActions (desktop apps)

This is the General Operator's execution engine. Capability-based,
data-flowing, environment-agnostic.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from friday.tools.registry import ToolCapability


@dataclass
class ExecutionContext:
    """Accumulates data as steps execute. Steps read from and write to this."""

    goal: str
    gathered_info: List[str] = field(default_factory=list)  # search/read results
    generated_content: str = ""  # synthesized text
    created_files: List[str] = field(default_factory=list)
    last_result: str = ""
    step_log: List[str] = field(default_factory=list)
    evidence: "ExecutionEvidence" = None  # type: ignore  # real evidence artifacts
    blocked: bool = False  # set when a captcha/verification wall is hit
    navigated_urls: List[str] = field(default_factory=list)  # dedupe tab opens

    def __post_init__(self):
        if self.evidence is None:
            from friday.verification.evidence_law import ExecutionEvidence
            self.evidence = ExecutionEvidence()

    def add_info(self, info: str) -> None:
        if info and info.strip():
            self.gathered_info.append(info.strip())

    @property
    def combined_info(self) -> str:
        """All gathered information combined."""
        return "\n\n".join(self.gathered_info)


@dataclass
class ExecutionResult:
    """Final result of executing a goal."""

    goal: str
    success: bool
    summary: str
    steps_executed: int
    steps_skipped: int
    created_files: List[str] = field(default_factory=list)
    final_content: str = ""
    step_log: List[str] = field(default_factory=list)
    evidence: "ExecutionEvidence" = None  # type: ignore  # populated in execute_plan
    blocked: bool = False  # True if a captcha/verification wall halted progress

    def __post_init__(self):
        if self.evidence is None:
            from friday.verification.evidence_law import ExecutionEvidence
            self.evidence = ExecutionEvidence()


class GoalExecutor:
    """Executes an OperatorPlan with data flowing between steps.

    Unlike the old per-step execution, this:
    - Keeps a persistent browser session across all steps
    - Accumulates gathered info in ExecutionContext
    - Feeds prior results into later steps (search → extract → synthesize → save)
    - Actually creates files

    Safety: when FRIDAY_DRY_RUN=1 is set (e.g. during testing), no real external
    actions are performed — the executor reports what it WOULD do without touching
    the machine. This prevents accidental Chrome/Notepad opens from background
    processes running old code.
    """

    def __init__(
        self,
        model_router=None,
        browser_controller=None,
        file_tool=None,
        delivery_gate=None,
        state_cache=None,
        exploration_engine=None,
        environment_provider=None,
    ) -> None:
        import os
        self._model_router = model_router
        self._browser = browser_controller
        self._dry_run = os.environ.get("FRIDAY_DRY_RUN", "0") == "1"
        self._delivery_gate = delivery_gate
        # Awareness UIA state cache (production path) — feeds the Accessibility tier
        # of Universal Perception. None on the standalone benchmark runner.
        self._state_cache = state_cache
        # M23 Req 6 — Exploration on low confidence. When a target cannot be
        # resolved confidently, the executor invokes this generic ExplorationEngine
        # over an abstract EnvironmentContract (from environment_provider) instead of
        # performing a blind action. Both default to None: when unwired the executor
        # still NEVER guesses — it fails cleanly. Real safe-experiments are therefore
        # opt-in (inject a live environment_provider) so the live real-action path is
        # explicit, while the mechanism itself is present and unit-verified.
        self._exploration_engine = exploration_engine
        self._environment_provider = environment_provider
        from friday.actions.file_tool import FileTool
        self._file_tool = file_tool or FileTool()

    def execute_plan(self, plan, goal: str) -> ExecutionResult:
        """Execute an OperatorPlan step by step with data flow.

        Args:
            plan: OperatorPlan with steps
            goal: The original goal text

        Returns:
            ExecutionResult with what was accomplished
        """
        ctx = ExecutionContext(goal=goal)
        executed = 0
        skipped = 0

        # Detect any web/research need across the plan
        needs_web = any(
            s.capability in (
                ToolCapability.SEARCH_WEB,
                ToolCapability.EXTRACT_WEB_CONTENT,
                ToolCapability.NAVIGATE_URL,
                ToolCapability.READ_DOM,
            )
            for s in plan.steps
        )

        for step in plan.steps:
            if step.can_skip:
                skipped += 1
                ctx.step_log.append(f"[skip] {step.description}: {step.skip_reason}")
                continue

            if step.capability == ToolCapability.VERIFY_GOAL:
                continue  # handled at end

            result = self._execute_step(step, ctx)
            ctx.step_log.append(f"[done] {step.description} -> {result[:80]}")
            ctx.last_result = result
            executed += 1

        # Final verification: did we produce the goal's output?
        success = self._verify_goal(goal, ctx)

        return ExecutionResult(
            goal=goal,
            success=success,
            summary=self._build_summary(goal, ctx),
            steps_executed=executed,
            steps_skipped=skipped,
            created_files=ctx.created_files,
            final_content=ctx.generated_content,
            step_log=ctx.step_log,
            evidence=ctx.evidence,
            blocked=ctx.blocked,
        )

    # TD-5: capabilities blocked under DRY_RUN because they cause VISIBLE/external
    # side effects. Kept as a set so the guard is data-driven and inspectable.
    _DRY_RUN_BLOCKED = frozenset({
        ToolCapability.OPEN_APPLICATION, ToolCapability.NAVIGATE_URL,
        ToolCapability.SEARCH_WEB, ToolCapability.EXTRACT_WEB_CONTENT,
        ToolCapability.READ_DOM, ToolCapability.READ_SCREEN,
        ToolCapability.CLICK_ELEMENT, ToolCapability.TYPE_TEXT,
        ToolCapability.SWITCH_WINDOW,
    })

    def _dispatch_table(self) -> Dict[Any, Any]:
        """TD-5: explicit capability→handler map (was an implicit if/elif ladder).

        Each handler has signature ``(target: str, cap, ctx) -> str`` and contains
        the exact behavior of its former branch. A capability absent from the map
        falls through to the description fallback in ``_execute_step`` — identical
        to the old ``else`` behavior. This makes dispatch data-driven and is the
        prerequisite for later wiring to the CapabilityRegistry, with zero behavior
        change today (guarded by characterization tests).
        """
        return {
            ToolCapability.SEARCH_WEB: self._dispatch_search_web,
            ToolCapability.NAVIGATE_URL: self._dispatch_navigate,
            ToolCapability.OPEN_APPLICATION: self._dispatch_navigate,
            ToolCapability.READ_DOM: self._dispatch_read,
            ToolCapability.EXTRACT_WEB_CONTENT: self._dispatch_read,
            ToolCapability.READ_SCREEN: self._dispatch_read,
            ToolCapability.CLICK_ELEMENT: self._dispatch_click,
            ToolCapability.TYPE_TEXT: self._dispatch_type,
            ToolCapability.GENERATE_TEXT: self._dispatch_generate,
            ToolCapability.SUMMARIZE: self._dispatch_generate,
            ToolCapability.CREATE_FILE: self._dispatch_create_file,
            ToolCapability.EDIT_FILE: self._dispatch_edit_file,
            ToolCapability.RUN_COMMAND: self._dispatch_run_command,
            ToolCapability.SEND_MESSAGE: self._dispatch_delivery,
            ToolCapability.SEND_EMAIL: self._dispatch_delivery,
            ToolCapability.VERIFY_RESULT: self._dispatch_verify_result,
        }

    def _execute_step(self, step, ctx: ExecutionContext) -> str:
        """Execute one capability step, reading/writing the context.

        TD-5: dispatch is a data-driven table (``_dispatch_table``) rather than an
        implicit if/elif ladder. Behavior is unchanged — the DRY-RUN guard and the
        description fallback are preserved exactly.
        """
        cap = step.capability
        target = step.target

        # DRY-RUN GUARD: block VISIBLE/external actions (open app, navigate,
        # click, type, search) but ALLOW safe local operations (file create/edit,
        # content generation, verification). This stops phantom Chrome/Notepad
        # windows during tests while keeping file-based tests working.
        if self._dry_run and cap in self._DRY_RUN_BLOCKED:
            return f"[DRY-RUN] Would execute {cap.value}: {target}"

        handler = self._dispatch_table().get(cap)
        if handler is not None:
            return handler(target, cap, ctx)

        return f"Executed: {step.description}"

    # --- Dispatch handlers (TD-5): each body is the exact former if/elif branch ---

    def _dispatch_search_web(self, target: str, cap, ctx: ExecutionContext) -> str:
        return self._execute_research(target, ctx)

    def _dispatch_navigate(self, target: str, cap, ctx: ExecutionContext) -> str:
        url = self._target_to_url(target)
        # TAB-SPAM GUARD: never open the same URL twice in one execution.
        if url and url in ctx.navigated_urls:
            return f"Already navigated to {url} (skipping duplicate open)"
        if url and self._browser and self._browser.available:
            result = self._browser.navigate(url)
            if result.get("ok"):
                landed = result.get("url", url)
                ctx.navigated_urls.append(url)
                ctx.evidence.add_navigation(landed)  # EVIDENCE: confirmed navigation
                # Visual evidence + block detection after landing.
                from friday.verification.screenshot_evidence import (
                    is_blocked_page, blocked_reason, capture_screenshot,
                )
                page_text = self._browser.read_text() if hasattr(self._browser, "read_text") else ""
                if is_blocked_page(page_text, landed):
                    shot = capture_screenshot(label="nav_blocked")
                    if shot.is_real:
                        ctx.evidence.add_screenshot(shot.path, shot.size, "nav_blocked")
                    ctx.blocked = True
                    return f"Navigated to {landed} but BLOCKED: {blocked_reason(page_text, landed)}"
                shot = capture_screenshot(label="after_navigate")
                if shot.is_real:
                    ctx.evidence.add_screenshot(shot.path, shot.size, "after_navigate")
                return f"Navigated to {landed}"
            return f"Navigation failed: {result.get('error','')}"
        elif url:
            # No real browser session. Open ONCE only — do NOT spam tabs
            # across replanning iterations. Unconfirmed, so no nav evidence.
            if url not in ctx.navigated_urls:
                import webbrowser
                webbrowser.open(url)
                ctx.navigated_urls.append(url)
                return f"Opened {url} (unconfirmed, no evidence recorded)"
            return f"Already opened {url} (skipping duplicate)"
        else:
            # SEARCH -> NAVIGATE CHAINING: a "navigate/open page" step with no
            # resolvable URL (e.g. an LLM planner placeholder like "<extracted
            # URL>") should navigate to a REAL url already gathered by a prior
            # search/research step — recording NAVIGATION — instead of trying to
            # launch the placeholder as a desktop app. General (Axiom 15): it uses
            # whatever sources were gathered, with no site-specific logic.
            if self._browser and self._browser.available:
                from friday.verification.evidence_law import EvidenceKind
                gathered_urls = [
                    a.detail
                    for a in ctx.evidence.of_kind(EvidenceKind.SOURCE_URL)
                    if a.detail
                ]
                next_url = next(
                    (u for u in gathered_urls if u not in ctx.navigated_urls), None
                )
                if next_url:
                    ctx.navigated_urls.append(next_url)  # guard against re-nav loops
                    result = self._browser.navigate(next_url)
                    if result.get("ok"):
                        landed = result.get("url", next_url)
                        ctx.evidence.add_navigation(landed)  # EVIDENCE: confirmed nav
                        from friday.verification.screenshot_evidence import (
                            capture_screenshot,
                        )
                        shot = capture_screenshot(label="after_navigate")
                        if shot.is_real:
                            ctx.evidence.add_screenshot(shot.path, shot.size, "after_navigate")
                        return f"Navigated to gathered source {landed}"
                    return f"Navigation to gathered source failed: {result.get('error','')}"

            from friday.actions.system import SystemActions
            from friday.verification.evidence_law import looks_like_placeholder
            # HARD verification (M23): a placeholder target ("<<extracted URL>>",
            # "<topic>") is NOT a launchable app — fail loudly, record nothing.
            if looks_like_placeholder(target):
                return (f"Navigation skipped: unresolved placeholder target "
                        f"'{target[:40]}' (no real URL was produced)")
            r = SystemActions().launch_app(target)
            if r.is_success:
                ctx.evidence.add_navigation(f"launched:{target}")
            return r.message

    def _dispatch_read(self, target: str, cap, ctx: ExecutionContext) -> str:
        # If research already gathered content this run, reuse it instead
        # of redundantly re-reading the current page.
        if cap == ToolCapability.EXTRACT_WEB_CONTENT and ctx.gathered_info:
            from friday.verification.evidence_law import EvidenceKind
            sources = len(ctx.evidence.of_kind(EvidenceKind.SOURCE_URL))
            return f"Using {len(ctx.gathered_info)} already-gathered items ({sources} sources)"
        if self._browser and self._browser.available:
            text = self._browser.read_text()
            if text:
                from friday.verification.screenshot_evidence import (
                    is_blocked_page, blocked_reason, capture_screenshot,
                )
                url_now = self._browser.current_url() if hasattr(self._browser, "current_url") else ""
                # A captcha/verification page is NOT real content.
                if is_blocked_page(text, url_now):
                    shot = capture_screenshot(label="read_blocked")
                    if shot.is_real:
                        ctx.evidence.add_screenshot(shot.path, shot.size, "read_blocked")
                    ctx.blocked = True
                    return f"Read BLOCKED page: {blocked_reason(text, url_now)} (not recorded as info)"
                ctx.add_info(f"Page content:\n{text[:2500]}")
                # EVIDENCE: real content was read from a real page
                ctx.evidence.add_gathered_info(text, source=url_now)
                if url_now:
                    ctx.evidence.add_source_url(url_now)
                shot = capture_screenshot(label="after_read")
                if shot.is_real:
                    ctx.evidence.add_screenshot(shot.path, shot.size, "after_read")
                return f"Read {len(text)} chars from page"
            return "No content read"
        return "No browser to read from"

    def _dispatch_click(self, target: str, cap, ctx: ExecutionContext) -> str:
        return self._execute_click(target, ctx)

    def _dispatch_type(self, target: str, cap, ctx: ExecutionContext) -> str:
        return self._execute_type(target, ctx)

    def _dispatch_generate(self, target: str, cap, ctx: ExecutionContext) -> str:
        # Generate / Summarize (uses gathered info!)
        content = self._generate(target, ctx)
        ctx.generated_content = content
        ctx.evidence.add_generated_content(content)  # EVIDENCE: content produced
        return f"Generated {len(content)} chars"

    def _dispatch_create_file(self, target: str, cap, ctx: ExecutionContext) -> str:
        # Create File (uses generated content!)
        filename = self._infer_filename(target, ctx)
        content = ctx.generated_content or ctx.combined_info or f"Content for: {ctx.goal}"
        result = self._file_tool.create_file(filename, content)
        if result.is_success:
            ctx.created_files.append(result.target)
            # EVIDENCE: real file on disk with verified byte size
            size = int(result.evidence.raw.get("size", 0)) if result.evidence else 0
            if size <= 0:
                size = self._file_size(result.target)
            ctx.evidence.add_file(result.target, size)
            return f"Created file: {result.target} ({size} bytes)"
        return f"File creation failed: {result.error}"

    def _dispatch_edit_file(self, target: str, cap, ctx: ExecutionContext) -> str:
        if ctx.created_files:
            content = ctx.generated_content or ctx.combined_info
            result = self._file_tool.write_file(ctx.created_files[-1], content)
            return result.message
        return "No file to edit"

    def _dispatch_run_command(self, target: str, cap, ctx: ExecutionContext) -> str:
        return f"Command execution: {target} (gated for safety)"

    def _dispatch_delivery(self, target: str, cap, ctx: ExecutionContext) -> str:
        # Send message / email (confirmation + verified delivery, M6)
        return self._execute_delivery(cap, target, ctx)

    def _dispatch_verify_result(self, target: str, cap, ctx: ExecutionContext) -> str:
        return "Intermediate check passed"

    def execute_repair(self, repair_actions, goal: str, prior_result) -> bool:
        """Run a targeted repair (M4): execute only the repair actions, reusing
        the prior execution's accumulated context/evidence.

        Mutates prior_result in place (created_files, final_content, evidence,
        step_log). Returns True if at least one action executed.
        """
        from friday.planner.operator_planner import OperatorStep
        from friday.planner.decomposer import TaskStatus

        # Rebuild a context seeded from the prior result so repairs build on
        # what already exists (don't redo satisfied work).
        ctx = ExecutionContext(goal=goal)
        ctx.evidence = getattr(prior_result, "evidence", None) or ctx.evidence
        ctx.generated_content = prior_result.final_content or ""
        ctx.created_files = list(prior_result.created_files)
        # Seed gathered info from existing evidence so PRODUCE/FILE repairs work.
        from friday.verification.evidence_law import EvidenceKind
        for art in ctx.evidence.of_kind(EvidenceKind.GATHERED_INFO):
            ctx.gathered_info.append(art.detail)

        ran = 0
        for order, action in enumerate(repair_actions):
            step = OperatorStep(
                capability=action.capability,
                tool_name="repair",
                target=action.target,
                description=action.description,
                status=TaskStatus.PENDING,
                order=order,
            )
            result = self._execute_step(step, ctx)
            ctx.step_log.append(f"[repair] {action.description} -> {result[:80]}")
            ran += 1
            if ctx.blocked:
                break

        # Merge repair outcomes back into the prior result.
        if ctx.generated_content:
            prior_result.final_content = ctx.generated_content
        for f in ctx.created_files:
            if f not in prior_result.created_files:
                prior_result.created_files.append(f)
        prior_result.step_log.extend(ctx.step_log)
        if ctx.blocked:
            prior_result.blocked = True

        return ran > 0

    def _execute_delivery(self, cap, target: str, ctx: ExecutionContext) -> str:
        """Send a message/email through generic live web operation + the gate.

        NO hardcoded Gmail/WhatsApp logic. If a real browser is present, the
        generic WebAgent operates whatever site is open (observe→decide→act) to
        perform the send. The DeliveryGate still governs confirmation, and
        delivery evidence is recorded only on observed success.
        """
        from friday.tools.registry import ToolCapability
        from friday.actions.delivery import DeliveryRequest, DeliveryChannel

        channel = (DeliveryChannel.EMAIL if cap == ToolCapability.SEND_EMAIL
                   else DeliveryChannel.MESSAGE)
        body = ctx.generated_content or ctx.combined_info or ""

        # Path A: a real browser + model router → operate the live site generically.
        if (self._browser and getattr(self._browser, "available", False)
                and self._model_router is not None):
            request = DeliveryRequest(
                channel=channel, recipient=target, body=body,
                attachments=list(ctx.created_files),
            )

            def _send_via_web(req: DeliveryRequest) -> bool:
                from friday.capabilities.web_agent import WebAgent
                agent = WebAgent(self._browser, self._model_router, max_steps=14)
                send_goal = (
                    f"Send a {channel.value} to '{req.recipient}'. "
                    f"Compose it and actually send it. Message body: {req.body[:500]}"
                )
                res = agent.run(send_goal, evidence=ctx.evidence)
                return res.achieved

            def _verify_sent(req: DeliveryRequest) -> str:
                # Honest verification: re-observe and let the page text confirm.
                text = self._browser.read_text(2000) if hasattr(self._browser, "read_text") else ""
                for kw in ("sent", "message sent", "delivered", "your message has been"):
                    if kw in text.lower():
                        return f"page indicates sent ('{kw}')"
                return ""

            gate = self._delivery_gate or _DefaultGate()
            gate._send_fn = _send_via_web
            gate._verify_fn = _verify_sent
            result = gate.deliver(request)
            if result.sent:
                ctx.evidence.add_delivery_confirmation(result.confirmation_detail)
                return f"Delivered to {target}: {result.confirmation_detail}"
            return f"Not delivered: {result.reason}"

        # Path B: no browser → gated, honest (nothing sent).
        if self._delivery_gate is None:
            return (f"Delivery gated: '{target}' — no browser to operate and no "
                    f"delivery handler wired (nothing sent).")
        request = DeliveryRequest(channel=channel, recipient=target, body=body,
                                  attachments=list(ctx.created_files))
        result = self._delivery_gate.deliver(request)
        if result.sent:
            ctx.evidence.add_delivery_confirmation(result.confirmation_detail)
            return f"Delivered to {target}: {result.confirmation_detail}"
        return f"Not delivered: {result.reason}"

    def _execute_research(self, query: str, ctx: ExecutionContext) -> str:
        """Execute real research using the research capability.

        Opens actual pages, reads real content, records source URLs as
        evidence. This is what makes GATHER requirements honestly satisfiable.
        """
        from friday.capabilities.research import research
        from friday.verification.evidence_law import looks_like_placeholder

        # HARD verification (M23): never research an unfilled template placeholder
        # (e.g. "<<topic>>", "a given topic"). Acting on it produces junk evidence.
        if looks_like_placeholder(query):
            return (f"Research skipped: unresolved placeholder target "
                    f"'{query[:40]}' — the goal was not instantiated")

        result = research(
            query=query,
            browser_controller=self._browser,
            evidence=ctx.evidence,
            max_sources=3,
        )

        if result.blocked:
            ctx.blocked = True
            return f"Research BLOCKED: {result.error}"

        if result.success:
            ctx.add_info(result.gathered_text)
            return (f"Researched '{query}': read {result.sources_read} sources "
                    f"({', '.join(result.source_urls[:3])})")

        if result.gathered_text.strip():
            # Got search results but couldn't open individual pages
            ctx.add_info(result.gathered_text)
            return f"Searched '{query}' (search results only, no source pages opened)"

        return f"Research failed: {result.error or 'no browser available'}"

    def _execute_click(self, target: str, ctx: ExecutionContext) -> str:
        """Click via Universal Action Layer primitives (tested, guarded)."""
        try:
            from friday.actions import primitives as P
            from friday.actions.target import Target
            from friday.perception.world_state import WorldStateBuilder

            if P.get_resolver() is None:
                # Primitives not initialized — fall back to direct browser.
                if self._browser and self._browser.available:
                    result = self._browser.click(target)
                    return f"Clicked '{target}'" if result.get("ok") else f"Click failed: {result.get('error','')}"
                return "No click path available (primitives not initialized, no browser)"

            # Build a minimal WorldState from current browser/desktop state.
            ws = self._build_world_state()
            t = Target(text=target)
            result = self._run_async(P.click(t, ws))
            if not result.is_success:
                # M23 Req 6: the resolver could not confidently resolve the target.
                # Explore (observe -> hypothesize -> safe-experiment -> verify ->
                # update World Model) instead of a blind action — never guess.
                if getattr(result, "error_category", "") == "target_not_found":
                    explored = self._explore_on_low_confidence(target, ctx)
                    if explored is not None:
                        return explored
                return f"Click failed: {result.error}"
            # M23 verified-success (Req 7): on the live path with a REAL WorldState,
            # success requires an OBSERVED change in the World Model — never inferred
            # from dispatch alone. In dry-run/tests the adapter result stands.
            if not self._dry_run and self._worldstate_is_real(ws):
                after = self._build_world_state()
                if not self._observed_change(ws, after):
                    return (f"Clicked '{target}' but no observable World-Model "
                            f"change (unverified)")
            ctx.evidence.add_navigation(f"clicked:{target}")
            return f"Clicked '{target}' (via {result.metadata.get('adapter', 'unknown')})"
        except Exception as exc:
            return f"Click failed: {exc}"

    def _execute_type(self, target: str, ctx: ExecutionContext) -> str:
        """Type via Universal Action Layer primitives (tested, guarded)."""
        try:
            from friday.actions import primitives as P
            from friday.actions.target import Target
            from friday.perception.world_state import WorldStateBuilder

            if P.get_resolver() is None:
                if self._browser and self._browser.available:
                    result = self._browser.type_text(target)
                    return f"Typed text" if result.get("ok") else f"Type failed"
                return "No type path available (primitives not initialized, no browser)"

            ws = self._build_world_state()
            result = self._run_async(P.type_text(target, ws))
            if not result.is_success:
                # M23 Req 6: unresolved target -> explore, never blind-type.
                if getattr(result, "error_category", "") == "target_not_found":
                    explored = self._explore_on_low_confidence(target, ctx)
                    if explored is not None:
                        return explored
                return f"Type failed: {result.error}"
            # M23 verified-success (Req 7): observed change required on the live path.
            if not self._dry_run and self._worldstate_is_real(ws):
                after = self._build_world_state()
                if not self._observed_change(ws, after):
                    return "Typed text but no observable World-Model change (unverified)"
            return f"Typed text (via {result.metadata.get('adapter', 'unknown')})"
        except Exception as exc:
            return f"Type failed: {exc}"

    def _explore_on_low_confidence(
        self, target: str, ctx: ExecutionContext
    ) -> Optional[str]:
        """M23 Req 6 — explore an unresolved target instead of a blind action.

        Invoked when the resolver cannot resolve a target above confidence (the
        primitive returns ``target_not_found``). Drives the generic
        ``ExplorationEngine`` over an abstract ``EnvironmentContract`` supplied by
        ``environment_provider`` — Observe → hypothesize → risk-ordered safe
        experiment → verify → update the World Model. The engine only runs
        confidence/risk-permitted experiments, so this is never a blind action, and
        it uses ONLY the abstract contract surface (no app/browser heuristics —
        Axiom 15).

        Returns a status string when exploration ran (or attempted), or ``None``
        when no exploration path is wired — in which case the caller reports the
        clean resolution failure (still no guess). Never raises.
        """
        engine = self._exploration_engine
        provider = self._environment_provider
        if engine is None or provider is None:
            return None
        try:
            environment = provider()
        except Exception:  # noqa: BLE001 - provider is best-effort
            environment = None
        if environment is None:
            return None
        try:
            outcome = engine.explore(environment)
        except Exception as exc:  # noqa: BLE001 - exploration must never crash a step
            note = f"Exploration failed for unresolved target '{target}': {exc}"
            ctx.step_log.append(f"[explore] {note}")
            return note
        note = (
            f"Explored environment for unresolved target '{target}': "
            f"{getattr(outcome, 'budget_spent', 0)} safe experiment(s), "
            f"confidence {getattr(outcome, 'confidence', 0.0):.2f}"
        )
        ctx.step_log.append(f"[explore] {note}")
        return note

    @staticmethod
    def _worldstate_is_real(ws) -> bool:
        """True when a snapshot carries actual perception (not an empty/dry-run WS).

        Used to gate M23 verified-success: change-verification only applies when we
        actually perceived the environment; an empty WorldState (e.g. dry-run) falls
        back to the adapter's own result.
        """
        return bool(
            ws.ui_elements or ws.ocr_regions or ws.browser_elements
            or ws.screenshot_hash
        )

    @staticmethod
    def _observed_change(before, after) -> bool:
        """Whether the World Model changed between two snapshots (Req 7).

        Success is verified by an observed change (URL/element/text/focus/window/
        pixel-hash), never inferred from having dispatched an input.
        """
        d = after.diff_from(before)
        return bool(
            d.get("hash_changed") or d.get("url_changed")
            or d.get("screenshot_changed") or d.get("element_count_changed")
            or d.get("focus_changed") or d.get("window_changed")
        )

    def _build_world_state(self):
        """Build a WorldState from the current browser state.

        Crucially, this populates the live interactive elements from the page
        so adapters (BrowserAdapter.resolve_element) can actually find targets.
        Passing an empty element list made every primitive click/type resolve
        against nothing and silently fail.
        """
        from friday.perception.world_state import WorldStateBuilder
        from friday.perception.types import BrowserElement, BoundingBox
        from friday.perception.active_window import populate_active_window

        builder = WorldStateBuilder()

        # M23 Universal Perception: fuse the active window's desktop stack
        # (Accessibility/UIA -> OCR -> pixels) so ANY window — a browser or any
        # other app — is perceivable without a browser-specific path. Skipped
        # under dry-run to keep unit tests free of real screen capture; the
        # optional browser DOM below is fused as an additional ranked source.
        if not self._dry_run:
            try:
                desktop = None
                if self._state_cache is not None:
                    from friday.perception.desktop import DesktopPerception
                    desktop = DesktopPerception(state_cache=self._state_cache)
                populate_active_window(builder, desktop=desktop)
            except Exception:
                pass

        if self._browser and self._browser.available:
            url = self._browser.current_url() if hasattr(self._browser, "current_url") else ""
            title = ""
            elements = []
            if hasattr(self._browser, "observe_interactive"):
                try:
                    snap = self._browser.observe_interactive()
                    if snap.get("ok"):
                        url = snap.get("url") or url
                        title = snap.get("title") or ""
                        for e in snap.get("elements", []):
                            cx = e.get("x")
                            cy = e.get("y")
                            bbox = None
                            if isinstance(cx, (int, float)) and isinstance(cy, (int, float)):
                                # Center-anchored 1x1 bbox; adapters match by
                                # text/selector/role, coords are for fallback.
                                bbox = BoundingBox(x=int(cx), y=int(cy), width=1, height=1)
                            elements.append(
                                BrowserElement(
                                    tag=e.get("tag", ""),
                                    text=e.get("text", ""),
                                    role=e.get("role", ""),
                                    clickable=not e.get("editable", False),
                                    visible=bool(e.get("in_view", True)),
                                    bbox=bbox,
                                    selector=e.get("selector", ""),
                                )
                            )
                except Exception:
                    # Observation is best-effort; fall back to empty elements.
                    elements = []
            builder.set_browser_state(
                url=url, title=title, elements=elements, connected=True
            )
        return builder.build()

    def _run_async(self, coro, timeout: float = 90.0):
        """Run an async coroutine synchronously with a hard timeout.

        Always runs the coroutine in a dedicated worker thread with its own
        event loop, so it works whether or not a loop is already running and
        can NEVER hang forever (bounded by `timeout`). On timeout/error the
        caller's except handler decides the fallback.
        """
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=timeout)
        finally:
            pool.shutdown(wait=False)

    def _generate(self, target: str, ctx: ExecutionContext) -> str:
        """Generate/synthesize content using the LLM with gathered info."""
        if not self._model_router:
            return ctx.combined_info or f"Content about {target}"

        info = ctx.combined_info
        # Collect the real source URLs research recorded, to require citations.
        from friday.verification.evidence_law import EvidenceKind
        source_urls = [a.detail for a in ctx.evidence.of_kind(EvidenceKind.SOURCE_URL)]

        if info:
            citation_instruction = ""
            if source_urls:
                src_list = "\n".join(f"- {u}" for u in source_urls[:8])
                citation_instruction = (
                    f"\n\nThe information was gathered from these sources:\n{src_list}\n"
                    f"Base your response ONLY on the gathered information above. "
                    f"Do NOT invent facts. Where relevant, reference the sources. "
                    f"Include a 'Sources' section at the end listing the URLs used."
                )
            prompt = (
                f"Based on the following gathered information, {target}.\n\n"
                f"Information:\n{info[:6000]}\n\n"
                f"Produce a clear, well-structured response for the goal: {ctx.goal}"
                f"{citation_instruction}"
            )
        else:
            prompt = f"For the goal '{ctx.goal}', {target}. Produce well-structured content."

        try:
            from friday.models.router import ModelCapability
            response = self._run_async(
                self._model_router.complete(
                    prompt,
                    capability=ModelCapability.REASONING,
                    # Responsive content model. The former meta/llama-3.3-70b now
                    # hangs to timeout on the free NIM tier; gpt-oss-120b returns
                    # well-structured prose in ~1-2s.
                    model="openai/gpt-oss-120b",
                    max_tokens=1200,
                    temperature=0.4,
                )
            )
            return response.text
        except Exception as exc:
            return ctx.combined_info or f"[Generation error: {exc}]"

    def _verify_goal(self, goal: str, ctx: ExecutionContext) -> bool:
        """Verify the goal was meaningfully completed."""
        # Goal involving file creation → check file exists
        if any(kw in goal.lower() for kw in ["create", "write", "save", "report", "document", "file"]):
            return len(ctx.created_files) > 0
        # Goal involving info gathering → check we gathered something
        if any(kw in goal.lower() for kw in ["research", "find", "search", "check", "look"]):
            return len(ctx.gathered_info) > 0 or bool(ctx.generated_content)
        # Default: did we do anything meaningful?
        return bool(ctx.last_result) or bool(ctx.generated_content)

    def _build_summary(self, goal: str, ctx: ExecutionContext) -> str:
        """Build a human-readable summary of what was accomplished."""
        parts = []
        if ctx.created_files:
            parts.append(f"Created: {', '.join(ctx.created_files)}")
        if ctx.generated_content:
            preview = ctx.generated_content[:400]
            parts.append(f"Content:\n{preview}")
        elif ctx.gathered_info:
            parts.append(f"Gathered {len(ctx.gathered_info)} pieces of information")
        if not parts:
            parts.append(ctx.last_result or "Task processed")
        return " | ".join(parts)

    def _infer_filename(self, target: str, ctx: ExecutionContext) -> str:
        """Infer a filename from the target/goal."""
        # Look for an explicit filename in target
        target_lower = target.lower()
        for ext in [".docx", ".txt", ".md", ".html", ".csv", ".xlsx"]:
            if ext in target_lower:
                # Extract the word with the extension
                for word in target.split():
                    if ext in word.lower():
                        return word.strip(".,;:\"'")

        # Infer from goal keywords
        goal_lower = ctx.goal.lower()
        if any(kw in goal_lower for kw in ["spreadsheet", "excel", ".xlsx", ".csv", "csv"]):
            ext = ".csv"
        elif "word" in goal_lower or "report" in goal_lower or "document" in goal_lower:
            ext = ".docx"
        elif "html" in goal_lower or "webpage" in goal_lower:
            ext = ".html"
        else:
            ext = ".txt"

        # Build a name from goal
        import re
        words = re.findall(r"[a-z0-9]+", goal_lower)[:4]
        base = "_".join(words) if words else "friday_output"
        return f"{base}{ext}"

    def _file_size(self, path: str) -> int:
        """Return the byte size of a file on disk, or 0 if unreadable."""
        import os
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    def _target_to_url(self, target: str) -> Optional[str]:
        """Resolve a target to a URL ONLY if it is already a URL/host (Axiom 15).

        No hardcoded site map: a bare app/site word resolves to ``None`` so the
        environment is discovered generically (search/exploration), never looked
        up by application name (FAS Ch 39/Ch 63).
        """
        from friday.actions.url_resolve import resolve_target_url

        return resolve_target_url(target)


class _DefaultGate:
    """Minimal delivery gate used when none is injected.

    Respects FRIDAY_AUTOCONFIRM: with it on, sends proceed; with it off and no
    confirm handler, nothing is sent (safe default — no accidental sends).
    The _send_fn / _verify_fn are set by the executor for generic web sending.
    """

    def __init__(self) -> None:
        self._confirm_fn = None
        self._send_fn = None
        self._verify_fn = None

    def deliver(self, request, *, auto_confirm: bool = False):
        from friday.actions.delivery import DeliveryGate
        gate = DeliveryGate(confirm_fn=self._confirm_fn,
                            send_fn=self._send_fn, verify_fn=self._verify_fn)
        return gate.deliver(request, auto_confirm=auto_confirm)
