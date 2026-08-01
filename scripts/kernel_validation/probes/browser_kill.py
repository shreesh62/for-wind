"""M13 — the browser-kill fault probe (C3).

What this probe actuates, in order:

1. Refuse to proceed without a live controller: no controller, or a controller
   that never started, is ``skipped`` with the reason (never a pass).
2. Establish the "before" state from a **real** operation — ``navigate`` to a
   neutral ``about:blank`` plus a ``current_url`` read — alongside the
   controller's ``connection_mode``. A kill only proves something if the session
   demonstrably worked first.
3. Attribute the browser process. ``BrowserController`` keeps no PID of its own,
   so the only sound attribution is structural: the controller's Playwright
   instance owns a driver process (``node``), and when the controller *launched*
   the browser itself that browser is a **descendant of that driver**. The probe
   therefore kills descendants of *its own* controller's driver process and
   nothing else.
4. Kill those processes at the OS level (``psutil.Process.kill()``), not through
   the graceful ``BrowserController.stop()``, and confirm they are gone.
5. Attempt a further real operation and judge the response against reality.

Requirement 3.4 is the hard constraint: when ``connection_mode`` is ``"cdp"`` the
live browser is the **user's own Chrome**, which the controller merely attached
to. It is not ours to kill, so the probe returns ``skipped`` naming that instead
of killing a user process or faking a kill it did not perform.

Pass/fail rule (Requirement 3.2): pass when the post-kill operation either works
against a genuinely live re-established browser, or fails **observably** (falsy
result, error surfaced). Fail when it reports success while no attributable
browser process is alive — that would be fabricated evidence.

No application- or site-specific logic (the only URL used is ``about:blank``),
and no failure is swallowed: every unusable condition returns a verdict with the
reason.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from scripts.kernel_validation.faults import (
    RESULT_FAIL,
    RESULT_PASS,
    RESULT_SKIPPED,
    ProbeContext,
    ProbeVerdict,
    register_probe,
)

PROBE_ID = "browser_fail.reconnect"

# Neutral target: proves the session works without depending on any site.
_NEUTRAL_URL = "about:blank"

_KILL_WAIT_S = 10.0


def _driver_pid(controller: Any) -> Tuple[Optional[int], str]:
    """Return the PID of the Playwright driver this controller started.

    Reached through Playwright's own object graph
    (``Playwright -> Connection -> PipeTransport -> Process``). These are private
    attributes, so every hop is checked and a missing hop is reported rather than
    assumed: without this PID the probe cannot attribute a browser process to the
    controller, and must not kill anything.
    """
    playwright = getattr(controller, "_playwright", None)
    if playwright is None:
        return None, "controller exposes no Playwright instance"
    connection = getattr(playwright, "_connection", None)
    if connection is None:
        impl = getattr(playwright, "_impl_obj", None)
        connection = getattr(impl, "_connection", None)
    if connection is None:
        return None, "Playwright instance exposes no connection"
    transport = getattr(connection, "_transport", None)
    if transport is None:
        return None, "Playwright connection exposes no transport"
    proc = getattr(transport, "_proc", None)
    pid = getattr(proc, "pid", None)
    if not isinstance(pid, int):
        return None, "Playwright transport exposes no driver process pid"
    return pid, ""


def _launched_browser_procs(driver_pid: int) -> List[Any]:
    """Live descendants of ``driver_pid`` — the processes this controller launched.

    Descendancy is the attribution: a process under our own driver was started by
    our own controller. Nothing outside this tree is ever touched.
    """
    import psutil

    try:
        driver = psutil.Process(driver_pid)
    except psutil.NoSuchProcess:
        return []
    try:
        return [p for p in driver.children(recursive=True) if p.is_running()]
    except psutil.NoSuchProcess:
        return []


def _describe(procs: List[Any]) -> str:
    import psutil

    parts: List[str] = []
    for proc in procs:
        try:
            parts.append(f"{proc.pid}:{proc.name()}")
        except psutil.Error:
            parts.append(f"{proc.pid}:<exited>")
    return ", ".join(parts) if parts else "<none>"


class BrowserKillProbe:
    """Kills the controller's own browser process and proves the system notices."""

    probe_id = PROBE_ID

    def actuate(self, context: ProbeContext) -> ProbeVerdict:
        controller = context.browser_controller
        if controller is None:
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_SKIPPED,
                error="no browser controller available; nothing to kill",
            )
        if not getattr(controller, "available", False):
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_SKIPPED,
                error=(
                    "browser controller is not started/available "
                    f"(last_error={getattr(controller, 'last_error', None)!r})"
                ),
            )

        try:
            import psutil  # noqa: F401 — needed to attribute and confirm the kill
        except ImportError as exc:
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_FAIL,
                error=(
                    "cannot attribute or confirm an OS-level kill without psutil: "
                    f"{exc}"
                ),
            )

        mode = getattr(controller, "connection_mode", None)
        assertions: List[str] = [f"pre-kill connection_mode: {mode!r}"]

        pre = controller.navigate(_NEUTRAL_URL)
        if not pre.get("ok"):
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_SKIPPED,
                assertions=tuple(assertions),
                error=(
                    "pre-kill operation already failed, so no working session "
                    f"existed to kill: {pre.get('error', '')!r}"
                ),
            )
        pre_url = controller.current_url()
        assertions.append(
            f"pre-kill session worked: navigate({_NEUTRAL_URL}) ok, "
            f"current_url={pre_url!r}"
        )

        if mode == "cdp":
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_SKIPPED,
                assertions=tuple(assertions),
                error=(
                    "connection_mode is 'cdp': the live browser is the user's own "
                    "Chrome, which the controller attached to but did not launch; "
                    "killing it would violate Requirement 3.4, so no kill was "
                    "actuated"
                ),
            )

        driver_pid, why = _driver_pid(controller)
        if driver_pid is None:
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_FAIL,
                assertions=tuple(assertions),
                error=(
                    "no process attributable to this controller is reachable "
                    f"({why}); refusing to kill by image name or fake a kill"
                ),
            )

        targets = _launched_browser_procs(driver_pid)
        if not targets:
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_FAIL,
                assertions=tuple(assertions),
                error=(
                    f"controller driver pid {driver_pid} has no live descendant "
                    "process, so no browser process is attributable to this "
                    "controller; refusing to kill anything else"
                ),
            )
        assertions.append(
            f"attributed browser processes as descendants of this controller's own "
            f"driver pid {driver_pid}: {_describe(targets)}"
        )

        try:
            return self._kill_and_assert(controller, driver_pid, targets, assertions)
        finally:
            self._reap(targets)

    # ------------------------------------------------------------------ steps

    def _kill_and_assert(
        self,
        controller: Any,
        driver_pid: int,
        targets: List[Any],
        assertions: List[str],
    ) -> ProbeVerdict:
        import psutil

        killed_pids = [p.pid for p in targets]
        for proc in targets:
            try:
                proc.kill()
            except psutil.NoSuchProcess:
                # Killing the root browser process takes its renderers with it;
                # a target that is already gone is still gone. Recorded below.
                continue
        gone, alive = psutil.wait_procs(targets, timeout=_KILL_WAIT_S)
        if alive:
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_FAIL,
                assertions=tuple(assertions),
                error=(
                    f"OS-level kill did not terminate {_describe(alive)} within "
                    f"{_KILL_WAIT_S:.0f}s"
                ),
            )
        assertions.append(
            f"killed pids {killed_pids} at OS level (psutil kill, not "
            f"BrowserController.stop()); all {len(gone)} confirmed terminated"
        )

        post = controller.navigate(_NEUTRAL_URL)
        post_ok = bool(post.get("ok"))
        post_error = str(post.get("error", ""))
        live_after = _launched_browser_procs(driver_pid)
        assertions.append(
            f"post-kill attributable browser processes: {_describe(live_after)}"
        )
        assertions.append(
            f"post-kill navigate({_NEUTRAL_URL}) returned ok={post_ok}"
            + (f", error={post_error!r}" if post_error else "")
        )

        if post_ok:
            if not live_after:
                return ProbeVerdict(
                    probe_id=PROBE_ID, result=RESULT_FAIL,
                    assertions=tuple(assertions),
                    error=(
                        "post-kill operation reported success while no attributable "
                        "browser process was alive — fabricated evidence"
                    ),
                )
            assertions.append(
                "controller re-established a working session: the operation "
                "succeeded against a live re-launched browser process"
            )
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_PASS, assertions=tuple(assertions)
            )

        last_error = getattr(controller, "last_error", None)
        assertions.append(
            "failure was reported observably, not fabricated as success: falsy "
            f"result with error={post_error or '<empty>'!r} "
            f"(controller.last_error={last_error!r})"
        )
        return ProbeVerdict(
            probe_id=PROBE_ID, result=RESULT_PASS, assertions=tuple(assertions)
        )

    def _reap(self, targets: List[Any]) -> None:
        """Leave no browser process this probe touched still running."""
        import psutil

        for proc in targets:
            try:
                if proc.is_running():
                    proc.kill()
            except psutil.NoSuchProcess:
                continue
        psutil.wait_procs(targets, timeout=_KILL_WAIT_S)


register_probe(BrowserKillProbe())
