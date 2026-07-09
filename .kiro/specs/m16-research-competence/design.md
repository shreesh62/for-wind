# Design Document — M16 Research Competence (Browserless Gather + Evidence)

## Overview

M16 makes the `research` and `long_horizon` capability-benchmark domains *satisfiable* on a
real machine by giving the Operator a way to gather real web information **without a browser**.
Today the only search/read path lives inside the Playwright `BrowserController.search_web`;
`friday/capabilities/research.py::research()` hard-requires a live `browser_controller` and, with
none, returns early at the no-browser guard recording zero evidence. Because the capability
benchmark constructs its `Operator` with **no** browser, every research goal produces no
`GATHERED_INFO` / `SOURCE_URL`, the Evidence Law (ADR-023) rightly refuses to satisfy the GATHER
requirement, and both domains score 0.0.

This design adds a **browserless gatherer** — a plain-HTTP search + best-effort page read over the
already-present `httpx` dependency — and wires it in as the *fallback inside* the existing
no-browser guard of `research()`. The browser path is untouched. All network I/O is gated by
`FRIDAY_DRY_RUN`. Gathered findings additionally become **M15 World Model v2 beliefs** (provenance
from result URLs, freshness for recency), surfaced on the `ResearchResult` for a kernel/world
consumer to ingest — because the executor holds no `WorldModel` reference today (verified: no
`world_model`/`WorldModel` symbol appears in `executor.py`).

The change is strictly **additive**: no production default changes, public signatures of
`research()` and `_execute_research` stay backward-compatible, and the design introduces **no
application- or site-specific logic** (Axiom 15) — the gatherer talks to a general
`Search_Provider` interface. The full regression suite (1297 tests) must stay green; all new tests
mock the HTTP layer and make zero live calls.

### Goals

- A `friday/capabilities/web_search.py` module providing a general, pluggable browserless search +
  gather, reusing the existing DuckDuckGo HTML result structure and `uddg=` redirect decoding.
- Route `research()` to the gatherer when no browser is available; preserve the browser path.
- Record real snippets + result URLs (and best-effort page text) as evidence via the existing
  `ExecutionEvidence` API — never model-generated text.
- Produce M15 beliefs with provenance + freshness from the gathered findings.
- Dry-run safety, untrusted-content handling, bounded reads/fetches, and no new heavy dependencies.

### Non-Goals

- No change to the Playwright `BrowserController` search/read behavior.
- No wiring of a live `WorldModel` into the executor (beliefs are *returned* for a future consumer).
- No fabrication of benchmark scores; the real competence gain (Requirement 6) is a live-only
  measurement recorded to `baseline.local.json` on a real machine and is **not** asserted by the
  test suite.

### Verified feasibility (used as-is)

- `POST https://html.duckduckgo.com/html/` with form `{"q": query}` + a browser-class User-Agent →
  HTTP 200 with ~20 result markers. Each result block carries a link (`result__a` href, usually a
  `/l/?uddg=<encoded>` redirect that must be URL-decoded) and a snippet (`result__snippet`).
- Fallback: `GET https://lite.duckduckgo.com/lite/?q=<query>` → 200 with links.
- Individual result pages may 403 to non-browser clients — best-effort, skip on non-200/error.

## Architecture

### Component placement

```
friday/
  capabilities/
    research.py        # MODIFIED: no-browser guard now routes to the gatherer
    web_search.py      # NEW: browserless Search_Provider + gatherer + belief production
  executor.py          # UNCHANGED signature; _execute_research already calls research()
  world/
    belief.py          # M15 — used to construct beliefs (unchanged)
    provenance.py      # M15 — supporting_observations (unchanged)
```

### Routing flow

```mermaid
flowchart TD
    A[_execute_research(query, ctx)] --> B[research(query, browser, evidence)]
    B --> C{browser available?}
    C -->|yes| D[Existing browser path\nsearch_web -> navigate -> read_text]
    C -->|no| E{FRIDAY_DRY_RUN == 1 ?}
    E -->|yes| F[return blocked/empty ResearchResult\nNO network call]
    E -->|no| G[gather(query, evidence, ...)]
    G --> H[http_search via Search_Provider\nhtml.duckduckgo.com POST]
    H --> I{HTTP 200?}
    I -->|no / error| J[fallback: lite.duckduckgo.com GET]
    I -->|yes| K[parse result blocks -> list[SearchHit]]
    J --> K
    K --> L[record snippet + source_url evidence]
    L --> M[best-effort GET each result page\nbounded count, skip 403/errors]
    M --> N[record page text evidence bounded]
    N --> O[build beliefs w/ provenance + freshness]
    O --> P[return ResearchResult incl. beliefs]
```

### Key architectural decisions

**AD-1 — New module `friday/capabilities/web_search.py` with a pure search function + a gatherer.**
The module exposes a general `Search_Provider` abstraction as a list of pluggable *backend
functions* (each `(query, *, timeout, max_results) -> list[SearchHit]`), a pure parser
`parse_ddg_html(body) -> list[SearchHit]`, a public `http_search(query, *, timeout, max_results)`
that walks the provider list in order, and a `gather(query, evidence, *, max_sources,
max_chars_per_source, ...) -> ResearchResult`. No per-site branching keyed on a website/app name
exists anywhere (Axiom 15) — the DDG hosts are configuration data (module-level constants), not
conditional logic.

**AD-2 — Synchronous `httpx.Client` (not async).** `research()` is invoked *synchronously* from
`executor._execute_research` (it calls `research(...)` directly, not through `self._run_async`).
A sync `httpx.Client` therefore avoids introducing an event loop into a sync call path and keeps
the gatherer trivially mockable. `httpx` is imported with the same optional guard used in
`nvidia_provider.py` (`try: import httpx / except ImportError: httpx = None`); if `httpx` is
unavailable the gatherer returns a graceful `success=False` result. No new dependency is added.

**AD-3 — HTML parsing with the standard library only.** `bs4`/`lxml` are **not** present in the
repo (verified: zero matches). Parsing reuses the DDG result structure the browser path already
relies on: extract `result__a` hrefs and `result__snippet` text with `html.parser` (stdlib) /
bounded regex, then decode `uddg=` redirects with the **exact** decode logic already in
`research.py::_decode_ddg_redirect` (promoted/shared, not duplicated).

**AD-4 — Fallback inside the no-browser guard.** `research()` keeps its signature. The current
early-return at the no-browser guard (research.py lines ~73–76) is replaced by a call into the
gatherer; the browser branch is unchanged. This is the minimal, additive wiring point.

**AD-5 — Beliefs are returned, not ingested.** The executor has no `WorldModel`. Beliefs built from
findings are attached to `ResearchResult.beliefs` so a future kernel/world consumer can ingest them
via the existing `WorldModel.ingest`/belief APIs. This boundary is documented honestly and the
belief construction is unit-tested directly.

## Components and Interfaces

### `SearchHit` (new dataclass, `web_search.py`)

```python
@dataclass
class SearchHit:
    url: str        # real destination (uddg-decoded), may be "" if undecodable
    snippet: str    # result__snippet text, may be ""
    title: str = "" # result__a text, best-effort
```

### `Search_Provider` backends (new, `web_search.py`)

```python
# Module-level configuration data (NOT site-specific logic):
_PRIMARY_HOST  = "html.duckduckgo.com"   # POST form {"q": query}
_FALLBACK_HOST = "lite.duckduckgo.com"   # GET  ?q=query
_USER_AGENT    = "Mozilla/5.0 (...)"     # browser-class UA
_PROVIDERS: list[Callable[..., list[SearchHit]]] = [_search_html_ddg, _search_lite_ddg]

def parse_ddg_html(body: str) -> list[SearchHit]: ...
def http_search(query: str, *, timeout: float = 10.0, max_results: int = 10) -> SearchOutcome: ...
```

`SearchOutcome` carries `hits: list[SearchHit]`, `ok: bool`, `error: str`, `host_used: str`.
`http_search` tries `_PROVIDERS` in order; the first provider returning ≥1 hit wins. If a provider
returns non-200 or raises, the next is tried. If all fail, `ok=False` with a descriptive `error`
and **no exception** propagates.

### `gather` (new, `web_search.py`)

```python
def gather(
    query: str,
    evidence: ExecutionEvidence,
    *,
    max_sources: int = 3,
    max_chars_per_source: int = 2500,
    timeout: float = 10.0,
) -> ResearchResult:
    """Browserless search + best-effort page read + evidence + belief production."""
```

Behavior:
1. If `FRIDAY_DRY_RUN == 1` → return an empty/blocked `ResearchResult` with **no** network call.
2. Call `http_search`. On total failure → `ResearchResult(success=False, error=...)`.
3. For each `SearchHit` with a non-empty snippet → `evidence.add_gathered_info(snippet, source=url)`;
   for each non-empty URL → `evidence.add_source_url(url)`.
4. Best-effort `GET` up to `max_sources` result pages (bounded); on 200 with non-empty text →
   `evidence.add_gathered_info(page_text[:max_chars_per_source], source=url)`; on non-200/error →
   skip and continue.
5. Build beliefs (see Data Models) and attach to `ResearchResult.beliefs`.

### `research()` (modified, `research.py`) — additive fallback

The no-browser guard changes from an early error return to a delegation:

```python
if not browser_controller or not getattr(browser_controller, "available", False):
    # M16: no browser -> browserless gather (dry-run safe inside gather()).
    from friday.capabilities.web_search import gather
    return gather(
        query, evidence,
        max_sources=max_sources,
        max_chars_per_source=max_chars_per_source,
    )
# ... existing browser path unchanged ...
```

Signature, defaults, and the browser path are unchanged (Req 3.2, 3.3, 3.5). `_execute_research`
needs no change — it already reads `result.success`, `result.gathered_text`, `result.source_urls`.

### `_execute_research` (executor, unchanged)

Confirmed compatible: it calls `research(query=..., browser_controller=self._browser,
evidence=ctx.evidence, max_sources=3)` and branches on `result.blocked` / `result.success` /
`result.gathered_text`. The gatherer populates all of these.

## Data Models

### `ResearchResult` (extended, additive fields only)

The existing dataclass gains one additive, defaulted field so no caller breaks:

```python
@dataclass
class ResearchResult:
    query: str
    sources_read: int = 0
    source_urls: List[str] = field(default_factory=list)
    gathered_text: str = ""
    blocked: bool = False
    error: str = ""
    beliefs: List["Belief"] = field(default_factory=list)  # M16 additive — for kernel ingest

    @property
    def success(self) -> bool:
        return self.sources_read > 0 and bool(self.gathered_text.strip())
```

Note: `success` intentionally keeps its existing semantics. For the browserless path, snippets alone
count as gathered text and each recorded snippet increments the internal read count so that a
search-results-only run is still honestly "successful" per the Evidence Law (≥1 GATHERED_INFO).

### Belief production from findings

For a research goal that recorded findings, `gather` builds **one summary Belief** (plus optionally
one per distinct source, capped by `max_sources`) using the existing M15 API — no new belief API:

```python
belief = Belief(
    description=f"Research finding for '{query}': {snippet_or_summary[:200]}",
    confidence=0.5,                         # unverified web finding
    source="browserless_gather",
    observed_at=now,                        # research recency (Req 5.3)
    half_life_seconds=RESEARCH_HALF_LIFE,   # research-appropriate freshness (e.g. 6h)
)
for url in source_urls:                     # Req 5.2 — provenance from result URLs
    belief = belief.add_supporting_observation(url)
```

`add_supporting_observation` returns a new Belief (immutable pattern) whose
`provenance.supporting_observations` contains the URLs. `observed_at=now` + `half_life_seconds`
encode recency/freshness (Req 5.3). Under dry-run, beliefs can still be built from mocked findings
in tests without any network call (Req 5.5). `RESEARCH_HALF_LIFE` is a module constant chosen for
research recency (proposed 6 hours = 21600s); it does not change the `Belief` default of 86400s.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a
system — essentially, a formal statement about what the system should do. Properties serve as the
bridge between human-readable specifications and machine-verifiable correctness guarantees.*

The 12 acceptance-criteria properties from `requirements.md` are consolidated below (redundant
criteria folded together per the prework reflection). Every property is testable with **mocked
`httpx`** — the suite makes no live calls. Requirement 6 (real-machine competence gain) is a
live-only measurement recorded to `baseline.local.json` and is intentionally **not** asserted by
the suite.

### Property 1: Search-results parsing extracts bounded, well-formed records

*For any* generated DuckDuckGo-style HTML body containing N synthetic result blocks,
`parse_ddg_html` returns a list of `SearchHit` records with `len(results) <= N` (a body with zero
result markers yields an empty list), and every returned record's URL is either empty or a decoded
(non-`uddg`-wrapped) destination.

**Validates: Requirements 1.3, 2.1, 2.2**

### Property 2: Evidence recording invariant (Evidence Law satisfied)

*For any* mocked HTTP 200 search response carrying at least one result with a non-empty snippet and
URL, when `gather` runs with no browser and dry-run inactive, the `ExecutionEvidence` contains at
least one real `GATHERED_INFO` artifact and at least one real `SOURCE_URL` artifact, each
`GATHERED_INFO` snippet is sourced to its result URL, and `EvidenceVerifier.verify_one` marks the
corresponding GATHER requirement satisfied.

**Validates: Requirements 2.1, 2.2, 2.3, 3.1, 3.4, 7.4**

### Property 3: Only real gathered text is recorded (no generated text)

*For any* mocked search/page results, every `GATHERED_INFO` artifact recorded by `gather` has a
`source` that traces to a result or fetched-page URL — model-generated text never appears as
`GATHERED_INFO`.

**Validates: Requirements 2.4, 3.4**

### Property 4: Dry-run performs zero network calls

*For any* query string, when `FRIDAY_DRY_RUN == 1`, `gather` (and `http_search`) issue **zero**
requests through the injected/spy `httpx` client and return without contacting any provider or
result page. Conversely, when dry-run is inactive and the query is non-empty, at least one request
is issued.

**Validates: Requirements 1.1, 4.1, 4.2, 5.5**

### Property 5: Fallback host order and graceful total failure

*For any* provider outcome sequence, when the primary host (`html.duckduckgo.com`) returns a
non-200 status or raises a transport error, `http_search` attempts the fallback host
(`lite.duckduckgo.com`) before reporting failure; and when every provider fails, it returns
`ok=False` with a descriptive error message and raises no exception to the caller.

**Validates: Requirements 1.4, 1.5**

### Property 6: Best-effort page fetch failures are skipped

*For any* mocked result-page fetch that returns a non-200 status or raises, `gather` skips that page,
continues processing remaining results, completes without raising, and retains all
previously-recorded search-page evidence.

**Validates: Requirements 2.6, 7.5**

### Property 7: Page-fetch enrichment is monotonic

*For any* mocked result page returning HTTP 200 with non-empty body text, the count of
`GATHERED_INFO` artifacts after best-effort fetching is greater than or equal to the count before,
and any added artifact is sourced to the fetched page URL.

**Validates: Requirements 2.5, 2.7**

### Property 8: Bounded reads and bounded fetches

*For any* oversized response body and *for any* result set larger than the configured limit, the
number of characters recorded from any single response is at most `max_chars_per_source`, and the
number of result pages fetched best-effort per research goal is at most `max_sources`.

**Validates: Requirements 4.4, 4.5**

### Property 9: No site/app-specific branching (Axiom 15 static guard)

*For any* scan of the M16 source module (`web_search.py`), no conditional branch is keyed on a
specific website or application name — provider hosts appear only as configuration constants, never
in `if`-logic.

**Validates: Requirements 1.6, 7.3**

### Property 10: Gathered findings produce beliefs with provenance and freshness

*For any* set of mocked findings with source URLs, `gather` produces at least one `Belief` whose
`provenance.supporting_observations` includes each supporting result URL, whose `observed_at`
reflects the gather time (recency), and whose `half_life_seconds` equals the research freshness
constant — and this holds under dry-run using mocked findings with zero network calls.

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

### Property 11: Browser-path parity and unchanged defaults

*For any* research goal executed with a (fake) `Browser_Controller` present, the evidence produced
via the browser path is identical with and without the M16 wiring, and the production defaults of
`Belief`, `WorldModel`, and `BrowserController` are unchanged.

**Validates: Requirements 3.2, 3.5, 5.4**

### Property 12: Backward-compatible signatures

*For any* legacy call shape of `research()` and `_execute_research`, the functions accept the prior
arguments unchanged and behave compatibly.

**Validates: Requirements 3.3**

### Property 13: Untrusted content is handled as data only

*For any* fetched body — including adversarial markup, script tags, or control characters — `gather`
extracts only text, never executes fetched content, and never raises.

**Validates: Requirements 4.3**

## Property-to-Requirement Traceability

| Property | Pattern category | Validates (Requirements) |
|----------|------------------|--------------------------|
| P1 Parsing bounded/well-formed | Metamorphic + Model-based | 1.3, 2.1, 2.2 |
| P2 Evidence recording invariant | Invariant (Evidence Law) | 2.1, 2.2, 2.3, 3.1, 3.4, 7.4 |
| P3 Only real gathered text | Invariant | 2.4, 3.4 |
| P4 Dry-run zero calls | Invariant | 1.1, 4.1, 4.2, 5.5 |
| P5 Fallback order + graceful fail | Error conditions + Confluence | 1.4, 1.5 |
| P6 Page-fetch skip | Error conditions | 2.6, 7.5 |
| P7 Page-fetch enrichment monotonic | Metamorphic | 2.5, 2.7 |
| P8 Bounded reads/fetches | Invariant | 4.4, 4.5 |
| P9 No site-name branching | Invariant (static guard) | 1.6, 7.3 |
| P10 Belief provenance + freshness | Invariant / Round-trip | 5.1, 5.2, 5.3, 5.4, 5.5 |
| P11 Browser parity + defaults | Model-based (parity) | 3.2, 3.5, 5.4 |
| P12 Backward-compat signatures | Invariant (backward compat) | 3.3 |
| P13 Untrusted content safe | Error conditions / edge-case | 4.3 |

## Design-to-Requirement Traceability

| Requirement | Design element |
|-------------|----------------|
| 1.1–1.3 | `http_search` + `parse_ddg_html`; POST to `html.duckduckgo.com` with form `q` + UA (AD-1, AD-2) |
| 1.4–1.5 | `_PROVIDERS` ordered list; fallback host; graceful `SearchOutcome(ok=False)` (AD-1) |
| 1.6 | General `Search_Provider` backend list; hosts as constants, no per-site `if` (AD-1, AD-3) |
| 2.1–2.4 | `gather` records snippet→`add_gathered_info(snippet, url)`, url→`add_source_url`; only real text |
| 2.5–2.7 | Best-effort page GET loop with bounded count, 200→`add_gathered_info(page[:cap], url)` |
| 3.1–3.5 | `research()` no-browser guard delegates to `gather`; browser path + signatures unchanged (AD-4) |
| 4.1–4.2 | Dry-run short-circuit at top of `gather`/`http_search` (no client construction) |
| 4.3 | stdlib text parsing only; never `eval`/`exec` fetched content (AD-3) |
| 4.4–4.5 | `max_chars_per_source` slice + `max_sources` fetch cap |
| 5.1–5.5 | Belief construction from findings via M15 API; `ResearchResult.beliefs`; returned for ingest (AD-5) |
| 6.1–6.5 | Live-only via benchmark harness (`requires_live` skipped in dry-run); `baseline.local.json` |
| 7.1–7.5 | New mocked-HTTP test files; extended no-site-names guard; full regression green |

## Error Handling

| Condition | Handling | Result to caller |
|-----------|----------|------------------|
| `httpx` not importable | Optional-import guard (mirrors `nvidia_provider`) | `ResearchResult(success=False, error="httpx unavailable")`; no raise |
| `FRIDAY_DRY_RUN == 1` | Short-circuit before any client construction | Empty/blocked `ResearchResult`; zero network calls |
| Primary host non-200 / transport error | Try fallback host next | Fallback attempted; only fail after all providers |
| All providers fail | `SearchOutcome(ok=False, error=...)` | `ResearchResult(success=False, error=...)`; no raise |
| Search 200 but zero parseable results | Empty hit list | `ResearchResult` with no evidence, `success=False`; no raise |
| Result-page fetch non-200 / 403 / raise | Skip page, continue loop | Prior search-page evidence retained; run completes |
| Oversized response body | Slice to `max_chars_per_source` before recording | Bounded `GATHERED_INFO` value |
| Too many results | Fetch at most `max_sources` pages | Bounded fetch count |
| Adversarial / malformed markup | Parse as text via stdlib; never execute | Text-only extraction; no raise |
| Belief construction from empty findings | No findings → no beliefs (empty list) | `ResearchResult.beliefs == []`; no raise |

All error paths are **non-raising** to the caller: `research()`/`gather` degrade to a descriptive
`ResearchResult` so the executor and Evidence Law remain the judges (never a crash).

## Testing Strategy

### Approach

- **Unit tests** cover specific examples, request-shape assertions, error conditions, and
  backward-compat/parity checks.
- **Property-based tests** (Hypothesis) cover the universal properties P1–P13 across generated
  inputs (HTML bodies, hit lists, queries, oversized bodies, adversarial markup, mocked outcome
  sequences).
- Both are complementary: unit tests pin concrete behavior; property tests verify general
  correctness.

### HTTP is always mocked — no live calls

Every M16 test patches the `httpx` layer (a fake/spy client or `httpx.MockTransport`) so **no real
network request** occurs. Tests set `os.environ.setdefault("FRIDAY_DRY_RUN", "1")` before importing
`friday` modules (matching the repo convention), and dry-run-inactive request behavior is exercised
by explicitly toggling the flag around a spy client (never issuing a real request). New tests reside
in **new files only**:

- `tests/friday/test_m16_web_search_units.py` — request shape (1.2), fallback order (P5), page-fetch
  skip (P6), backward-compat signatures (P12), browser parity + unchanged defaults (P11), static
  no-site-name guard (P9).
- `tests/friday/test_m16_properties.py` — Hypothesis property tests P1–P10, P13.
- `tests/friday/test_m16_isolation.py` — no-site-name / no-hardcoding static scan over `web_search.py`
  (extends the existing `test_no_site_names_in_source` pattern).

### Property-based testing configuration

- Use the repo's existing **Hypothesis** dependency (already used by `test_m*_properties.py`).
  Do NOT implement property testing from scratch.
- Each property test runs a **minimum of 100 iterations** (`@settings(max_examples=100)` or higher).
- Each property test is tagged with a comment referencing the design property, format:
  **Feature: m16-research-competence, Property N: {property_text}**
- Generators: synthetic DDG HTML bodies with N result blocks (varying snippet/href presence,
  `uddg`-wrapped and bare hrefs), lists of `SearchHit`, arbitrary query strings, oversized bodies
  (length > cap), adversarial bodies (script tags, control chars), and mocked provider/page outcome
  sequences (200 / non-200 / raise).

### What is NOT tested in the suite (honesty rule)

Requirement 6 (real `research`/`long_horizon` competence gain) is a **live-only** measurement. The
benchmark harness marks these `requires_live` and skips them under `FRIDAY_DRY_RUN`
(`scripts/kernel_validation/run_capability_benchmarks.py`); real scores are recorded to
`baseline.local.json` on a real machine, and the committed baseline seed stays all-unmeasured. The
suite asserts none of these scores — it only asserts the mocked-HTTP properties above.

### Regression safety

The full existing suite (1297 tests) must stay green. M16 is additive: `research()` keeps its
signature and browser path; `_execute_research` is unchanged; `ResearchResult` gains only a
defaulted `beliefs` field; and no production default of `Belief`, `WorldModel`, or
`BrowserController` is altered. Target competence domains: **research** and **long_horizon**.
