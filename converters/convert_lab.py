import json
import uuid
import sys
import math
from datetime import datetime
from pathlib import Path
from hl7apy.parser import parse_message

folder = Path(__file__).resolve().parents[1] / "samples"
source = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else folder / "lab-002.hl7"
message = parse_message(source.read_bytes().decode("utf-8"), find_groups=False)

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

measured_at = datetime.strptime(message.obr.obr_7.to_er7(), "%Y%m%d%H%M%S%z").isoformat()


order_id = message.obr.obr_3.ei_1.to_er7()
order_authority = message.obr.obr_3.ei_2.to_er7()
result_number = obx.obx_1.to_er7()
sender = message.msh.msh_3.to_er7()
facility = message.msh.msh_4.to_er7()

if not all([order_id, order_authority, result_number, sender, facility]):
    raise ValueError("Missing source information needed for a stable lab ID")

source_key = [sender, facility, authority, mrn, order_authority, order_id, result_number]

if source_key == ["DEMO", "TRAINING", "DEMO", "SYN002", "DEMO", "SYN-ORDER-002", "1"]:
    lab_id = "demo-glucose-002"
else:
    lab_id = "lab-" + str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(source_key)))

observation = {
    "resourceType": "Observation",
    "id": lab_id,
    "status": "final",
    "category": [
        {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                    "code": "laboratory",
                }
            ]
        }
    ],
    "code": {
        "coding": [
            {
                "system": "http://loinc.org",
                "code": obx.obx_3.ce_1.to_er7(),
                "display": obx.obx_3.ce_2.to_er7(),
            }
        ]
    },
    "subject": {"reference": "Patient/demo-patient-002"},
    "effectiveDateTime": measured_at,
    "valueQuantity": {
        "value": value,
        "unit": obx.obx_6.ce_1.to_er7(),
        "system": "http://unitsofmeasure.org",
        "code": obx.obx_6.ce_1.to_er7(),
    },
}

path = source.with_suffix(".fhir.json")
path.write_text(json.dumps(observation, indent=2), encoding="utf-8")
print("Saved:", path)
print(json.dumps(observation, indent=2))
