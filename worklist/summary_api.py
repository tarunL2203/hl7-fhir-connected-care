
import json
import re
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit

from auth_fhir import BASE, get_json, search
from evaluator_v2 import evaluate, patient_reference

ROOT = Path(__file__).resolve().parent

def patient_observations(patient_id, policy):
    # Search exact references from the original snapshot and the current service.
    # These are query values; network requests still go only to protected 8081.
    references = ["Patient/" + patient_id] + [
        base.rstrip("/") + "/Patient/" + patient_id
        for base in policy["retrieval"]["allowed_fhir_bases"]
    ]
    records = {}
    for reference in dict.fromkeys(references):
        query = urlencode({"subject": reference})
        for observation in search("Observation?" + query, "Observation"):
            if patient_reference(observation.get("subject", {}).get("reference"), policy) != "Patient/" + patient_id:
                raise RuntimeError("Observation patient reference mismatch")
            record_id = observation["id"]
            if record_id in records and records[record_id] != observation:
                raise RuntimeError("Observation changed during reference searches")
            records[record_id] = observation
    return list(records.values())

def summary(patient_id):
    policy = json.loads((ROOT / "spec/v2/policy.json").read_text())
    assignments = json.loads(
        (ROOT / "spec/v2/visit-assignments.json").read_text()
    )["appointments"]

    patient = get_json(BASE + "/Patient/" + patient_id)
    if (
        patient.get("resourceType") != "Patient"
        or patient.get("id") != patient_id
    ):
        raise RuntimeError("Patient read-back mismatch")

    observations = patient_observations(patient_id, policy)
    appointments = [
        appointment for appointment in search("Appointment", "Appointment")
        if any(
            patient_reference(
                participant.get("actor", {}).get("reference"), policy
            ) == "Patient/" + patient_id
            for participant in appointment.get("participant", [])
        )
    ]

    assessments = []
    for appointment in appointments:
        assignment = assignments.get(appointment["id"])
        if assignment and assignment["patient_id"] != patient_id:
            raise RuntimeError("Visit assignment patient mismatch")

        case = {
            "patient_id": patient_id,
            "appointment": appointment,
            "profile_id": (
                assignment["profile_id"] if assignment else "unconfigured"
            ),
            "identity_state": "resolved",
            "retrieval_state": "complete",
            "observations": observations
        }
        assessments.append(evaluate(case, policy))

    # Open existing worklist read-only.
    db = sqlite3.connect(
        (ROOT / "data/worklist.sqlite").as_uri() + "?mode=ro",
        uri=True
    )
    db.row_factory = sqlite3.Row
    work_items = []
    try:
        for row in db.execute("SELECT * FROM items ORDER BY id"):
            payload = json.loads(row["payload"])
            if payload["patient_id"] != patient_id:
                continue
            history = [
                dict(event) for event in db.execute(
                    """SELECT action,actor,reason,at FROM history
                       WHERE item_id=? ORDER BY id""",
                    (row["id"],)
                )
            ]
            work_items.append({
                **payload,
                "id": row["id"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "history": history
            })
    finally:
        db.close()

    return {
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "supported_record_types": ["Patient", "Observation", "Appointment"],
        "patient": patient,
        "observations": observations,
        "appointments": appointments,
        "assessments": assessments,
        "work_items": work_items,
        "interpretation": policy["assessment"]["label"]
    }

class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, content):
        data = json.dumps(content, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            self.send_json(200, {"status": "running"})
            return

        match = re.fullmatch(
            r"/patients/([A-Za-z0-9.-]{1,64})/summary", path
        )
        if not match:
            self.send_json(404, {"error": "route_not_found"})
            return

        try:
            self.send_json(200, summary(match.group(1)))
        except HTTPError as error:
            self.send_json(502, {
                "error": "upstream_request_failed",
                "upstream_status": error.code,
                "assessment_completed": False
            })
        except Exception as error:
            self.send_json(502, {
                "error": "summary_not_completed",
                "detail": str(error),
                "assessment_completed": False
            })

if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8082), Handler)
    print("Summary API: http://localhost:8082", flush=True)
    print("Keep this terminal open. Ctrl+C stops this API.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
