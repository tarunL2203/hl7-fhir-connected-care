"""Compare the 30-patient batch's Snowflake results with the generator's expected outcomes.

Run from the repository root:
 python analytics/compare_fc30_outcomes.py
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "datasets/fc30-failure-cases"
RESULTS = ROOT / "results/2026-10-07-30-patient-batch"


def rows(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main():
    expected = {r["appointment_id"]: r for r in rows(DATASET / "expected-outcomes.csv")}
    actual = {r["APPOINTMENT_ID"]: r for r in rows(RESULTS / "availability-by-appointment.csv")}
    failures = []
    for appointment_id, want in sorted(expected.items()):
        got = actual.get(appointment_id)
        if got is None:
            failures.append(appointment_id + ": missing from Snowflake result")
            continue
        outcome = want["expected_information_availability"]
        if got["INFORMATION_AVAILABILITY"] != outcome:
            failures.append(f"{appointment_id}: expected {outcome}, got {got['INFORMATION_AVAILABILITY']}")
        # Without a configured rule nothing is evaluated, so no results are counted as qualifying.
        count = want["expected_qualifying_glucose_count"] if outcome != "requirements_not_configured" else "0"
        if int(got["QUALIFYING_GLUCOSE_COUNT"]) != int(count):
            failures.append(f"{appointment_id}: expected {count} qualifying results, got {got['QUALIFYING_GLUCOSE_COUNT']}")
    extra = sorted(set(actual) - set(expected))
    failures += [a + ": not in the expected outcomes" for a in extra]

    expected_issues = {r["resource_id"]: r["issue"] for r in rows(DATASET / "expected-review-issues.csv")}
    flagged = {r["OBSERVATION_ID"]: r["REVIEW_REASON"] for r in rows(RESULTS / "needs-review-observations.csv")}
    if set(flagged) != set(expected_issues):
        failures.append(f"review flags differ: expected {sorted(expected_issues)}, got {sorted(flagged)}")

    if failures:
        print("\n".join("FAIL: " + f for f in failures))
        sys.exit(1)
    print(f"PASS: all {len(expected)} appointment outcomes and qualifying counts match the expected outcomes.")
    print(f"PASS: all {len(expected_issues)} deliberately broken observations were flagged for review.")


if __name__ == "__main__":
    main()
