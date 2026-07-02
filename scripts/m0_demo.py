"""M0 demonstration — prove false completion is now impossible.

Runs the exact Truth Report failure case ("Research laptops and create a
summary") with NO browser available, and prints the per-requirement verdicts.

BEFORE M0: operator reported completed=True with research "satisfied" by
generated text, even though search and read both failed.

AFTER M0: the gather/research requirement must report UNMET with an honest
reason, because no information was actually gathered.
"""

from friday.operator import Operator
from friday.verification.evidence_law import classify_requirement


def main() -> None:
    goal = "Research laptops and create a summary"
    print("=" * 70)
    print(f"GOAL: {goal}")
    print("Environment: NO browser, NO model router (search/read cannot happen)")
    print("=" * 70)

    operator = Operator(model_router=None, browser_controller=None)
    outcome = operator.run(goal)

    print(f"\ncompleted        : {outcome.completed}")
    print(f"completion_ratio : {outcome.completion_ratio:.2f}")
    print(f"requirements_met : {outcome.requirements_met}/{outcome.requirements_total}")
    print(f"created_files    : {outcome.created_files}")

    print("\nPer-requirement verdicts:")
    for r in operator._discovery.discover(goal).requirements:
        kind = classify_requirement(r.description)
        print(f"  [{kind.value:8}] {r.description}")

    print("\nEvidence artifacts collected during execution:")
    # Re-run executor evidence is inside the trace; show the trace tail.
    for line in outcome.trace:
        print(f"  {line}")

    print("\n" + "=" * 70)
    if outcome.completed:
        print("RESULT: completed=True")
        print("⚠️  If a gather requirement was blocking, this would be a FALSE")
        print("    SUCCESS. Check that research is reported UNMET above.")
    else:
        print("RESULT: completed=False - honest. Research could not be satisfied")
        print("        without real gathered information. NO false success. [OK]")
    print("=" * 70)


if __name__ == "__main__":
    main()
