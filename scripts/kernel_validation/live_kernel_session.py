"""M13 — live product-path session on the kernel execution path.

The parity harness runs both paths per scenario, but it does not run *the product*
with the kernel path as its execution default. This script closes that gap: it
builds the real FRIDAY API application with ``FRIDAY_USE_KERNEL_EXECUTION=1`` and
drives real goals through the real route
(``POST /api/command`` → ``FridayBridge.process`` → ``_execute_via_kernel`` →
``CognitiveKernel.submit_goal`` → ``GoalExecutionRuntime`` → ``Operator``).

Routing is not assumed, it is proven: kernel goal-lifecycle events are counted in
the kernel's own durable event log before and after each goal. A goal that took the
legacy branch would produce no ``goal.created`` there.

Nothing is fabricated: a goal that fails is reported as failed, and the script
changes no production default (the env flag is set for this process only and the
committed ``BridgeConfig.use_kernel_execution`` is left untouched).

Run it manually:

    python -m scripts.kernel_validation.live_kernel_session
    python -m scripts.kernel_validation.live_kernel_session --out docs/validation/LIVE_KERNEL_SESSION.md
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Real multi-step goals: each must classify above a simple action so the bridge
# takes its kernel branch. Deliberately generic (no site/app names, Axiom 15).
_GOALS = (
    "Research the latest stable Python release and write a short summary file.",
    "Find two facts about renewable energy and save them to a notes file.",
    "Research event-driven architecture and save a summary document to disk.",
)

_KERNEL_LIFECYCLE = ("goal.created", "goal.completed", "goal.failed")


def _default_store_path() -> Path:
    """The kernel's default durable event log (CognitiveKernel default store)."""
    return Path(os.path.expanduser("~/.friday/events/session.jsonl"))


def _read_events(path: Path) -> list:
    if not path.exists():
        return []
    events = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return events


def _parse_flag(name: str, default=None):
    for i, arg in enumerate(sys.argv):
        if arg == f"--{name}" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if arg.startswith(f"--{name}="):
            return arg.split("=", 1)[1]
    return default


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - not all streams support reconfigure
        pass

    print("=" * 64)
    print("  FRIDAY — live product-path session on the KERNEL execution path")
    print("=" * 64)

    if os.environ.get("FRIDAY_DRY_RUN") == "1":
        print("\n[abort] FRIDAY_DRY_RUN=1 — this session must be live to mean anything.")
        return 2

    # Process-local only: the committed BridgeConfig default is NOT changed.
    os.environ["FRIDAY_USE_KERNEL_EXECUTION"] = "1"
    os.environ.setdefault("REMOTE_API_KEY", "live-session-key")
    api_key = os.environ["REMOTE_API_KEY"]

    try:
        from fastapi.testclient import TestClient
    except ImportError as exc:
        print(f"\n[abort] fastapi/testclient unavailable: {exc}")
        return 2

    from friday.api.server import create_app

    print("\n[info] building the REAL application (kernel execution enabled)...")
    app = create_app()
    client = TestClient(app)

    store = _default_store_path()
    print(f"[info] kernel event log: {store}")

    rows = []
    for goal in _GOALS:
        before = _read_events(store)
        n_before = sum(1 for e in before if e.get("event_type") in _KERNEL_LIFECYCLE)

        print(f"\n    [goal] {goal[:70]} ... ", end="", flush=True)
        started = time.perf_counter()
        response = client.post(
            "/api/command", json={"text": goal}, headers={"X-API-Key": api_key}
        )
        elapsed = time.perf_counter() - started

        payload = response.json() if response.status_code == 200 else {}
        after = _read_events(store)
        new_lifecycle = [
            str(e.get("event_type"))
            for e in after[len(before):]
            if e.get("event_type") in _KERNEL_LIFECYCLE
        ]
        n_after = sum(1 for e in after if e.get("event_type") in _KERNEL_LIFECYCLE)
        via_kernel = n_after > n_before

        rows.append({
            "goal": goal,
            "http": response.status_code,
            "ok": bool(payload.get("ok")),
            "mode": payload.get("mode", ""),
            "complexity": payload.get("complexity", ""),
            "handled": payload.get("handled"),
            "seconds": round(elapsed, 1),
            "via_kernel": via_kernel,
            "kernel_events": new_lifecycle,
            "response": str(payload.get("text", ""))[:400],
            "error": str(payload.get("error", "") or ""),
        })
        print(
            f"http={response.status_code} ok={payload.get('ok')} "
            f"via_kernel={via_kernel} events={new_lifecycle} ({elapsed:.1f}s)",
            flush=True,
        )

    status = client.get("/api/status", headers={"X-API-Key": api_key})
    status_payload = status.json() if status.status_code == 200 else {}

    report = _render(rows, status_payload, store)
    print("\n" + report)

    out = _parse_flag("out")
    if out:
        try:
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_text(report, encoding="utf-8")
            print(f"[ok] session report written to {out}")
        except OSError as exc:
            print(f"[warn] could not write report to {out}: {exc}")

    routed = sum(1 for r in rows if r["via_kernel"])
    succeeded = sum(1 for r in rows if r["ok"])
    print(f"\n[summary] routed via kernel: {routed}/{len(rows)} | "
          f"succeeded: {succeeded}/{len(rows)}")
    # Non-zero exit when the kernel path was not actually exercised, so this
    # cannot be mistaken for evidence it did not produce.
    return 0 if routed == len(rows) else 1


def _render(rows, status_payload, store: Path) -> str:
    routed = sum(1 for r in rows if r["via_kernel"])
    succeeded = sum(1 for r in rows if r["ok"])
    lines = [
        "# Live Product-Path Session — Kernel Execution",
        "",
        "Real application (`friday.api.server.create_app`) built with",
        "`FRIDAY_USE_KERNEL_EXECUTION=1`, driven through the real route",
        "`POST /api/command`. Routing is proven by counting kernel goal-lifecycle",
        "events in the kernel's own durable log, not assumed.",
        "",
        f"- Kernel event log: `{store}`",
        f"- Goals run: **{len(rows)}**",
        f"- Routed via the kernel: **{routed}/{len(rows)}**",
        f"- Succeeded: **{succeeded}/{len(rows)}**",
        "",
        "| Goal | HTTP | ok | Mode | Cx | Via kernel | Kernel events | Seconds |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['goal'][:52]} | {r['http']} | {r['ok']} | {r['mode']} "
            f"| {r['complexity']} | {r['via_kernel']} | {', '.join(r['kernel_events'])} "
            f"| {r['seconds']} |"
        )
    lines.append("")
    for r in rows:
        lines.append(f"### {r['goal'][:70]}")
        lines.append("")
        lines.append(f"- via kernel: {r['via_kernel']} (events: {r['kernel_events']})")
        if r["response"]:
            lines.append(f"- response: {r['response']}")
        if r["error"]:
            lines.append(f"- error: {r['error']}")
        lines.append("")
    if status_payload:
        lines.append("## Application status after the session")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(status_payload, indent=2, default=str)[:2000])
        lines.append("```")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover - manual live entry point
    raise SystemExit(main())
