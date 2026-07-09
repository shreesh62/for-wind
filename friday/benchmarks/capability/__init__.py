"""M14 — capability-level benchmarks over the M11 primitives.

Measurable, evidence-scored, domain-general acceptance tests for the five
capability domains (browser, desktop, research, coding, long-horizon) plus a
competence ratchet that gates regressions. Benchmarks measure *capability*, not
a specific application: no app/site names, no hardcoded workflows (Axiom 15).
"""

from friday.benchmarks.capability.domains import (
    CapabilityBenchmark,
    all_domain_suites,
    browser_suite,
    coding_suite,
    desktop_suite,
    long_horizon_suite,
    research_suite,
)
from friday.benchmarks.capability.scoring import score_benchmark, score_domain
from friday.benchmarks.capability.ratchet import (
    CompetenceRatchet,
    CompetenceScorecard,
    DomainScore,
    RatchetVerdict,
)

__all__ = [
    "CapabilityBenchmark",
    "browser_suite",
    "desktop_suite",
    "research_suite",
    "coding_suite",
    "long_horizon_suite",
    "all_domain_suites",
    "score_benchmark",
    "score_domain",
    "CompetenceRatchet",
    "CompetenceScorecard",
    "DomainScore",
    "RatchetVerdict",
]
