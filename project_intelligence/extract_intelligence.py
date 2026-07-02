
#!/usr/bin/env python3
"""Repository Intelligence Extraction (Graphify-ready).

This script generates a long-lived knowledge package under ./project_intelligence
for handoff to another AI agent.

Constraints:
- Standard library only.
- Do not copy secret values; only index .env keys.
- Prefer over-capture and explicit nodes/edges for Graphify ingestion.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any, Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO_ROOT / "project_intelligence"
GRAPH_ROOT = OUT_ROOT / "GRAPHIFY_EXPORT"

DEFAULT_EXCLUDE_DIR_NAMES = {
    ".git",
    ".venv",
    ".venv312",
    "friday_env",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    "tts_output",
    "logs",
    "screenshots",
}

COPY_DIR_RE = re.compile(r" - Copy( \(\d+\))?$")

ENV_GET_RE = re.compile(
    r"""os\.getenv\(\s*[\"'](?P<key>[A-Za-z_][A-Za-z0-9_]*)[\"']""",
    re.MULTILINE,
)

FILE_IO_RE = re.compile(
    r"""(?:open\(|Path\([\"']|Path\().{0,80}?(?P<path>memory/[^\"' )]+|logs/[^\"' )]+|screenshots/[^\"' )]+)""",
    re.MULTILINE,
)


def utc_now_iso() -> str:
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def safe_read_text(path: Path, limit_bytes: int = 2_000_000) -> str:
    try:
        data = path.read_bytes()
    except Exception:
        return ""
    if len(data) > limit_bytes:
        data = data[:limit_bytes]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", "replace")


def iter_repo_files(
    root: Path,
    *,
    exclude_dir_names: set[str] | None = None,
    include_copies: bool = False,
) -> Iterable[Path]:
    exclude = set(exclude_dir_names or DEFAULT_EXCLUDE_DIR_NAMES)
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        rel_parts = p.relative_to(root).parts
        if any(part in exclude for part in rel_parts):
            continue
        if not include_copies:
            if any(COPY_DIR_RE.search(part or "") for part in rel_parts):
                continue
        yield p


@dataclasses.dataclass
class PySymbol:
    kind: str  # class | function
    name: str
    lineno: int
    doc: str | None = None


@dataclasses.dataclass
class PyFileInfo:
    path: str
    module: str | None
    imports: list[str]
    symbols: list[PySymbol]
    env_keys: list[str]
    io_paths: list[str]
    doc: str | None


def path_to_module(rel_path: Path) -> Optional[str]:
    if rel_path.suffix != ".py":
        return None
    parts = list(rel_path.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    if not parts:
        return None
    return ".".join(parts)


def parse_python_file(root: Path, path: Path) -> PyFileInfo:
    rel = path.relative_to(root).as_posix()
    module = path_to_module(path.relative_to(root))
    text = safe_read_text(path)

    doc = None
    imports: list[str] = []
    symbols: list[PySymbol] = []
    env_keys = sorted({m.group("key") for m in ENV_GET_RE.finditer(text)})
    io_paths = sorted({m.group("path") for m in FILE_IO_RE.finditer(text) if m.group("path")})

    try:
        tree = ast.parse(text, filename=rel)
        doc = ast.get_docstring(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
            elif isinstance(node, ast.ClassDef):
                symbols.append(
                    PySymbol(
                        kind="class",
                        name=node.name,
                        lineno=getattr(node, "lineno", 1),
                        doc=ast.get_docstring(node),
                    )
                )
            elif isinstance(node, ast.FunctionDef):
                symbols.append(
                    PySymbol(
                        kind="function",
                        name=node.name,
                        lineno=getattr(node, "lineno", 1),
                        doc=ast.get_docstring(node),
                    )
                )
    except Exception:
        pass

    imports = sorted({i for i in imports if i})
    symbols = sorted(symbols, key=lambda s: (s.kind, s.name, s.lineno))

    return PyFileInfo(
        path=rel,
        module=module,
        imports=imports,
        symbols=symbols,
        env_keys=env_keys,
        io_paths=io_paths,
        doc=doc.splitlines()[0].strip() if doc else None,
    )


def read_env_keys(env_path: Path) -> list[str]:
    if not env_path.exists():
        return []
    keys: list[str] = []
    for line in safe_read_text(env_path).splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k = s.split("=", 1)[0].strip()
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k):
            keys.append(k)
    return sorted(set(keys))


def load_json(path: Path) -> dict | list | None:
    try:
        return json.loads(safe_read_text(path))
    except Exception:
        return None


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=False), encoding="utf-8")


def risk_level_for_path(rel_path: str) -> str:
    p = rel_path.replace("\\", "/")
    if p.startswith("security/"):
        return "High"
    if p.startswith("automation/") or p.startswith("awareness/") or p.startswith("core/"):
        return "High"
    if p.startswith("server/") or p.startswith("remote/"):
        return "Medium-High"
    if p.startswith("desktop_app/") or p.startswith("mobile_dashboard/"):
        return "Medium"
    if p.startswith("tests/") or p.startswith("scripts/"):
        return "Low-Medium"
    if p.endswith(".md") or p.endswith(".json") or p.endswith(".ini"):
        return "Low-Medium"
    return "Unknown"


def status_for_path(rel_path: str) -> str:
    p = rel_path.replace("\\", "/")
    if " - Copy" in p:
        return "Deprecated"
    if p.endswith("_test.py") or p.startswith("tests/") or p.startswith("e2e/") or p.endswith(".spec"):
        return "Experimental"
    if p.endswith(".md") and ("COMPLETE" in p.upper() or "README" in p.upper()):
        return "Working"
    return "Unknown"


def mk_node(node_id: str, ntype: str, name: str, **props: Any) -> dict:
    d = {"id": node_id, "type": ntype, "name": name}
    if props:
        d["props"] = props
    return d


def mk_edge(edge_id: str, src: str, dst: str, rtype: str, **meta: Any) -> dict:
    e = {"id": edge_id, "from": src, "to": dst, "type": rtype}
    if meta:
        e["metadata"] = meta
    return e


def derive_features(py_infos: list[PyFileInfo], env_keys: list[str]) -> list[dict]:
    features: dict[str, dict] = {}

    def add_feature(
        name: str,
        status: str,
        deps: list[str],
        notes: str,
        completion_pct: int,
        stability: str,
    ) -> None:
        if name in features:
            features[name]["dependencies"] = sorted(set(features[name]["dependencies"] + deps))
            if notes and notes not in features[name]["notes"]:
                features[name]["notes"] += " | " + notes
            order = ["Working", "Partial", "Experimental", "Planned", "Deprecated", "Broken", "Unknown"]
            if order.index(status) > order.index(features[name]["status"]):
                features[name]["status"] = status
            features[name]["completion_pct"] = max(features[name]["completion_pct"], completion_pct)
            return
        features[name] = {
            "feature": name,
            "status": status,
            "completion_pct": completion_pct,
            "stability": stability,
            "dependencies": deps,
            "notes": notes,
        }

    if any(k.startswith("PORCUPINE") for k in env_keys):
        add_feature(
            "Wake Word (Porcupine)",
            "Working",
            ["pvporcupine", "PyAudio", "wake_words/*.ppn", ".env:PORCUPINE_ACCESS_KEY"],
            "Wake word optional via DISABLE_WAKE_WORD; falls back when deps missing.",
            80,
            "Medium",
        )
    if "GROQ_API_KEY" in env_keys:
        add_feature(
            "LLM Reasoning via Groq",
            "Working",
            ["groq", ".env:GROQ_API_KEY", "groq_llm.py"],
            "Used as llm_callable for assistant reasoning and automation planning.",
            70,
            "Medium",
        )
    if "REMOTE_API_KEY" in env_keys:
        add_feature(
            "Remote Control API (FastAPI)",
            "Working",
            ["fastapi", "uvicorn", "server/app.py", ".env:REMOTE_API_KEY"],
            "API-key protected endpoints plus static dashboard.",
            75,
            "Medium",
        )

    for info in py_infos:
        p = info.path
        if p.startswith("automation/"):
            add_feature(
                "Automation: Browser + Desktop",
                "Working",
                ["playwright", "pyautogui", "pywinauto", "uiautomation", "automation/*"],
                "AutomationServices facade; planner + cognitive loop exist.",
                70,
                "Medium-High",
            )
        if p == "automation/cognitive_loop.py":
            add_feature(
                "Cognitive Loop (Perceive-Plan-Act-Verify-Repair)",
                "Partial",
                [
                    "automation/cognitive_loop.py",
                    "awareness/world_state.py",
                    "core/self_repair.py",
                    "memory/ui_memory.json",
                ],
                "Phase-coded; integrated behind COGNITIVE_MODE=1.",
                65,
                "Medium",
            )
        if "pytesseract" in info.imports:
            add_feature(
                "OCR (Tesseract)",
                "Experimental",
                ["pytesseract", "pillow", "awareness/*", "ocr_test*.py"],
                "OCR experiments exist; unclear if integrated into main flow.",
                35,
                "Low-Medium",
            )
        if p.startswith("security/"):
            add_feature(
                "Credential Vault + Training Mode",
                "Partial",
                ["security/*", "core/training_controller.py"],
                "DPAPI vault; training mode mentioned in COGNITIVE_SYSTEM_COMPLETE.md.",
                60,
                "Medium",
            )
        if p.startswith("ui/") or p.startswith("desktop_app/"):
            add_feature(
                "Desktop UI (Electron + WebSocket IPC)",
                "Working",
                ["desktop_app/*", "ui/*", "websockets"],
                "Electron bundles ui/ as extraResources; IPC server in Python.",
                70,
                "Medium",
            )
        if p.startswith("mobile_dashboard/"):
            add_feature(
                "Mobile Dashboard (React/Vite)",
                "Working",
                ["mobile_dashboard/*", "server/app.py"],
                "Vite dev server; talks to remote server for status/commands.",
                60,
                "Medium",
            )

    return sorted(features.values(), key=lambda x: x["feature"].lower())


def build_graphs(
    *,
    py_infos: list[PyFileInfo],
    env_keys: list[str],
    top_folders: list[str],
    all_files: list[str],
    features: list[dict],
) -> dict[str, dict]:
    # Graphify schema: {graph_name, metadata, nodes[], edges[]}
    graphs: dict[str, dict] = {}

    repo_node = mk_node("repo:root", "repository", REPO_ROOT.name, path=str(REPO_ROOT))

    folder_nodes = []
    folder_edges = []
    for folder in top_folders:
        fid = f"folder:{folder}"
        folder_nodes.append(mk_node(fid, "folder", folder))
        folder_edges.append(mk_edge(f"edge:repo_contains:{folder}", "repo:root", fid, "contains"))

    file_nodes = []
    file_edges = []
    for f in all_files:
        file_nodes.append(
            mk_node(
                f"file:{f}",
                "file",
                Path(f).name,
                path=f,
                status=status_for_path(f),
                risk=risk_level_for_path(f),
            )
        )
        top = f.split("/", 1)[0] if "/" in f else "(root)"
        if top == "(root)":
            file_edges.append(mk_edge(f"edge:repo_contains_file:{f}", "repo:root", f"file:{f}", "contains"))
        else:
            file_edges.append(mk_edge(f"edge:folder_contains_file:{top}:{f}", f"folder:{top}", f"file:{f}", "contains"))

    env_nodes = [mk_node(f"env:{k}", "env_var", k) for k in env_keys]
    py_nodes = []
    py_edges = []
    for info in py_infos:
        mod_id = f"py_module:{info.module}" if info.module else f"py_module_path:{info.path}"
        py_nodes.append(mk_node(mod_id, "py_module", info.module or info.path, path=info.path, doc=info.doc or ""))
        py_edges.append(mk_edge(f"edge:file_defines_module:{info.path}", f"file:{info.path}", mod_id, "defines_module"))
        for imp in info.imports:
            py_nodes.append(mk_node(f"py_import:{imp}", "py_import", imp))
            py_edges.append(mk_edge(f"edge:module_imports:{info.path}:{imp}", mod_id, f"py_import:{imp}", "imports", raw=imp))
        for sym in info.symbols:
            sid = f"{sym.kind}:{info.path}:{sym.name}"
            py_nodes.append(mk_node(sid, sym.kind, sym.name, file=info.path, lineno=sym.lineno, doc=sym.doc or ""))
            py_edges.append(mk_edge(f"edge:module_defines_symbol:{sid}", mod_id, sid, "defines", lineno=sym.lineno))
        for k in info.env_keys:
            py_edges.append(mk_edge(f"edge:module_uses_env:{info.path}:{k}", mod_id, f"env:{k}", "uses_env"))
        for ip in info.io_paths:
            py_nodes.append(mk_node(f"path:{ip}", "path", ip))
            py_edges.append(mk_edge(f"edge:module_io:{info.path}:{ip}", mod_id, f"path:{ip}", "reads_or_writes_path"))

    feature_nodes = []
    feature_edges = []
    dep_nodes = []
    for feat in features:
        fid = f"feature:{feat['feature']}"
        feature_nodes.append(mk_node(fid, "feature", feat["feature"], **feat))
        for dep in feat.get("dependencies", []):
            dep_nodes.append(mk_node(f"dep:{dep}", "dependency", dep))
            feature_edges.append(mk_edge(f"edge:feature_dep:{feat['feature']}:{dep}", fid, f"dep:{dep}", "depends_on", raw=dep))
    dep_nodes = list({n["id"]: n for n in dep_nodes}.values())

    graphs["JARVIS_MASTER_INTELLIGENCE_GRAPH1"] = {
        "graph_name": "JARVIS_MASTER_INTELLIGENCE_GRAPH1",
        "metadata": {"generated_at": utc_now_iso(), "repo_root": str(REPO_ROOT)},
        "nodes": [repo_node, *folder_nodes, *file_nodes, *env_nodes, *py_nodes, *feature_nodes, *dep_nodes],
        "edges": [*folder_edges, *file_edges, *py_edges, *feature_edges],
    }

    return graphs


def build_additional_graphs(
    *,
    py_infos: list[PyFileInfo],
    env_keys: list[str],
    all_files: list[str],
    features: list[dict],
) -> dict[str, dict]:
    repo_node = mk_node("repo:root", "repository", REPO_ROOT.name, path=str(REPO_ROOT))

    # Pre-build a file node list for cross-links.
    file_nodes = [
        mk_node(
            f"file:{f}",
            "file",
            Path(f).name,
            path=f,
            status=status_for_path(f),
            risk=risk_level_for_path(f),
        )
        for f in all_files
    ]

    graphs: dict[str, dict] = {}

    # ARCHITECTURE graph: high-level components.
    arch_nodes = [repo_node]
    arch_edges = []
    components = [
        ("component:entrypoint", "Entrypoint (main.py)", {"file": "main.py"}),
        ("component:assistant_orchestrator", "AssistantOrchestrator", {"file": "core/assistant.py"}),
        ("component:capability_dispatch", "Capability Dispatch", {"file": "core/capability_dispatcher.py"}),
        ("component:automation_services", "AutomationServices", {"file": "automation/services.py"}),
        ("component:cognitive_loop", "CognitiveLoop", {"file": "automation/cognitive_loop.py"}),
        ("component:awareness", "Awareness/Perception", {"folder": "awareness/"}),
        ("component:memory", "Memory", {"folder": "memory/"}),
        ("component:security", "Security", {"folder": "security/"}),
        ("component:remote_server", "RemoteServer (FastAPI)", {"folder": "server/"}),
        ("component:ui_ipc", "UI IPC/WebSocket", {"folder": "ui/"}),
        ("component:desktop_app", "Desktop Shell (Electron)", {"folder": "desktop_app/"}),
        ("component:mobile_dashboard", "Mobile Dashboard", {"folder": "mobile_dashboard/"}),
        ("component:plugins", "Plugins", {"folder": "plugins/"}),
        ("component:services", "External Services", {"folder": "services/"}),
    ]
    for cid, name, props in components:
        arch_nodes.append(mk_node(cid, "component", name, **props))
        arch_edges.append(mk_edge(f"edge:repo_has_component:{cid}", "repo:root", cid, "has_component"))

    def link(a: str, b: str, rel: str, note: str) -> None:
        arch_edges.append(mk_edge(f"edge:arch:{a}:{rel}:{b}", a, b, rel, note=note))

    link("component:entrypoint", "component:assistant_orchestrator", "initializes", "JarvisAssistant builds AssistantOrchestrator")
    link("component:assistant_orchestrator", "component:capability_dispatch", "uses", "Routes commands through dispatcher registry")
    link("component:assistant_orchestrator", "component:automation_services", "uses", "Planner/cognitive loop call into automation services")
    link("component:assistant_orchestrator", "component:cognitive_loop", "optional_uses", "Enabled when COGNITIVE_MODE=1")
    link("component:assistant_orchestrator", "component:awareness", "uses", "Uses StateCache snapshots / redaction")
    link("component:assistant_orchestrator", "component:memory", "uses", "MemoryController stores turns")
    link("component:remote_server", "component:assistant_orchestrator", "controls", "Remote /execute forwards text commands")
    link("component:desktop_app", "component:ui_ipc", "bundles", "Electron bundles ui/ via extraResources")
    link("component:mobile_dashboard", "component:remote_server", "calls", "HTTP polling + command submission")
    link("component:plugins", "component:capability_dispatch", "extends", "PluginLoader registers handlers")

    graphs["JARVIS_ARCHITECTURE_GRAPH1"] = {
        "graph_name": "JARVIS_ARCHITECTURE_GRAPH1",
        "metadata": {"generated_at": utc_now_iso(), "repo_root": str(REPO_ROOT)},
        "nodes": arch_nodes,
        "edges": arch_edges,
    }

    # DEPENDENCY graph: requirements + JS deps + import edges.
    dep_nodes = [repo_node]
    dep_edges = []

    for req_file in ("requirements.txt", "requirements-dev.txt", "requirements-312.txt"):
        rp = REPO_ROOT / req_file
        if not rp.exists():
            continue
        for line in safe_read_text(rp).splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            rid = f"py_req:{s}"
            dep_nodes.append(mk_node(rid, "python_requirement", s, file=req_file))
            dep_edges.append(mk_edge(f"edge:req:{req_file}:{s}", "repo:root", rid, "declares_dependency"))

    for pkg_path in (
        REPO_ROOT / "package.json",
        REPO_ROOT / "desktop_app" / "package.json",
        REPO_ROOT / "mobile_dashboard" / "package.json",
    ):
        if not pkg_path.exists():
            continue
        data = load_json(pkg_path)
        if not isinstance(data, dict):
            continue
        for scope in ("dependencies", "devDependencies"):
            deps = data.get(scope, {})
            if not isinstance(deps, dict):
                continue
            for name, ver in deps.items():
                nid = f"js_dep:{name}"
                dep_nodes.append(mk_node(nid, "js_dependency", name, version=str(ver), scope=scope, file=str(pkg_path.relative_to(REPO_ROOT)).replace("\\", "/")))
                dep_edges.append(mk_edge(f"edge:jsdep:{pkg_path.name}:{scope}:{name}", "repo:root", nid, "declares_dependency"))

    for info in py_infos:
        if not info.module:
            continue
        src = f"py_module:{info.module}"
        dep_nodes.append(mk_node(src, "py_module", info.module, path=info.path))
        for imp in info.imports:
            dep_nodes.append(mk_node(f"py_import:{imp}", "py_import", imp))
            dep_edges.append(mk_edge(f"edge:py_import:{info.module}:{imp}", src, f"py_import:{imp}", "imports"))

    dep_nodes = list({n["id"]: n for n in dep_nodes}.values())

    graphs["JARVIS_DEPENDENCY_GRAPH1"] = {
        "graph_name": "JARVIS_DEPENDENCY_GRAPH1",
        "metadata": {"generated_at": utc_now_iso(), "repo_root": str(REPO_ROOT)},
        "nodes": dep_nodes,
        "edges": dep_edges,
    }

    # RUNTIME FLOW graph: canonical flow steps.
    rt_nodes = [repo_node]
    rt_edges = []
    steps = [
        ("runtime:startup", "Startup"),
        ("runtime:load_env", "Load settings (.env -> config.get_settings)"),
        ("runtime:init_awareness", "Init awareness controller/monitors"),
        ("runtime:init_automation", "Init AutomationServices + planner/cognitive loop"),
        ("runtime:init_ui", "Init UI IPC/WebSocket server"),
        ("runtime:init_remote", "Init RemoteServer (FastAPI)"),
        ("runtime:voice_loop", "Wake-word + mic -> command loop"),
        ("runtime:reasoning", "Reason about command"),
        ("runtime:dispatch", "Dispatch capability / automation"),
        ("runtime:automation_execute", "Perform automation"),
        ("runtime:verify", "Verify outcome via awareness snapshots"),
        ("runtime:memory_write", "Write memory + telemetry"),
        ("runtime:tts", "TTS output"),
        ("runtime:shutdown", "Shutdown services"),
    ]
    for nid, title in steps:
        rt_nodes.append(mk_node(nid, "runtime_step", title))
        rt_edges.append(mk_edge(f"edge:rt_has:{nid}", "repo:root", nid, "has_runtime_step"))
    for (a, _), (b, _) in zip(steps, steps[1:]):
        rt_edges.append(mk_edge(f"edge:rt_next:{a}:{b}", a, b, "next"))

    rt_nodes.append(mk_node("runtime:remote_execute", "runtime_step", "Remote /execute -> process_command"))
    rt_edges.append(mk_edge("edge:rt_alt:remote", "runtime:init_remote", "runtime:remote_execute", "enables"))
    rt_edges.append(mk_edge("edge:rt_alt:remote2", "runtime:remote_execute", "runtime:reasoning", "calls"))

    graphs["JARVIS_RUNTIME_FLOW_GRAPH1"] = {
        "graph_name": "JARVIS_RUNTIME_FLOW_GRAPH1",
        "metadata": {"generated_at": utc_now_iso(), "repo_root": str(REPO_ROOT), "confidence": "Medium"},
        "nodes": rt_nodes,
        "edges": rt_edges,
    }

    # FEATURE STATUS graph
    f_nodes = []
    f_edges = []
    d_nodes = []
    for feat in features:
        fid = f"feature:{feat['feature']}"
        f_nodes.append(mk_node(fid, "feature", feat["feature"], **feat))
        for dep in feat.get("dependencies", []):
            d_nodes.append(mk_node(f"dep:{dep}", "dependency", dep))
            f_edges.append(mk_edge(f"edge:feature_dep:{feat['feature']}:{dep}", fid, f"dep:{dep}", "depends_on"))
    d_nodes = list({n["id"]: n for n in d_nodes}.values())

    graphs["JARVIS_FEATURE_STATUS_GRAPH1"] = {
        "graph_name": "JARVIS_FEATURE_STATUS_GRAPH1",
        "metadata": {"generated_at": utc_now_iso(), "repo_root": str(REPO_ROOT)},
        "nodes": [*f_nodes, *d_nodes],
        "edges": f_edges,
    }

    # FAILURE graph (heuristic)
    failures = [
        {
            "id": "failure:phase7_integration",
            "title": "Cognitive routing integration drift",
            "goal": "Route all automation through cognitive loop (single source of truth)",
            "cause": "Phase-coded integration in progress; strict no-fallback may be risky",
            "state": "Partial",
            "recommendation": "Add reality-check harness; gate cognitive strictness behind env flags",
            "files": ["core/assistant.py", "automation/cognitive_loop.py"],
        },
        {
            "id": "failure:ocr_integration",
            "title": "OCR/vision not fully integrated",
            "goal": "Use OCR/ROI/change detection as perception signals",
            "cause": "Standalone test scripts; unclear integration into WorldState",
            "state": "Experimental",
            "recommendation": "Define vision contract; wire into awareness snapshot",
            "files": ["ocr_test.py", "ocr_roi_test.py", "roi_change_ocr.py"],
        },
    ]
    fail_nodes = [repo_node, *file_nodes]
    fail_edges = []
    for f in failures:
        fail_nodes.append(mk_node(f["id"], "failure", f.get("title") or f["id"], **f))
        fail_edges.append(mk_edge(f"edge:repo_has_failure:{f['id']}", "repo:root", f["id"], "has_failure"))
        for fp in f.get("files", []):
            fail_edges.append(mk_edge(f"edge:failure_affects:{f['id']}:{fp}", f["id"], f"file:{fp}", "affects"))

    graphs["JARVIS_FAILURE_GRAPH1"] = {
        "graph_name": "JARVIS_FAILURE_GRAPH1",
        "metadata": {"generated_at": utc_now_iso(), "repo_root": str(REPO_ROOT), "confidence": "Low-Medium"},
        "nodes": list({n["id"]: n for n in fail_nodes}.values()),
        "edges": fail_edges,
    }

    # ROADMAP graph: from Cognitive System doc phases (7-13).
    rm_nodes = [repo_node, *file_nodes]
    rm_edges = []
    phases = [
        ("roadmap:phase7", "Phase 7 - cognitive routing"),
        ("roadmap:phase8", "Phase 8 - force real perception after actions"),
        ("roadmap:phase9", "Phase 9 - persistent UI memory"),
        ("roadmap:phase10", "Phase 10 - credential-aware element resolution"),
        ("roadmap:phase11", "Phase 11 - kill illusion paths"),
        ("roadmap:phase12", "Phase 12 - reality test harness"),
        ("roadmap:phase13", "Phase 13 - cognitive-only strict mode"),
    ]
    for nid, title in phases:
        rm_nodes.append(mk_node(nid, "roadmap_item", title))
        rm_edges.append(mk_edge(f"edge:repo_has_roadmap:{nid}", "repo:root", nid, "has_roadmap_item"))
    for (a, _), (b, _) in zip(phases, phases[1:]):
        rm_edges.append(mk_edge(f"edge:roadmap_order:{a}:{b}", a, b, "suggested_order"))
    rm_edges.append(mk_edge("edge:roadmap_doc", "roadmap:phase7", "file:COGNITIVE_SYSTEM_COMPLETE.md", "documented_in"))

    graphs["JARVIS_ROADMAP_GRAPH1"] = {
        "graph_name": "JARVIS_ROADMAP_GRAPH1",
        "metadata": {"generated_at": utc_now_iso(), "repo_root": str(REPO_ROOT), "confidence": "Medium"},
        "nodes": list({n["id"]: n for n in rm_nodes}.values()),
        "edges": rm_edges,
    }

    # FRIDAY pivot graph: inferred layers.
    fr_nodes = [repo_node]
    fr_edges = []
    layers = [
        ("friday:vision", "Vision Layer"),
        ("friday:reasoning", "Reasoning Layer"),
        ("friday:action", "Action Layer"),
        ("friday:feedback", "Feedback Layer"),
    ]
    for nid, title in layers:
        fr_nodes.append(mk_node(nid, "layer", title))
        fr_edges.append(mk_edge(f"edge:repo_has_layer:{nid}", "repo:root", nid, "has_layer"))

    evidence = [
        ("friday_evidence:screen_capture", "Screen capture (PIL.ImageGrab)", "automation/services.py"),
        ("friday_evidence:uia", "UI Automation monitor (UIA)", "awareness/windows/*"),
        ("friday_evidence:ocr", "OCR + ROI change tests", "ocr_test.py / roi_change_ocr.py"),
        ("friday_evidence:cognitive_loop", "Closed-loop control", "automation/cognitive_loop.py"),
        ("friday_evidence:verification", "Semantic verification", "automation/verification.py"),
    ]
    for nid, title, file_hint in evidence:
        fr_nodes.append(mk_node(nid, "evidence", title, file_hint=file_hint))
        fr_edges.append(mk_edge(f"edge:repo_has_evidence:{nid}", "repo:root", nid, "has_evidence"))

    fr_edges.append(mk_edge("edge:fr_assign:vision_screen", "friday:vision", "friday_evidence:screen_capture", "implemented_by"))
    fr_edges.append(mk_edge("edge:fr_assign:vision_uia", "friday:vision", "friday_evidence:uia", "implemented_by"))
    fr_edges.append(mk_edge("edge:fr_assign:vision_ocr", "friday:vision", "friday_evidence:ocr", "experimental"))
    fr_edges.append(mk_edge("edge:fr_assign:reasoning_cog", "friday:reasoning", "friday_evidence:cognitive_loop", "implemented_by"))
    fr_edges.append(mk_edge("edge:fr_assign:feedback_verify", "friday:feedback", "friday_evidence:verification", "implemented_by"))

    graphs["JARVIS_FRIDAY_PIVOT_GRAPH1"] = {
        "graph_name": "JARVIS_FRIDAY_PIVOT_GRAPH1",
        "metadata": {"generated_at": utc_now_iso(), "repo_root": str(REPO_ROOT), "confidence": "Low"},
        "nodes": fr_nodes,
        "edges": fr_edges,
    }

    return graphs


def run() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    GRAPH_ROOT.mkdir(parents=True, exist_ok=True)

    files = sorted(iter_repo_files(REPO_ROOT), key=lambda p: str(p).lower())
    rel_files = [p.relative_to(REPO_ROOT).as_posix() for p in files]

    py_infos: list[PyFileInfo] = []
    for p in files:
        if p.suffix.lower() == ".py":
            py_infos.append(parse_python_file(REPO_ROOT, p))

    env_keys = sorted(set(read_env_keys(REPO_ROOT / ".env.example") + read_env_keys(REPO_ROOT / ".env")))

    top_folders = sorted({rf.split("/", 1)[0] for rf in rel_files if "/" in rf})

    features = derive_features(py_infos, env_keys)

    graphs = build_graphs(py_infos=py_infos, env_keys=env_keys, top_folders=top_folders, all_files=rel_files, features=features)
    graphs.update(build_additional_graphs(py_infos=py_infos, env_keys=env_keys, all_files=rel_files, features=features))

    for gname, graph in graphs.items():
        write_json(GRAPH_ROOT / f"{gname}.json", graph)

    # Machine-readable indexes
    write_json(
        OUT_ROOT / "repo_index.json",
        {
            "generated_at": utc_now_iso(),
            "repo_root": str(REPO_ROOT),
            "file_count_excluding_heavy_dirs": len(rel_files),
            "python_file_count": sum(1 for f in rel_files if f.endswith(".py")),
            "env_keys_redacted": env_keys,
            "top_level_folders": top_folders,
            "graphs": sorted(graphs.keys()),
        },
    )

    py_index = []
    for info in py_infos:
        py_index.append(
            {
                "path": info.path,
                "module": info.module,
                "doc": info.doc,
                "imports": info.imports,
                "env_keys": info.env_keys,
                "io_paths": info.io_paths,
                "symbols": [dataclasses.asdict(s) for s in info.symbols],
            }
        )
    write_json(OUT_ROOT / "python_index.json", py_index)

    write_text(
        OUT_ROOT / "EXTRACTION_RUN.md",
        "\n".join(
            [
                "# Extraction Run",
                "",
                f"- generated_at_utc: {utc_now_iso()}",
                f"- repo_root: {REPO_ROOT}",
                f"- file_count (excluded heavy dirs): {len(rel_files)}",
                f"- python_files: {sum(1 for f in rel_files if f.endswith('.py'))}",
                f"- graphs: {', '.join(sorted(graphs.keys()))}",
                "",
                "Notes:",
                "- This is an automated extraction pass.",
                "- .env values are NOT copied; only keys are indexed.",
                "- Heavy directories excluded by default: " + ", ".join(sorted(DEFAULT_EXCLUDE_DIR_NAMES)),
                "",
            ]
        )
        + "\n",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
