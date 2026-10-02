import json
import math
from datetime import datetime
from pathlib import Path
from hl7apy.parser import parse_message

folder = Path.home() / "firely-learning" / "samples"
message = parse_message(
    (folder / "lab-002.hl7").read_bytes().decode("utf-8"),
    find_groups=False
)

if message.msh.msh_9.to_er7() != "ORU^R01^ORU_R01":
    raise ValueError("Expected an ORU lab message")

if len([s for s in message.children if s.name == "OBX"]) != 1:
    raise ValueError("This training converter expects one result")

mrn = message.pid.pid_3.cx_1.to_er7()
authority = message.pid.pid_3.cx_4.to_er7()
if (authority, mrn) != ("DEMO", "SYN002"):
    raise ValueError("Patient is outside this training mapping")

obx = message.obx
if obx.obx_2.to_er7() != "NM" or obx.obx_11.to_er7() != "F":
    raise ValueError("Expected a final numeric result")

if obx.obx_3.ce_3.to_er7() != "LN":
    raise ValueError("Expected a LOINC test code")
if obx.obx_6.ce_3.to_er7() != "UCUM":
    raise ValueError("Expected UCUM units")

value = float(obx.obx_5.to_er7())
if not math.isfinite(value):
    raise ValueError("Result must be a finite number")

measured_at = datetime.strptime(
    message.obr.obr_7.to_er7(), "%Y%m%d%H%M%S%z"
).isoformat()

observation = {
    "resourceType": "Observation",
    "id": "demo-glucose-002",
    "status": "final",
    "category": [{"coding": [{
        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
        "code": "laboratory"
    }]}],
    "code": {"coding": [{
        "system": "http://loinc.org",
        "code": obx.obx_3.ce_1.to_er7(),
        "display": obx.obx_3.ce_2.to_er7()
    }]},
    "subject": {"reference": "Patient/demo-patient-002"},
    "effectiveDateTime": measured_at,
    "valueQuantity": {
        "value": value,
        "unit": obx.obx_6.ce_1.to_er7(),
        "system": "http://unitsofmeasure.org",
        "code": obx.obx_6.ce_1.to_er7()
    }
}

path = folder / "lab-002.fhir.json"
path.write_text(json.dumps(observation, indent=2), encoding="utf-8")
print("Saved:", path)
print(json.dumps(observation, indent=2))

