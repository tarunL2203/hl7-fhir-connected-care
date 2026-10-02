
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import (
    Request, HTTPRedirectHandler, build_opener
)

ROOT = Path.home() / "firely-learning/worklist"
BASE = "http://localhost:8081"
PATIENT_ID = "demo-patient-002"

def allowed(url):
    parsed = urlsplit(url)
    return (
        parsed.scheme == "http"
        and parsed.netloc == "localhost:8081"
        and not parsed.username
        and not parsed.password
    )

class LocalRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed(newurl):
            raise RuntimeError("Redirect outside local Firely blocked")
        return super().redirect_request(req, fp, code, msg, headers, newurl)

opener = build_opener(LocalRedirects())

def get_json(url):
    if not allowed(url):
        raise RuntimeError("Request outside local Firely blocked")
    request = Request(
        url, headers={"Accept": "application/fhir+json"}
    )
    with opener.open(request, timeout=60) as response:
        return json.load(response)

def search(path, resource_type):
    url = BASE + "/" + path
    visited = set()
    records = {}

    while url:
        if url in visited:
            raise RuntimeError("Repeated pagination link")
        visited.add(url)
        bundle = get_json(url)

        if (
            bundle.get("resourceType") != "Bundle"
            or bundle.get("type") != "searchset"
        ):
            raise RuntimeError("Invalid search response")

        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "OperationOutcome":
                raise RuntimeError("Search returned an OperationOutcome; inspect before assessing")
            if resource.get("resourceType") == resource_type:
                records[resource["id"]] = resource

        next_links = [
            link["url"] for link in bundle.get("link", [])
            if link.get("relation") == "next"
        ]
        if len(next_links) > 1:
            raise RuntimeError("Ambiguous pagination links")
        url = urljoin(url, next_links[0]) if next_links else None

    return list(records.values())

def main():
    policy = json.loads((ROOT / "spec/v2/policy.json").read_text())
    spec = importlib.util.spec_from_file_location(
        "evaluator_v2", ROOT / "evaluator_v2.py"
    )
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)

    patient = get_json(BASE + "/Patient/" + PATIENT_ID)
    if (
        patient.get("resourceType") != "Patient"
        or patient.get("id") != PATIENT_ID
    ):
        raise RuntimeError("Patient read-back does not match requested ID")

    appointments = search("Appointment", "Appointment")
    linked = [
        appointment for appointment in appointments
        if any(
            engine.patient_reference(
                participant.get("actor", {}).get("reference"), policy
            ) == "Patient/" + PATIENT_ID
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
        "observations": observations
    }
    result = engine.evaluate(case, policy)
    now = datetime.now(timezone.utc)
    evidence = {
        "assessed_at": now.isoformat(),
        "source": BASE,
        "profile_assignment": "Explicit synthetic demo assignment",
        "input": case,
        "result": result
    }
    output = ROOT / "evidence" / (
        "ravi-assessment-" + now.strftime("%Y%m%dT%H%M%S%fZ") + ".json"
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
        raise SystemExit(1)
