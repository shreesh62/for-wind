# Requirements Document

## Introduction

M16 — Research Competence (Browserless Gather + Evidence) moves a *measured* capability. The
`research` and `long_horizon` capability-benchmark domains currently score 0.0 on a real machine,
not because the models cannot reason, but because the Operator produces no real
`GATHERED_INFO` + `SOURCE_URL` evidence for research goals — and the Evidence Law (ADR-023) rightly
refuses to satisfy a gather requirement from generated text alone.

Root cause (confirmed by investigation):

- The only web search/read path lives inside the Playwright `BrowserController.search_web`
  (`friday/actions/browser_controller.py`). `friday/capabilities/research.py::research()`
  hard-requires a live `browser_controller`; with none, it returns at the no-browser guard
  recording zero evidence.
- The capability benchmark constructs `Operator(model_router=..., max_iterations=2)` with **no**
  `browser_controller` (`scripts/kernel_validation/run_capability_benchmarks.py::_real_execute_factory`),
  so research goals gather nothing → the GATHER requirement is UNMET → `research` and
  `long_horizon` score 0.0.
- `coding` and `desktop` benchmarks pass because their evidence (`GENERATED_CONTENT` via the LLM,
  `FILE_ARTIFACT` via `FileTool`) needs no browser. Only the gather path is broken.

Feasibility (verified by live probe): a browserless search works over plain `httpx` — a
`POST https://html.duckduckgo.com/html/` with form field `q` and a normal User-Agent returns
HTTP 200 with real result markers. The search-results page itself carries snippets
(gathered info) and result links (source URLs), which alone satisfies the benchmark. Fetching
individual result pages is best-effort enrichment (some return 403 to non-browser clients and are
skipped gracefully).

This milestone delivers a browserless research/gather capability using the existing `httpx`
dependency, wires it into the research path as the no-browser fallback (preserving existing browser
behavior), and — per the M15 close-out governance note — makes gathered findings a live producer
for M15 World Model v2 beliefs (provenance from result URLs, freshness/TTL from research recency).
All network I/O is gated by `FRIDAY_DRY_RUN`; real competence gain is demonstrated only on a real
machine and recorded to `baseline.local.json` (the committed seed stays all-unmeasured). No
application-specific logic is introduced (Axiom 15); the change is additive and the full regression
suite (currently 1297 tests) must stay green.

## Glossary

- **Browserless_Gatherer**: The new capability (plain HTTP via `httpx`, no Playwright/browser) that
  runs a web search through a general search provider, extracts result snippets + result URLs,
  optionally fetches a few result pages best-effort, and records evidence.
- **Search_Provider**: A general, pluggable search backend abstraction (default: the DuckDuckGo HTML
  endpoint on host `html.duckduckgo.com`, with `lite.duckduckgo.com` as a fallback). It is framed as
  a general web-search interface, never site-specific per-page workflow branching.
- **Research_Path**: The Operator route that fulfills a research/gather goal —
  `friday/capabilities/research.py::research()` and `friday/executor.py::_execute_research`.
- **Browser_Controller**: The existing Playwright `BrowserController` whose `search_web`/`navigate`/
  `read_text` power the current browser-based research path.
- **Execution_Evidence**: `friday/verification/evidence_law.py::ExecutionEvidence`, the bundle of
  evidence artifacts an execution produces. `add_gathered_info(text, source)` records only when
  `text` is non-empty; `add_source_url(url)` records only when `url` is non-empty.
- **Evidence_Verifier**: `EvidenceVerifier`, which marks a GATHER requirement satisfied only if at
  least one real `GATHERED_INFO` artifact exists (the Evidence Law).
- **GATHERED_INFO**: An evidence artifact holding real text read from a source/search-results page.
- **SOURCE_URL**: An evidence artifact holding a URL that was actually obtained from search results
  (and optionally opened).
- **Dry_Run**: The state where the environment variable `FRIDAY_DRY_RUN` equals `"1"`. In this state
  no real network call is performed.
- **World_Model**: M15 `friday/world/world_model.py::WorldModel`, the kernel-owned belief store.
- **Belief**: M15 `friday/world/belief.py::Belief`, carrying freshness half-life, optional TTL, and
  a `BeliefProvenance` graph.
- **Belief_Provenance**: M15 `friday/world/provenance.py::BeliefProvenance`, recording supporting
  observations and derivation for a belief.
- **Capability_Benchmark**: A `research`/`long_horizon` benchmark in
  `friday/benchmarks/capability/domains.py` scored by
  `scripts/kernel_validation/run_capability_benchmarks.py`.
- **Untrusted_Content**: Any text or markup fetched from the web; treated as data only (never
  executed) and size-limited on read.

## Requirements

### Requirement 1: Browserless search over a general search provider

**User Story:** As the Operator, I want to run a web search without a browser, so that I can gather
real information when no `Browser_Controller` is available.

#### Acceptance Criteria

1. WHEN the Browserless_Gatherer receives a non-empty query AND Dry_Run is inactive, THE
   Browserless_Gatherer SHALL issue an HTTP request to the configured Search_Provider using the
   `httpx` dependency.
2. THE Browserless_Gatherer SHALL send the query to the Search_Provider host `html.duckduckgo.com`
   as an HTTP POST with the query carried in the form field named `q` and a browser-class
   User-Agent header.
3. WHEN the Search_Provider returns HTTP 200, THE Browserless_Gatherer SHALL parse the response body
   into a list of result records, where each result record contains a snippet text and a result URL.
4. IF the primary Search_Provider request returns a non-200 status OR raises a transport error,
   THEN THE Browserless_Gatherer SHALL attempt the configured fallback Search_Provider host
   `lite.duckduckgo.com` before reporting failure.
5. IF every configured Search_Provider request fails, THEN THE Browserless_Gatherer SHALL return a
   result whose success indicator is false and whose error field contains a descriptive message,
   without raising an exception to the caller.
6. THE Browserless_Gatherer SHALL select the Search_Provider through a general web-search interface
   and SHALL NOT contain per-site conditional branching keyed on a specific website or application
   name (Axiom 15).

### Requirement 2: Extract snippets and result URLs and record evidence

**User Story:** As the Operator, I want the gathered search results recorded as real evidence, so
that a GATHER requirement is satisfied honestly by information I actually collected.

#### Acceptance Criteria

1. WHEN the Browserless_Gatherer parses at least one result record with a non-empty snippet, THE
   Browserless_Gatherer SHALL record that snippet on the Execution_Evidence by calling
   `add_gathered_info` with the snippet text and the originating result URL as the source.
2. WHEN the Browserless_Gatherer parses at least one result record with a non-empty result URL, THE
   Browserless_Gatherer SHALL record that URL on the Execution_Evidence by calling `add_source_url`.
3. WHEN a research goal is executed with no Browser_Controller AND Dry_Run is inactive AND the
   Search_Provider returns at least one result record, THE Browserless_Gatherer SHALL record at
   least one `GATHERED_INFO` artifact and at least one `SOURCE_URL` artifact on the
   Execution_Evidence.
4. THE Browserless_Gatherer SHALL record only real snippet and URL text as evidence and SHALL NOT
   record model-generated text as `GATHERED_INFO`, so the Evidence Law remains the sole judge of a
   satisfied GATHER requirement.
5. WHERE a result URL is available, THE Browserless_Gatherer SHALL attempt a best-effort HTTP GET of
   that result page to enrich the gathered text.
6. IF a best-effort result-page fetch returns a non-200 status OR raises an error, THEN THE
   Browserless_Gatherer SHALL skip that page and continue processing remaining results.
7. WHEN a best-effort result-page fetch returns HTTP 200 with non-empty body text, THE
   Browserless_Gatherer SHALL record the page text on the Execution_Evidence via `add_gathered_info`
   with the fetched URL as the source.

### Requirement 3: Wire browserless gathering into the research path

**User Story:** As the Operator, I want the research path to gather real info even without a
browser, so that the `research` and `long_horizon` benchmarks become satisfiable end-to-end.

#### Acceptance Criteria

1. WHEN the Research_Path executes a research goal AND no Browser_Controller is available, THE
   Research_Path SHALL route the goal to the Browserless_Gatherer.
2. WHERE a Browser_Controller is available, THE Research_Path SHALL preserve the existing
   browser-based research behavior.
3. THE Research_Path SHALL leave the public signatures of `research()` and `_execute_research`
   backward compatible so existing callers require no change.
4. WHEN the Browserless_Gatherer records at least one `GATHERED_INFO` artifact and at least one
   `SOURCE_URL` artifact, THE Evidence_Verifier SHALL mark the corresponding GATHER requirement
   satisfied.
5. THE M16 changes SHALL be additive and SHALL NOT change any production default of the existing
   `Belief`, `WorldModel`, or Browser_Controller research APIs.

### Requirement 4: Respect dry-run and treat fetched content as untrusted

**User Story:** As a maintainer, I want the gatherer to be network-safe in tests and defensive with
web content, so that the suite makes no live calls and fetched markup cannot harm the system.

#### Acceptance Criteria

1. WHILE Dry_Run is active, THE Browserless_Gatherer SHALL perform no real network request.
2. WHILE Dry_Run is active AND a research goal is executed, THE Browserless_Gatherer SHALL return a
   result without contacting any Search_Provider or result page.
3. THE Browserless_Gatherer SHALL treat all fetched web content as Untrusted_Content, using it only
   as data and never executing it.
4. THE Browserless_Gatherer SHALL limit the number of characters read from any single fetched
   response to a bounded maximum.
5. THE Browserless_Gatherer SHALL limit the number of result pages it fetches best-effort to a
   bounded maximum per research goal.

### Requirement 5: Produce M15 World Model v2 beliefs from gathered findings

**User Story:** As the World_Model, I want gathered findings to become beliefs with provenance and
freshness, so that M15's freshness/provenance mechanism finally has a real producer.

#### Acceptance Criteria

1. WHEN the Browserless_Gatherer records gathered findings for a research goal, THE Research_Path
   SHALL produce at least one Belief representing a gathered finding.
2. WHEN a Belief is produced from a gathered finding, THE Research_Path SHALL attach each supporting
   result URL to the Belief as a supporting observation in its Belief_Provenance.
3. WHEN a Belief is produced from a gathered finding, THE Research_Path SHALL set the Belief
   freshness parameters to reflect research recency at the time of gathering.
4. THE production of beliefs from gathered findings SHALL be additive and present by default in the
   Research_Path, while leaving the M15 `Belief` and `WorldModel` public APIs unchanged.
5. WHILE Dry_Run is active, THE Research_Path SHALL still be able to produce beliefs from gathered
   findings supplied by mocked results, without performing any real network request.

### Requirement 6: Measured competence gain, honestly recorded

**User Story:** As the project owner, I want the research and long_horizon benchmarks to become
passable on a real machine, so that this milestone moves a measured capability without fabrication.

#### Acceptance Criteria

1. WHEN the `research.gather_with_sources` Capability_Benchmark is executed on a real machine with
   the Browserless_Gatherer wired in, THE Research_Path SHALL produce the `GATHERED_INFO` and
   `SOURCE_URL` evidence the benchmark requires.
2. WHEN the `research.produce_cited_summary` Capability_Benchmark is executed on a real machine, THE
   Research_Path SHALL make `GATHERED_INFO`, `SOURCE_URL`, and `GENERATED_CONTENT` all obtainable.
3. WHEN the `long_horizon.research_to_document` Capability_Benchmark is executed on a real machine,
   THE Research_Path SHALL make its research-derived evidence obtainable end-to-end.
4. WHEN capability benchmarks are scored on a real machine, THE scoring process SHALL record real
   `research` and `long_horizon` domain scores to `baseline.local.json`.
5. THE committed baseline seed SHALL remain all-unmeasured and SHALL NOT be overwritten with
   machine-specific scores.

### Requirement 7: Regression safety and network-free tests

**User Story:** As a maintainer, I want new tests to cover the gatherer with mocked HTTP, so that
the full suite stays green and never makes live calls.

#### Acceptance Criteria

1. THE M16 test additions SHALL reside in new test files and SHALL mock the HTTP layer so no real
   network call occurs during the suite.
2. WHEN the full regression suite is executed, THE suite SHALL pass with no failures, preserving the
   existing green baseline.
3. THE existing guard test `test_no_site_names_in_source` and equivalent no-hardcoding guards SHALL
   continue to pass against the M16 source.
4. WHEN a test supplies a mocked HTTP 200 search response with at least one result to the
   Browserless_Gatherer, THE Browserless_Gatherer SHALL record at least one `GATHERED_INFO` artifact
   and at least one `SOURCE_URL` artifact.
5. WHEN a test supplies a mocked HTTP 403 or transport error for a result-page fetch, THE
   Browserless_Gatherer SHALL skip that page and complete without raising.

## Property-to-Requirement Mapping

This milestone is testable with mocked-HTTP unit and property tests. The table maps each testable
property to its correctness-pattern category, the requirement it verifies, and the intended test
approach.

| # | Property | Pattern category | Requirements | Test approach |
|---|----------|------------------|--------------|---------------|
| P1 | Search-results parsing extracts a result record (snippet + URL) for every result marker in a mocked 200 body; no result markers ⇒ empty result list | Metamorphic (`len(results) <= len(markers)`) + Model-based | 1.3, 2.1, 2.2 | Property test over generated mock HTML bodies with N synthetic result blocks; assert parsed count and that each record has snippet+URL |
| P2 | Given a mocked 200 search response with ≥1 result and no browser, evidence has ≥1 `GATHERED_INFO` and ≥1 `SOURCE_URL` | Invariant | 2.3, 3.1, 3.4, 7.4 | Unit + property test with mocked `httpx`; assert `evidence.of_kind(GATHERED_INFO)` and `of_kind(SOURCE_URL)` non-empty |
| P3 | Generated/model text never appears as `GATHERED_INFO`; only real snippet/page text does | Invariant (Evidence Law) | 2.4, 3.4 | Unit test: run gatherer with mocked results, assert every `GATHERED_INFO` source traces to a result/page URL, not the LLM |
| P4 | Under `FRIDAY_DRY_RUN=1`, zero network calls are made for any query | Invariant | 4.1, 4.2, 5.5 | Property test over arbitrary queries with a spy `httpx` client; assert call count == 0 |
| P5 | Primary-provider failure falls back to the secondary host; total failure yields success=false with a message and no exception | Error conditions + Confluence (host order) | 1.4, 1.5 | Unit tests with mocked 200/non-200/exception sequences across both hosts |
| P6 | Best-effort page fetch returning 403 or raising is skipped; the run still completes and prior evidence is retained | Error conditions | 2.6, 7.5 | Unit test: mock search 200 + page 403/exception; assert no raise and search-page evidence intact |
| P7 | Best-effort page fetch returning 200 adds `GATHERED_INFO` sourced to the fetched URL | Metamorphic (`gathered_after >= gathered_before`) | 2.5, 2.7 | Unit test with mocked 200 page body; assert gathered-info count increases with the page URL as source |
| P8 | Characters read from any single response are bounded; pages fetched per goal are bounded | Invariant | 4.4, 4.5 | Property test with oversized mock bodies / many results; assert recorded length ≤ cap and fetch count ≤ cap |
| P9 | No site/app name conditional branches exist in the M16 source | Invariant (static guard) | 1.6, 7.3 | Extend `test_no_site_names_in_source`-style static scan over the new module |
| P10 | A gathered finding produces ≥1 Belief whose provenance supporting observations include the result URL(s), with freshness set for recency | Round-trip / Invariant | 5.1, 5.2, 5.3, 5.4 | Property test: feed mocked findings, assert produced Belief provenance contains the source URLs and freshness params set |
| P11 | With a Browser_Controller present, the existing browser research behavior is unchanged (same evidence path as before) | Model-based (parity) | 3.2, 3.3, 3.5 | Unit test comparing browser-path evidence with and without M16 wiring using a fake browser |
| P12 | Existing `research()` / `_execute_research` signatures accept prior call shapes unchanged | Invariant (backward compat) | 3.3 | Unit test invoking the functions with the legacy argument shape |

Note on scope: the real-machine competence gain (Requirement 6) is a live-only measurement and is
NOT asserted by the suite — it is recorded to `baseline.local.json` on a real machine, per the
project's honesty rule. The benchmark harness treats `research`/`long_horizon` as `requires_live`
and skips them under `FRIDAY_DRY_RUN`.
