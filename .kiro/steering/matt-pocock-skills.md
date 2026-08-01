---
description: Matt Pocock's engineering skills — grilling for shared understanding, TDD red-green loop, and token-efficient communication. Small, composable practices for disciplined development.
---

# Matt Pocock's Skills

## Grilling (Stress-Test Plans)

When the user wants to build something non-trivial, or says "grill me", "stress test this", or presents a plan:

- Interview relentlessly about every aspect until reaching shared understanding
- Walk down each branch of the decision tree, resolving dependencies one-by-one
- For each question, provide a recommended answer
- Ask questions ONE AT A TIME — multiple questions at once is bewildering
- If a fact can be found by exploring the environment (filesystem, tools), look it up rather than asking
- Decisions are the user's — put each one to them and wait
- Do not act until the user confirms shared understanding is reached

## Test-Driven Development

When building features or fixing bugs test-first:

**What a good test is:**
- Tests verify behavior through public interfaces, not implementation details
- A good test reads like a specification and survives refactors
- Tests live at seams (public boundaries), never against internals

**Anti-patterns to avoid:**
- Implementation-coupled: mocks internals, tests private methods, breaks on refactor when behavior hasn't changed
- Tautological: assertion recomputes expected value the same way code does
- Horizontal slicing: writing all tests first then all implementation — work in vertical slices instead

**Rules of the loop:**
- Red before green — write the failing test first, then only enough code to pass it
- One slice at a time — one seam, one test, one minimal implementation per cycle
- Refactoring belongs to review, not the red-green implementation cycle

## Caveman Mode (Token Efficiency)

When the user says "caveman mode", "less tokens", "be brief":
- Drop filler, articles, pleasantries
- Keep full technical accuracy
- Cut output tokens ~75%
- Code, commands, and errors stay byte-for-byte exact
- Only prose gets compressed
