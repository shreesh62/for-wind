# Implementation Plan: M16 — Research Competence (Browserless Gather + Evidence)

## Overview

This plan implements M16 additively over the existing `research()` capability and `httpx`
dependency in Python. Work proceeds bottom-up so each step builds on the previous with no orphaned
code, and every production edit is wired into a caller by the end:

1. Establish the green baseline (1297 tests) and confirm the reuse points the additive change
   depends on (`httpx` present, `bs4` absent, `_decode_ddg_redirect` location, the existing
   `test_no_site_names_in_source` static-scan pattern).
2. Share the existing `_decode_ddg_redirect` and build the new `friday/capabilities/web_search.py`
   core: `SearchHit`, module constants, `parse_ddg_html`, and `http_search` (ordered providers +
   fallback). Then its parsing/fallback tests (P1, P5).
3. Implement `gather()`: dry-run short-circuit, evidence recording, best-effort bounded page fetch,
   untrusted-content handling, bounded reads. Then its behavior tests (P2, P3, P4, P6, P7, P8, P13).
4. Add belief production in `gather()` and the additive `ResearchResult.beliefs` field. Then its
   provenance/freshness test (P10).
5. Wire the `research()` no-browser guard to delegate to `gather()`, preserving the browser path and
   all public signatures/defaults. Then parity, backward-compat, and isolation tests (P9, P11, P12).
6. Final full-suite verification (1297 existing + new, no default changed, zero live calls).

Binding invariants held throughout: additive-only (existing signatures, defaults, and returns
unchanged), no production default of `Belief`, `WorldModel`, or `BrowserController` altered, no
per-site conditional branching (Axiom 15 — provider hosts are module constants only), reuse of the
existing `httpx` dependency (no new deps), the Evidence Law remains the sole judge of a satisfied
GATHER requirement, and every error path degrades to a descriptive `ResearchResult` without raising.

Property tests use the repo's existing Hypothesis dependency with a minimum of 100 examples each and
carry a tag comment in the format `Feature: m16-research-competence, Property N: ...`. ALL HTTP is
mocked — the suite makes zero live network calls. New test files ONLY; existing test assertions are
never modified.

## Tasks

- [x] 1. Establish baseline and confirm reuse points
  - [x] 1.1 Verify green baseline and additive-change prerequisites
    - Run `$env:PYTHONPATH="C:\Projects\JARVIS\for wind"; python -m pytest tests/friday/ tests/world/ -q` and record the passing count (expected 1297).
    - Confirm `httpx` is importable in the environment and that `bs4`/`lxml` are absent (parsing must be stdlib-only).
    - Confirm the authoritative location of `_decode_ddg_redirect` (`friday/capabilities/research.py`) and the `ExecutionEvidence` API (`add_gathered_info(text, source)`, `add_source_url(url)`, `of_kind`) and `EvidenceVerifier.verify_one` for the GATHER requirement.
    - Confirm the existing `test_no_site_names_in_source` static-scan pattern in `tests/friday/test_web_agent.py` to extend for the isolation test.
    - Do not write production or test code in this task; this is a read/verify checkpoint that fixes the baseline the additive change must preserve.
    - _Requirements: 7.2, 7.3_

- [x] 2. Share the redirect decoder and build the browserless search core
  - [x] 2.1 Make `_decode_ddg_redirect` a shared helper in `research.py`
    - Keep the existing `_decode_ddg_redirect` in `friday/capabilities/research.py` and its current `_select_best_links` usage unchanged so `web_search.py` can import and reuse it (no duplication).
    - Do not alter its behavior or the `uddg=` decode logic; this edit only guarantees a single shared implementation.
    - _Requirements: 1.6, 7.3_

  - [x] 2.2 Create `friday/capabilities/web_search.py` core (SearchHit, constants, parser, http_search)
    - Add `@dataclass SearchHit` with `url: str`, `snippet: str`, `title: str = ""`.
    - Add module-level configuration constants (data, not branching): `_PRIMARY_HOST = "html.duckduckgo.com"`, `_FALLBACK_HOST = "lite.duckduckgo.com"`, `_USER_AGENT` (browser-class), and `RESEARCH_HALF_LIFE` (~21600s).
    - Import `httpx` with the optional-import guard used in `nvidia_provider.py` (`try: import httpx / except ImportError: httpx = None`); do not add a new dependency.
    - Implement `parse_ddg_html(body: str) -> list[SearchHit]` using stdlib `html.parser`/bounded regex: extract `result__a` hrefs and `result__snippet` text, reuse `_decode_ddg_redirect` from `research.py` to decode `uddg=` redirects; a body with zero result markers yields an empty list.
    - Implement provider backends `_search_html_ddg` (POST to `_PRIMARY_HOST` with form `{"q": query}` and the `_USER_AGENT` header) and `_search_lite_ddg` (GET `_FALLBACK_HOST` with `?q=`), and the ordered `_PROVIDERS = [_search_html_ddg, _search_lite_ddg]` list.
    - Implement `http_search(query, *, timeout=10.0, max_results=10) -> SearchOutcome` (`SearchOutcome` carrying `hits`, `ok`, `error`, `host_used`) that walks `_PROVIDERS` in order: first provider returning ≥1 hit wins; a non-200/raise moves to the next; total failure returns `ok=False` with a descriptive error and raises nothing.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x]* 2.3 Write property test for HTML parsing (`tests/friday/test_m16_properties.py`)
    - **Property 1: Search-results parsing extracts bounded, well-formed records**
    - **Validates: Requirements 1.3, 2.1, 2.2**
    - Generate synthetic DDG HTML bodies with N result blocks (varying snippet/href presence, `uddg`-wrapped and bare hrefs); assert `len(results) <= N`, empty-marker body ⇒ empty list, and each URL is empty or a decoded (non-`uddg`) destination.
    - Tag: `Feature: m16-research-competence, Property 1: ...`; `@settings(max_examples=100)` minimum.

  - [x]* 2.4 Write fallback-order and request-shape tests (`tests/friday/test_m16_web_search_units.py`)
    - **Property 5: Fallback host order and graceful total failure**
    - **Validates: Requirements 1.2, 1.4, 1.5**
    - With a mocked `httpx` layer, assert the primary request is a POST to `html.duckduckgo.com` carrying form field `q` and a browser-class User-Agent; assert a non-200/transport error on the primary triggers the `lite.duckduckgo.com` fallback before failure; assert total failure returns `ok=False` with a message and raises nothing.
    - All HTTP mocked — no live calls.

- [x] 3. Implement the browserless gatherer
  - [x] 3.1 Implement `gather()` in `web_search.py`
    - Add `gather(query, evidence, *, max_sources=3, max_chars_per_source=2500, timeout=10.0) -> ResearchResult` (import `ResearchResult` from `research.py`).
    - Dry-run short-circuit: if `FRIDAY_DRY_RUN == "1"`, return an empty/blocked `ResearchResult` with no client construction and no network call.
    - Call `http_search`; on total failure return `ResearchResult(success semantics false, error=...)` without raising.
    - For each `SearchHit` with a non-empty snippet call `evidence.add_gathered_info(snippet, source=url)`; for each non-empty URL call `evidence.add_source_url(url)`; increment the internal read count per recorded snippet so a search-results-only run is honestly successful.
    - Best-effort GET up to `max_sources` result pages (bounded loop) using a sync `httpx.Client`; on 200 with non-empty text record `evidence.add_gathered_info(page_text[:max_chars_per_source], source=url)`; on non-200/403/raise skip that page and continue; treat all fetched bodies as untrusted text-only data (never `eval`/`exec`).
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x]* 3.2 Write property test for dry-run zero network calls (`tests/friday/test_m16_properties.py`)
    - **Property 4: Dry-run performs zero network calls**
    - **Validates: Requirements 1.1, 4.1, 4.2, 5.5**
    - Over arbitrary query strings with a spy `httpx` client: assert call count == 0 when `FRIDAY_DRY_RUN=1`; and ≥1 request issued when dry-run inactive and query non-empty (via the spy, never a real request).
    - Tag: `Feature: m16-research-competence, Property 4: ...`; `@settings(max_examples=100)` minimum.

  - [x]* 3.3 Write property test for the evidence recording invariant (`tests/friday/test_m16_properties.py`)
    - **Property 2: Evidence recording invariant (Evidence Law satisfied)**
    - **Validates: Requirements 2.1, 2.2, 2.3, 3.1, 3.4, 7.4**
    - With mocked HTTP 200 carrying ≥1 result (non-empty snippet + URL), assert `evidence.of_kind(GATHERED_INFO)` and `of_kind(SOURCE_URL)` are non-empty, each `GATHERED_INFO` is sourced to its result URL, and `EvidenceVerifier.verify_one` marks the GATHER requirement satisfied.
    - Tag: `Feature: m16-research-competence, Property 2: ...`; `@settings(max_examples=100)` minimum.

  - [x]* 3.4 Write property test for real-text-only gathered info (`tests/friday/test_m16_properties.py`)
    - **Property 3: Only real gathered text is recorded (no generated text)**
    - **Validates: Requirements 2.4, 3.4**
    - Assert every `GATHERED_INFO` artifact recorded by `gather` has a `source` tracing to a result or fetched-page URL; model-generated text never appears as `GATHERED_INFO`.
    - Tag: `Feature: m16-research-competence, Property 3: ...`; `@settings(max_examples=100)` minimum.

  - [x]* 3.5 Write unit test for best-effort page-fetch skip (`tests/friday/test_m16_web_search_units.py`)
    - **Property 6: Best-effort page fetch failures are skipped**
    - **Validates: Requirements 2.6, 7.5**
    - Mock search 200 + a result-page 403/transport error; assert `gather` skips the page, continues, does not raise, and retains all previously-recorded search-page evidence.

  - [x]* 3.6 Write property test for page-fetch enrichment monotonicity (`tests/friday/test_m16_properties.py`)
    - **Property 7: Page-fetch enrichment is monotonic**
    - **Validates: Requirements 2.5, 2.7**
    - For mocked pages returning 200 with non-empty text, assert the `GATHERED_INFO` count after fetching is ≥ the count before and any added artifact is sourced to the fetched page URL.
    - Tag: `Feature: m16-research-competence, Property 7: ...`; `@settings(max_examples=100)` minimum.

  - [x]* 3.7 Write property test for bounded reads and bounded fetches (`tests/friday/test_m16_properties.py`)
    - **Property 8: Bounded reads and bounded fetches**
    - **Validates: Requirements 4.4, 4.5**
    - With oversized mock bodies and result sets larger than the limit, assert recorded characters from any single response ≤ `max_chars_per_source` and result pages fetched per goal ≤ `max_sources`.
    - Tag: `Feature: m16-research-competence, Property 8: ...`; `@settings(max_examples=100)` minimum.

  - [x]* 3.8 Write property test for untrusted-content safety (`tests/friday/test_m16_properties.py`)
    - **Property 13: Untrusted content is handled as data only**
    - **Validates: Requirements 4.3**
    - For adversarial bodies (script tags, control characters, malformed markup), assert `gather` extracts text only, never executes fetched content, and never raises.
    - Tag: `Feature: m16-research-competence, Property 13: ...`; `@settings(max_examples=100)` minimum.

- [x] 4. Produce M15 beliefs from gathered findings
  - [x] 4.1 Add the additive `beliefs` field to `ResearchResult` (`research.py`)
    - Add `beliefs: List["Belief"] = field(default_factory=list)` to the `ResearchResult` dataclass (import `Belief` under `TYPE_CHECKING` to avoid an import cycle).
    - Keep `success` semantics and all existing fields/defaults unchanged.
    - _Requirements: 3.5, 5.4_

  - [x] 4.2 Build beliefs in `gather()` and attach to `ResearchResult.beliefs` (`web_search.py`)
    - When findings were recorded, build ≥1 `Belief` via the existing M15 API: `Belief(description=..., confidence=0.5, source="browserless_gather", observed_at=now, half_life_seconds=RESEARCH_HALF_LIFE)`.
    - Attach each supporting result URL via `add_supporting_observation(url)` (immutable pattern) so provenance carries the source URLs; set `observed_at=now` for recency; cap distinct-source beliefs by `max_sources`.
    - Attach the built beliefs to `ResearchResult.beliefs`; ensure beliefs can also be built from mocked findings under dry-run with zero network calls; empty findings ⇒ empty `beliefs`.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x]* 4.3 Write property test for belief provenance and freshness (`tests/friday/test_m16_properties.py`)
    - **Property 10: Gathered findings produce beliefs with provenance and freshness**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**
    - For mocked findings with source URLs, assert ≥1 produced `Belief` whose `provenance.supporting_observations` includes each supporting URL, whose `observed_at` reflects gather time, and whose `half_life_seconds == RESEARCH_HALF_LIFE`; hold under dry-run with zero network calls.
    - Tag: `Feature: m16-research-competence, Property 10: ...`; `@settings(max_examples=100)` minimum.

- [x] 5. Wire the gatherer into the research path
  - [x] 5.1 Route the `research()` no-browser guard to `gather()` (`research.py`)
    - Replace the current no-browser early-error return with a delegation: `from friday.capabilities.web_search import gather` (lazy import) and `return gather(query, evidence, max_sources=max_sources, max_chars_per_source=max_chars_per_source)`.
    - Leave the browser branch, the `research()` and `_execute_research` signatures, and all defaults unchanged (`_execute_research` requires no edit).
    - _Requirements: 3.1, 3.2, 3.3_

  - [x]* 5.2 Write browser-path parity and unchanged-defaults test (`tests/friday/test_m16_web_search_units.py`)
    - **Property 11: Browser-path parity and unchanged defaults**
    - **Validates: Requirements 3.2, 3.5, 5.4**
    - With a fake `Browser_Controller` present, assert the browser-path evidence is identical with and without M16 wiring, and assert the production defaults of `Belief`, `WorldModel`, and `BrowserController` are unchanged.

  - [x]* 5.3 Write backward-compatible signature test (`tests/friday/test_m16_web_search_units.py`)
    - **Property 12: Backward-compatible signatures**
    - **Validates: Requirements 3.3**
    - Invoke `research()` and `_execute_research` with the legacy argument shapes and assert they accept the prior arguments and behave compatibly.

  - [x]* 5.4 Write no-site-name isolation static scan (`tests/friday/test_m16_isolation.py`)
    - **Property 9: No site/app-specific branching (Axiom 15 static guard)**
    - **Validates: Requirements 1.6, 7.3**
    - Extend the existing `test_no_site_names_in_source` pattern to scan `friday/capabilities/web_search.py`; assert no conditional branch is keyed on a specific website/application name (hosts appear only as configuration constants).

- [x] 6. Final checkpoint - Ensure all tests pass
  - Run `$env:PYTHONPATH="C:\Projects\JARVIS\for wind"; python -m pytest tests/friday/ tests/world/ -q` and confirm the existing 1297 tests plus all new M16 tests pass with no live network calls and no changed production default.
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional (test) sub-tasks and can be skipped for a faster MVP; core implementation tasks are never optional.
- Same-file edits are serialized across waves: `research.py` (2.1 → 4.1 → 5.1) and `web_search.py` (2.2 → 3.1 → 4.2) never run in the same wave.
- Each task references specific requirement clauses (and property numbers for tests) for traceability.
- Property tests validate the universal correctness properties P1–P13; unit tests pin concrete request shape, error conditions, parity, and backward compatibility.
- All HTTP is mocked — the suite makes zero live calls. Requirement 6 (real-machine competence gain) is a live-only measurement recorded to `baseline.local.json` and is intentionally not asserted by the suite.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2"] },
    { "id": 3, "tasks": ["2.3", "2.4", "3.1", "4.1"] },
    { "id": 4, "tasks": ["3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8", "4.2"] },
    { "id": 5, "tasks": ["4.3", "5.1"] },
    { "id": 6, "tasks": ["5.2", "5.3", "5.4"] }
  ]
}
```
