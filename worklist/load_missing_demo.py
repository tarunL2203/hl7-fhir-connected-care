
import copy
import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request
from pathlib import Path
from assess_ravi import BASE, get_json, search, opener

ROOT = Path(__file__).resolve().parent

def normalize(resource):
    value = copy.deepcopy(resource)
    meta = value.get("meta", {})
    meta.pop("versionId", None)
    meta.pop("lastUpdated", None)
    if not meta:
        value.pop("meta", None)

    def walk(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if key == "reference" and isinstance(child, str):
                    prefix = BASE + "/"
                    if child.startswith(prefix):
                        item[key] = child[len(prefix):]
                else:
                    walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
    walk(value)
    return value

def main():
    fixtures = json.loads(
        (ROOT / "fixtures/v2/assessment-fixtures.json").read_text()
    )
    patient = next(
        p for p in fixtures["patients"] if p["id"] == "fixture-v2-p02"
    )
    appointment = next(
        a for a in fixtures["appointments"] if a["id"] == "fixture-v2-a02"
    )
    resources = [patient, appointment]
    missing = []

    # Preflight both resources before creating either.
    for resource in resources:
        endpoint = BASE + "/" + resource["resourceType"] + "/" + resource["id"]
        try:
            existing = get_json(endpoint)
        except HTTPError as error:
            if error.code != 404:
                raise
            missing.append(resource)
        else:
            if normalize(existing) != normalize(resource):
                raise RuntimeError("Existing resource differs: " + resource["id"])

    query = urlencode({"subject": "Patient/" + patient["id"]})
    if search("Observation?" + query, "Observation"):
        raise RuntimeError("This missing-result demo already has observations")

    for resource in missing:
        endpoint = BASE + "/" + resource["resourceType"] + "/" + resource["id"]
        request = Request(
            endpoint,
            data=json.dumps(resource).encode(),
            method="PUT",
            headers={
                "Content-Type": "application/fhir+json",
                "Accept": "application/fhir+json",
                "If-None-Match": "*"
            }
        )
        with opener.open(request, timeout=60) as response:
            if response.status not in (200, 201):
                raise RuntimeError("Unexpected write response")
            response.read()

    for resource in resources:
        saved = get_json(
            BASE + "/" + resource["resourceType"] + "/" + resource["id"]
        )
        if normalize(saved) != normalize(resource):
            raise RuntimeError("Read-back mismatch: " + resource["id"])
        print("Verified:", resource["resourceType"] + "/" + resource["id"])

    print("Resources created this run:", len(missing))
    print("Demo patient observations: 0")

if __name__ == "__main__":
    main()
