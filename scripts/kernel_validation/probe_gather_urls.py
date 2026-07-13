"""Diagnostic: does the browserless gather return real http source URLs that
pass the hardened Evidence Law? Distinguishes DuckDuckGo throttling (no hits)
from a verification false-positive (hits present but URLs rejected).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.pop("FRIDAY_DRY_RUN", None)
try:
    from dotenv import load_dotenv
    load_dotenv()
    os.environ.pop("FRIDAY_DRY_RUN", None)
except Exception:
    pass

from friday.capabilities.web_search import gather
from friday.verification.evidence_law import (
    ExecutionEvidence, EvidenceKind, _looks_like_url,
)


def main() -> int:
    ev = ExecutionEvidence()
    result = gather("OpenAI", ev, max_sources=3)
    print("gather ok:", getattr(result, "success", None), "blocked:", getattr(result, "blocked", None))
    print("error:", getattr(result, "error", None))
    urls = getattr(result, "source_urls", [])
    print(f"raw source_urls ({len(urls)}):")
    for u in urls[:6]:
        print(f"   valid_url={_looks_like_url(u)}  {u!r}")
    real_srcs = ev.of_kind(EvidenceKind.SOURCE_URL)
    real_info = ev.of_kind(EvidenceKind.GATHERED_INFO)
    print(f"evidence: GATHERED_INFO(real)={len(real_info)}  SOURCE_URL(real)={len(real_srcs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
