
import math
from datetime import datetime, timedelta
from urllib.parse import urlsplit

def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Missing timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp requires timezone")
    return parsed

def patient_reference(reference, policy):
    if not isinstance(reference, str):
        return None
    if reference.startswith("Patient/") and len(reference.split("/")) == 2:
        return reference
    for base in policy["retrieval"]["allowed_fhir_bases"]:
        prefix = base.rstrip("/") + "/"
        if reference.startswith(prefix):
            relative = reference[len(prefix):]
            parsed = urlsplit(relative)
            if (
                not parsed.query and not parsed.fragment
                and relative.startswith("Patient/")
                and len(relative.split("/")) == 2
            ):
                return relative
    return None

def evaluate(case, policy):
    result = {
        "policy_id": policy["policy_id"],
        "patient_id": case["patient_id"],
        "appointment_id": case["appointment"]["id"],
        "outcome": None,
        "reason": None,
        "requirements": [],
        "interpretation": policy["assessment"]["label"]
    }

    def finish(outcome, reason):
        result["outcome"] = outcome
        result["reason"] = reason
        return result

    profile = policy["visit_profiles"].get(case.get("profile_id"))
    if not profile:
        return finish(
            policy["assessment"]["no_matching_visit_profile"],
            "No configured requirements for this visit profile"
        )
    if not profile.get("requirements"):
        return finish(
            policy["assessment"]["no_matching_visit_profile"],
            "Visit profile has no requirements"
        )

    if case.get("identity_state") != "resolved":
        return finish(
            policy["assessment"]["unresolved_identity"],
            "Patient identity mapping is unresolved"
        )

    expected_ref = "Patient/" + case["patient_id"]
    participants = case["appointment"].get("participant", [])
    linked = any(
        patient_reference(
            p.get("actor", {}).get("reference"), policy
        ) == expected_ref
        for p in participants
    )
    if not linked:
        return finish("unable_to_assess", "Appointment patient link is unresolved")

    if case.get("retrieval_state") != "complete":
        return finish(
            policy["assessment"]["retrieval_failed_or_incomplete"],
            "Retrieval failed or not all search pages were retrieved"
        )

    try:
        visit_time = timestamp(case["appointment"].get("start"))
    except (ValueError, TypeError):
        return finish("unable_to_assess", "Appointment start is missing or invalid")

    observations = case.get("observations")
    if not isinstance(observations, list):
        return finish("unable_to_assess", "Observation response is invalid")

    for requirement in profile["requirements"]:
        if requirement["resource_type"] != "Observation":
            raise ValueError("This evaluator currently supports Observation requirements")

        start = visit_time - timedelta(days=requirement["lookback_days"])
        matched = []
        rejected = []
        uncertain = []

        for observation in observations:
            record_id = observation.get("id", "(missing ID)")
            coding = observation.get("code", {}).get("coding", [])
            matches_code = any(
                c.get("system") == requirement["code"]["system"]
                and c.get("code") == requirement["code"]["code"]
                for c in coding
            )
            if not matches_code:
                continue

            reference = patient_reference(
                observation.get("subject", {}).get("reference"), policy
            )
            if reference is None:
                uncertain.append({"id": record_id, "reason": "Unresolved patient reference"})
                continue
            if reference != expected_ref:
                rejected.append({"id": record_id, "reason": "Different patient"})
                continue

            if observation.get("status") not in requirement["accepted_statuses"]:
                rejected.append({"id": record_id, "reason": "Status not accepted"})
                continue

            try:
                result_time = timestamp(observation.get(requirement["date_field"]))
            except (ValueError, TypeError):
                uncertain.append({"id": record_id, "reason": "Missing or invalid result date"})
                continue

            after_start = (
                result_time >= start if requirement["start_inclusive"]
                else result_time > start
            )
            before_end = (
                result_time <= visit_time if requirement["end_inclusive"]
                else result_time < visit_time
            )
            if not (after_start and before_end):
                rejected.append({"id": record_id, "reason": "Outside configured window"})
                continue

            quantity = observation.get("valueQuantity", {})
            value = quantity.get("value")
            numeric = (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
            )
            unit = quantity.get("unit") or quantity.get("code")
            if requirement["require_numeric_value"] and not numeric:
                uncertain.append({"id": record_id, "reason": "Missing or invalid numeric value"})
                continue
            if requirement["require_unit"] and (
                not isinstance(unit, str) or not unit.strip()
            ):
                uncertain.append({"id": record_id, "reason": "Missing unit"})
                continue

            matched.append(record_id)

        # Conservative demo policy: relevant unresolved data blocks completion.
        if uncertain:
            outcome = policy["assessment"]["invalid_required_data"]
        elif matched:
            outcome = policy["assessment"]["all_requirements_satisfied"]
        else:
            outcome = policy["assessment"]["successful_search_without_qualifying_record"]

        result["requirements"].append({
            "requirement_id": requirement["requirement_id"],
            "outcome": outcome,
            "window_start": start.isoformat(),
            "window_end": visit_time.isoformat(),
            "matched_record_ids": matched,
            "rejected_records": rejected,
            "uncertain_records": uncertain
        })

    outcomes = [r["outcome"] for r in result["requirements"]]
    if "unable_to_assess" in outcomes:
        return finish("unable_to_assess", "Relevant data could not be assessed")
    if "information_gap" in outcomes:
        return finish("information_gap", "A configured requirement has no qualifying record")
    return finish("information_complete", "All configured requirements satisfied")
