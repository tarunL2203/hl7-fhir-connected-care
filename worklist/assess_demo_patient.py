"""Assess the demo patient's booked visit against the pre-visit policy and save the evidence."""
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from fhir_client import BASE, get_json, search

ROOT = Path(__file__).resolve().parent
PATIENT_ID = "demo-patient-002"


def main():
    policy = json.loads((ROOT / "spec/v2/policy.json").read_text())
    spec = importlib.util.spec_from_file_location("evaluator_v2", ROOT / "evaluator_v2.py")
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)

    patient = get_json(BASE + "/Patient/" + PATIENT_ID)
    if patient.get("resourceType") != "Patient" or patient.get("id") != PATIENT_ID:
        raise RuntimeError("Patient read-back does not match requested ID")

    appointments = search("Appointment", "Appointment")
    linked = [
        appointment
        for appointment in appointments
        if any(
            engine.patient_reference(participant.get("actor", {}).get("reference"), policy)
            == "Patient/" + PATIENT_ID
            for participant in appointment.get("participant", [])
        )
    ]
    if len(linked) != 1:
        raise RuntimeError(
            f"Expected one linked appointment; found {len(linked)}. "
            "Select the intended appointment before assessing."
        )

    query = urlencode({"subject": "Patient/" + PATIENT_ID})
    observations = search("Observation?" + query, "Observation")

    case = {
        "patient_id": PATIENT_ID,
        "appointment": linked[0],
        "profile_id": "demo-lab-review",
        "identity_state": "resolved",
        "retrieval_state": "complete",
        "observations": observations,
    }
    result = engine.evaluate(case, policy)
    now = datetime.now(timezone.utc)
    evidence = {
        "assessed_at": now.isoformat(),
        "source": BASE,
        "profile_assignment": "Explicit synthetic demo assignment",
        "input": case,
        "result": result,
    }
    output = (
        ROOT
        / "evidence"
        / ("demo-patient-assessment-" + now.strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    )
    output.write_text(json.dumps(evidence, indent=2) + "\n")

    print("Patient:", PATIENT_ID)
    print("Linked appointments:", len(linked))
    print("Observations retrieved:", len(observations))
    print("Assessment:", result["outcome"])
    print("Reason:", result["reason"])
    for requirement in result["requirements"]:
        print("Requirement:", requirement["requirement_id"])
        print("Matching records:", len(requirement["matched_record_ids"]))
    print("Evidence saved:", output.name)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Assessment not completed:", error)
        print("No missing-record conclusion was made.")
        raise SystemExit(1) from error
