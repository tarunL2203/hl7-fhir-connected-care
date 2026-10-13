"""Convert a supported HL7 v2 ADT^A01 admission into a FHIR R4 Patient.

The patient is matched in the source FHIR server by MRN identifier, never by name.
Usage: python converters/convert_admission.py <message.hl7>  (writes <message>.fhir.json)
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import NAMESPACE_URL, uuid5

from hl7apy.parser import parse_message

FHIR_SOURCE_URL = os.environ.get("FHIR_SOURCE_URL", "http://localhost:8080").rstrip("/")
MRN_SYSTEM = "https://example.org/training/mrn"
ASSIGNING_AUTHORITY = "DEMO"
GENDER_CODES = {"M": "male", "F": "female", "O": "other", "U": "unknown"}


def find_patients(system, identifier):
    """Return the search Bundle of Patients carrying this identifier (at most two entries)."""
    query = urlencode({"identifier": system + "|" + identifier, "_count": "2"})
    request = Request(
        FHIR_SOURCE_URL + "/Patient?" + query,
        headers={"Accept": "application/fhir+json; fhirVersion=4.0"},
    )
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def convert(raw_message, search=find_patients):
    """Return the FHIR Patient for one supported ADT^A01 message, or raise ValueError."""
    message = parse_message(raw_message, find_groups=False)
    if message.msh.msh_9.to_er7() != "ADT^A01^ADT_A01":
        raise ValueError("Only ADT^A01 admission messages are supported.")

    pid = message.pid
    if pid.pid_3.cx_4.to_er7() != ASSIGNING_AUTHORITY:
        raise ValueError("Only the DEMO identifier authority is configured.")

    identifier = pid.pid_3.cx_1.to_er7()
    family = pid.pid_5.xpn_1.fn_1.to_er7()
    given = pid.pid_5.xpn_2.to_er7()
    if not all([identifier, family, given]):
        raise ValueError("Required patient details are missing.")

    bundle = search(MRN_SYSTEM, identifier)
    matches = [
        entry["resource"]
        for entry in bundle.get("entry", [])
        if entry.get("resource", {}).get("resourceType") == "Patient"
    ]
    if len(matches) > 1 or bundle.get("total", 0) > 1:
        raise ValueError("Duplicate identifier: review before continuing.")

    patient_id = (
        matches[0]["id"]
        if matches
        else "patient-" + str(uuid5(NAMESPACE_URL, MRN_SYSTEM + "|" + identifier))
    )
    return {
        "resourceType": "Patient",
        "id": patient_id,
        "identifier": [{"system": MRN_SYSTEM, "value": identifier}],
        "name": [{"family": family, "given": [given]}],
        "birthDate": datetime.strptime(pid.pid_7.to_er7(), "%Y%m%d").date().isoformat(),
        "gender": GENDER_CODES[pid.pid_8.to_er7()],
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: python converters/convert_admission.py <message.hl7>")
    source = Path(sys.argv[1])
    patient = convert(source.read_bytes().decode())
    output = source.with_suffix(".fhir.json")
    output.write_text(json.dumps(patient, indent=2) + "\n", encoding="utf-8")
    print("Saved:", output)
    print(json.dumps(patient, indent=2))


if __name__ == "__main__":
    main()
