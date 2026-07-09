# After-Milestone Review — Template (mandatory for M15+)

Copy this file to `docs/reviews/REVIEW_<milestone-id>.md` and complete it **before** starting the next
milestone. Per the approved governance rule, no milestone continues until it has demonstrated that
FRIDAY's measured competence improved or held.

> **Rule:** every milestone must improve a *measurable* capability rather than simply adding
> components. This review is the gate that enforces it.

---

## 0. Milestone under review

- Milestone: `M<n> — <name>`
- Target capability domain(s) this milestone was meant to improve: `<browser|desktop|research|coding|long_horizon>`
- Summary of what shipped (one paragraph):

## 1. Regression safety (automated)

- [ ] Full test suite green: `python -m pytest tests/friday/ -q` → `____ passed, 0 failed`
- [ ] No production default changed (unless this milestone's explicit purpose, with a rollback plan)
- [ ] Architectural invariants preserved (one Kernel / World Model / Goal Graph / Competence Model; no
      app-specific logic; no hardcoded workflows; general mechanisms)

## 2. Real-world capability benchmarks (real machine)

Run the capability benchmark suite on a real machine (see
`scripts/kernel_validation/run_capability_benchmarks.py`). Paste the `CompetenceScorecard`:

```
<paste CompetenceScorecard.to_markdown() output here>
```

- Ratchet verdict: `PASS | FAIL`
- If FAIL, list regressed domains and the root cause. **A FAIL blocks continuation.**

## 3. Competence delta

| Domain | Prev baseline | This run | Δ | Verdict |
|---|---|---|---|---|
| browser |  |  |  |  |
| desktop |  |  |  |  |
| research |  |  |  |  |
| coding |  |  |  |  |
| long_horizon |  |  |  |  |

- Did the target domain improve or hold? `yes | no`
- If a non-target domain regressed, explain and justify.

## 4. Architecture review

- Which FAS chapters / v2.1 amendments did this milestone touch or realize?
- Any new technical debt introduced? (add to the audit debt table)
- Any amendment that proved wrong or incomplete in practice? (propose a v2.x change)
- Confirm: the milestone improved a *mechanism*, not just added a component.

## 5. Decision

- [ ] **PROCEED** — competence improved/held, invariants intact, ratchet PASS → record new baseline
      (`CompetenceRatchet.record(...)`) and start the next milestone.
- [ ] **HOLD** — ratchet FAIL or regression → fix before continuing.

Reviewer / date:
