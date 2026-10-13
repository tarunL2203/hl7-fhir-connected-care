import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid5, NAMESPACE_URL
from hl7apy.parser import parse_message

source = Path(sys.argv[1])
message = parse_message(source.read_bytes().decode(), find_groups=False)
if message.msh.msh_9.to_er7() != "ADT^A01^ADT_A01":
    raise ValueError("Only our ADT admission examples are supported.")

pid = message.pid
if pid.pid_3.cx_4.to_er7() != "DEMO":
    raise ValueError("Only the DEMO identifier authority is configured.")

system = "https://example.org/training/mrn"
identifier = pid.pid_3.cx_1.to_er7()
family = pid.pid_5.xpn_1.fn_1.to_er7()
given = pid.pid_5.xpn_2.to_er7()
if not all([identifier, family, given]):
    raise ValueError("Required patient details are missing.")

query = urlencode({"identifier": system + "|" + identifier, "_count": "2"})
request = Request(
    "http://localhost:8080/Patient?" + query,
    headers={"Accept": "application/fhir+json; fhirVersion=4.0"}
)
with urlopen(request, timeout=10) as response:
    bundle = json.load(response)
matches = [
    entry["resource"] for entry in bundle.get("entry", [])
    if entry.get("resource", {}).get("resourceType") == "Patient"
]
if len(matches) > 1 or bundle.get("total", 0) > 1:
    raise ValueError("Duplicate identifier: review before continuing.")

patient_id = (
    matches[0]["id"] if matches
    else "patient-" + str(uuid5(NAMESPACE_URL, system + "|" + identifier))
)
gender_codes = {"M": "male", "F": "female", "O": "other", "U": "unknown"}
patient = {
    "resourceType": "Patient",
    "id": patient_id,
    "identifier": [{"system": system, "value": identifier}],
    "name": [{"family": family, "given": [given]}],
    "birthDate": datetime.strptime(pid.pid_7.to_er7(), "%Y%m%d").date().isoformat(),
    "gender": gender_codes[pid.pid_8.to_er7()]
}
output = source.with_suffix(".fhir.json")
output.write_text(json.dumps(patient, indent=2) + "\n", encoding="utf-8")
print("Saved:", output)
print(json.dumps(patient, indent=2))
