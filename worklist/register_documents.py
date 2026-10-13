import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request
from fhir_client import BASE, get_json, opener
from load_missing_demo import normalize

ROOT = Path(__file__).resolve().parent


def main():
    config = json.loads((ROOT / "spec/v2/document-storage.json").read_text())
    patient = get_json(BASE + "/Patient/" + config["patient_id"])
    if patient.get("id") != config["patient_id"]:
        raise RuntimeError("Patient read-back mismatch")

    resources = []
    for document in config["documents"]:
        object_url = (
            "https://"
            + config["bucket"]
            + ".s3."
            + config["region"]
            + ".amazonaws.com/"
            + document["key"]
        )
        resources.append(
            {
                "resourceType": "DocumentReference",
                "id": document["document_reference_id"],
                "status": "current",
                "type": {"text": "Synthetic training document"},
                "description": "Training data only; not a clinical report or medical scan",
                "identifier": [
                    {
                        "system": "urn:demo:s3-object-location",
                        "value": "s3://" + config["bucket"] + "/" + document["key"],
                    }
                ],
                "subject": {"reference": "Patient/" + config["patient_id"]},
                "content": [
                    {
                        "attachment": {
                            "contentType": document["content_type"],
                            "url": object_url,
                            "size": document["size_bytes"],
                            "title": document["filename"],
                        }
                    }
                ],
            }
        )

    missing = []
    for resource in resources:
        endpoint = BASE + "/DocumentReference/" + resource["id"]
        try:
            saved = get_json(endpoint)
        except HTTPError as error:
            if error.code != 404:
                raise
            missing.append(resource)
        else:
            if normalize(saved) != normalize(resource):
                raise RuntimeError("Existing document reference differs: " + resource["id"])

    for resource in missing:
        request = Request(
            BASE + "/DocumentReference/" + resource["id"],
            data=json.dumps(resource).encode(),
            method="PUT",
            headers={
                "Content-Type": "application/fhir+json",
                "Accept": "application/fhir+json",
                "If-None-Match": "*",
            },
        )
        with opener.open(request, timeout=60) as response:
            if response.status not in (200, 201):
                raise RuntimeError("Unexpected write response")
            response.read()

    for resource in resources:
        saved = get_json(BASE + "/DocumentReference/" + resource["id"])
        if normalize(saved) != normalize(resource):
            raise RuntimeError("Document reference read-back mismatch")
        print("Verified:", resource["id"])

    print("DocumentReferences created this run:", len(missing))


if __name__ == "__main__":
    main()
