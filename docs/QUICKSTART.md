# FRIDAY — Quick Start

## Start the server

```bash
python start_friday.py
```

The API is at `http://127.0.0.1:8801` with interactive docs at `http://127.0.0.1:8801/docs`.

## Prerequisites

1. **Python 3.12+** with dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # for tests
   ```

2. **NVIDIA API key** in `.env`:
   ```
   NVIDIA_API_KEY=nvapi-...
   REMOTE_API_KEY=your-api-key-here
   ```

3. **Chrome with remote debugging** (optional, for real browser interaction):
   ```bash
   chrome --remote-debugging-port=9222
   ```
   Without this, FRIDAY falls back to fresh Chromium (no logins/extensions).

## Send a command

```bash
# Conversational (JARVIS mode — fast, ~1s)
curl -X POST http://127.0.0.1:8801/api/command \
  -H "X-API-Key: your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{"text": "What is quantum computing?"}'

# Action (FRIDAY mode — researches, creates files, ~60-100s)
curl -X POST http://127.0.0.1:8801/api/command \
  -H "X-API-Key: your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{"text": "Research AI agents and save a summary to a file"}'
```

## What happens

- **Questions** route to JARVIS mode: fast LLM response, ~1s
- **Actions** route to FRIDAY mode through the cognitive kernel:
  1. Requirements discovered (what must be true when done?)
  2. Capabilities planned (what steps achieve it?)
  3. Steps executed (search, navigate, generate, create files)
  4. Evidence verified (did real work actually happen?)
  5. Repairs attempted (if a requirement is unmet, fix only that)

## Architecture at a glance

```
User → POST /api/command → FridayBridge
  ├── JARVIS mode (questions) → LLM → response
  └── FRIDAY mode (actions) → CognitiveKernel
       → GoalExecutionRuntime → Operator
            → RequirementsDiscovery (LLM: what must be true?)
            → OperatorPlanner (LLM: what capabilities needed?)
            → GoalExecutor (real actions: search, navigate, generate, save)
            → EvidenceVerifier (did real work happen?)
            → RepairDiagnoser (fix only what's unmet)
       → goal.completed event → memory recorded
```

## Key features

- **Memory across goals** — the agent recalls prior context and records outcomes
- **Permission gate** — irreversible actions are withheld without approval
- **Kernel suspension** — in-flight goals can be interrupted and resumed
- **Crash recovery** — goal state survives a process kill via the durable event log
- **Per-model failover** — dead NVIDIA models are circuit-broken automatically
- **Evidence Law** — a requirement is satisfied ONLY by real artifacts, never by
  claiming work was done

## Rollback

Set `FRIDAY_USE_KERNEL_EXECUTION=0` in the environment to route goals through the
legacy Operator path (no kernel, no event log). Zero code change, instant.

## Run tests

```bash
python -m pytest tests -q              # full suite (~3 min)
python -m pytest tests/integration -q  # integration only (~2s)
```

## Run validation

```bash
# Parity (all 22 scenarios)
python -m scripts.kernel_validation.runner --cdp --timeout 300

# Capability benchmarks (9 benchmarks, 5 domains)
python -m scripts.kernel_validation.run_capability_benchmarks --no-cdp --browser

# Realistic interactions on your real Chrome
python -m scripts.kernel_validation.runner --cdp --timeout 300 --category realistic_interaction
```
