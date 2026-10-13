from datetime import timedelta
from evaluator_v2 import timestamp


def build_items(case, result, policy):
    if (
        result["patient_id"] != case["patient_id"]
        or result["appointment_id"] != case["appointment"]["id"]
        or result["policy_id"] != policy["policy_id"]
    ):
        raise ValueError("Assessment identity or policy mismatch")

    if result["outcome"] in ("information_complete", "requirements_not_configured"):
        return []

    findings = []
    for requirement in result["requirements"]:
        if requirement["outcome"] == "information_gap":
            findings.append((requirement["requirement_id"], "missing_expected_record", requirement))
        elif requirement["outcome"] == "unable_to_assess":
            findings.append((requirement["requirement_id"], "invalid_required_data", requirement))

    if not findings:
        if case.get("identity_state") != "resolved":
            issue = "identity_unresolved"
        elif case.get("retrieval_state") != "complete":
            issue = "retrieval_failed"
        else:
            issue = "invalid_required_data"
        findings.append(
            ("assessment", issue, {"outcome": result["outcome"], "reason": result["reason"]})
        )

    hours = policy["work_items"]["due_time"]["demo_hours_before_appointment"]
    due = timestamp(case["appointment"]["start"]) - timedelta(hours=hours)

    items = []
    for requirement_id, issue_type, evidence in findings:
        route = policy["work_items"]["routing"][issue_type]
        items.append(
            {
                "patient_id": case["patient_id"],
                "appointment_id": case["appointment"]["id"],
                "requirement_id": requirement_id,
                "issue_type": issue_type,
                "policy_id": policy["policy_id"],
                "evidence": evidence,
                "owner_role": route["owner"],
                "permitted_action": route["action"],
                "due_at": due.isoformat(),
            }
        )
    return items


def synchronize(store, case, result, policy):
    changes = []
    for payload in build_items(case, result, policy):
        item_id, action = store.upsert(payload)
        changes.append({"item_id": item_id, "action": action})
    return changes
