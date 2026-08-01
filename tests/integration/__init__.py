"""Integration tests — real end-to-end pipeline verification.

Unlike the unit tests (which mock dependencies and verify contracts), these tests
drive the REAL system through its public surfaces with REAL model calls (or the
real deterministic fallback) and verify OBSERVABLE outcomes: files on disk, evidence
artifacts, recalled memory, withheld actions, correct routing.

Run them with:
    python -m pytest tests/integration -q

They are slower than unit tests (seconds, not milliseconds) because they exercise
real subsystems. They are NOT network-dependent by default — DRY_RUN is NOT set,
but they don't require browser/LLM unless explicitly marked.
"""
