
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from assess_ravi import BASE, get_json, search
from evaluator_v2 import evaluate, patient_reference
from worklist_bridge import synchronize
from worklist_store import WorklistStore

ROOT = Path(__file__).resolve().parent
PATIENT_ID = "fixture-v2-p02"
APPOINTMENT_ID = "fixture-v2-a02"

def main():
    policy = json.loads((ROOT / "spec/v2/policy.json").read_text())

    patient = get_json(BASE + "/Patient/" + PATIENT_ID)
    appointment = get_json(BASE + "/Appointment/" + APPOINTMENT_ID)

    if (
        patient.get("resourceType") != "Patient"
        or patient.get("id") != PATIENT_ID
        or appointment.get("resourceType") != "Appointment"
        or appointment.get("id") != APPOINTMENT_ID
    ):
        raise RuntimeError("Requested records did not match read-back")

    linked = any(
        patient_reference(p.get("actor", {}).get("reference"), policy)
        == "Patient/" + PATIENT_ID
        for p in appointment.get("participant", [])
    )
    if not linked:
        raise RuntimeError("Appointment patient link does not match")

    query = urlencode({"subject": "Patient/" + PATIENT_ID})
    observations = search("Observation?" + query, "Observation")

    case = {
        "patient_id": PATIENT_ID,
        "appointment": appointment,
        "profile_id": "demo-lab-review",
        "identity_state": "resolved",
        "retrieval_state": "complete",
        "observations": observations
    }
    result = evaluate(case, policy)
    assessed_at = datetime.now(timezone.utc)

    # Save assessment evidence before changing the worklist.
    path = ROOT / "evidence" / (
        "missing-demo-assessment-"
        + assessed_at.strftime("%Y%m%dT%H%M%S%fZ") + ".json"
    )
    path.write_text(json.dumps({
        "assessed_at": assessed_at.isoformat(),
        "source": BASE,
        "profile_assignment": "Explicit synthetic demo assignment",
        "input": case,
        "result": result
    }, indent=2) + "\n")

    store = WorklistStore(ROOT / "data/worklist.sqlite")
    try:
        changes = synchronize(store, case, result, policy)
        print("Patient:", PATIENT_ID)
        print("Observations retrieved:", len(observations))
        print("Assessment:", result["outcome"])
        for change in changes:
            print("Work item action:", change["action"])
        count = store.db.execute(
            "SELECT COUNT(*) FROM items WHERE appointment_id=?",
            (APPOINTMENT_ID,)
        ).fetchone()[0]
        print("Saved items for this appointment:", count)
        print("Evidence saved:", path.name)
    finally:
        store.close()

if __name__ == "__main__":
    main()
