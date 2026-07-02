"""Query extraction — turn a goal into a focused search query.

The fallback planner previously used the ENTIRE goal string as the search
query, so "research best gaming laptop and make a spreadsheet" was typed
verbatim into the search engine. That is not how a human searches — they
search the TOPIC ("best gaming laptop"), not the instruction.

This module strips:
- leading action verbs ("research", "find", "look up", "search for")
- trailing output/delivery clauses ("and make a spreadsheet", "then save
  it as a docx", "and email it to ...")
so the planner searches the actual subject of interest.

Pure string logic — no LLM. The LLM decomposer remains the primary path;
this only improves the no-LLM fallback so it stops searching whole sentences.
"""

from __future__ import annotations

import re

# Verbs that typically begin a goal and are not part of the search topic.
_LEADING_VERBS = (
    "research", "find", "search for", "search", "look up", "look for",
    "find out", "get me", "get", "tell me about", "tell me", "show me",
    "give me", "i want to know about", "i want", "please",
)

# Clause markers that introduce OUTPUT / DELIVERY actions, not the topic.
# Everything from the first marker onward is dropped from the query.
_OUTPUT_MARKERS = (
    " and make ", " and create ", " and write ", " and build ",
    " and save ", " and store ", " and put ", " and generate ",
    " and compile ", " and prepare ", " and produce ", " and draft ",
    " then make ", " then create ", " then write ", " then save ",
    " then email ", " then send ", " and email ", " and send ",
    " and compare ", " into a ", " as a spreadsheet", " as a document",
    " in a spreadsheet", " in a document", " in a file",
    " make a ", " create a ", " save it", " save them", " save as",
    " write a ", " compile into ", " put it in ", " put them in ",
)


def extract_search_query(goal_text: str) -> str:
    """Return a focused search query from a goal.

    Examples:
        "research best gaming laptop and make a spreadsheet" -> "best gaming laptop"
        "find the top 5 ML papers and save to a file"        -> "the top 5 ML papers"
        "look up France's GDP and email it"                  -> "France's GDP"
        "weather in Tokyo"                                    -> "weather in Tokyo"
    """
    if not goal_text:
        return ""

    q = goal_text.strip()
    lowered = q.lower()

    # 1. Cut at the first output/delivery marker.
    cut_at = len(q)
    for marker in _OUTPUT_MARKERS:
        idx = lowered.find(marker)
        if idx != -1 and idx < cut_at:
            cut_at = idx
    q = q[:cut_at].strip()
    lowered = q.lower()

    # 2. Strip a leading action verb.
    for verb in sorted(_LEADING_VERBS, key=len, reverse=True):
        if lowered.startswith(verb + " "):
            q = q[len(verb):].strip()
            lowered = q.lower()
            break

    # 3. Tidy up trailing conjunctions/punctuation.
    q = re.sub(r"[\s,;:.]+$", "", q).strip()
    q = re.sub(r"\s+(and|then|to)$", "", q, flags=re.IGNORECASE).strip()

    # 4. Never return empty — fall back to the original goal.
    return q or goal_text.strip()
