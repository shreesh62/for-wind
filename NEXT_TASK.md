# Next Task

## Direction: General Operator (ADR-021) — Requirements, Not Workflows

### Litmus test for everything:
"Does this make FRIDAY better at completing ARBITRARY goals?"

### Priority 1: Universal Action Layer
Build `friday/actions/primitives.py` with atomic actions that ALL higher
capabilities compose from:
- click(), double_click(), right_click()
- type_text(), press_key(), press_hotkey()
- scroll(), drag()
- switch_window(), wait_for(), observe(), verify()

Every capability (browser click, desktop click) becomes a composition of
these primitives + the right environment adapter. This eliminates
environment-specific action code duplication.

### Priority 2: Wire Requirements Discovery into Execution
Currently RequirementsDiscovery exists but isn't driving execution.
Wire it so:
1. Goal → discover requirements
2. Plan capabilities to satisfy each requirement
3. After execution → check each requirement satisfied
4. Unsatisfied requirements → replan (don't just stop)

### Priority 3: Dynamic Replanning Loop
When verification shows a requirement unmet:
- Diagnose why (element not found? wrong page? missing data?)
- Replan that requirement (different capability/approach)
- Retry up to N times
- This is what makes novel goals succeed

### Priority 4: Capability Learning (future)
When a needed capability doesn't exist:
- Identify the gap
- Propose implementation
- Generate + test
- Request approval
- Integrate safely

### Recently Done
- Removed workflow drift (_try_fast_path, _single_goal_capabilities)
- Requirements Discovery layer (8 tests)
- LLM decomposition is primary path
- Generic fallback is requirement-shaped, not workflow-shaped
- 375 tests passing

### Honest State
- LLM latency (NVIDIA cold start 20-30s) makes multi-step web tasks slow
- Web extraction needs logged-in Chrome profile
- Verification is action-level; needs requirement-level upgrade
