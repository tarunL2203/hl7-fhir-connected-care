"""Convert a supported HL7 v2 ORU^R01 glucose result into a FHIR R4 Observation.

Usage: python converters/convert_lab.py <message.hl7>  (writes <message>.fhir.json)
"""

import json
import math
import sys
import uuid
from datetime import datetime
from pathlib import Path

from hl7apy.parser import parse_message

SAMPLES = Path(__file__).resolve().parents[1] / "samples"

# Patients this converter may link results to: (assigning authority, MRN) -> FHIR Patient ID.
# A production interface would resolve identity through the master patient index instead.
PATIENT_INDEX = {("DEMO", "SYN002"): "demo-patient-002"}

# Results converted before stable IDs were introduced keep their original resource ID.
LEGACY_RESULT_IDS = {
    ("DEMO", "TRAINING", "DEMO", "SYN002", "DEMO", "SYN-ORDER-002", "1"): "demo-glucose-002"
}


def result_id(source_key):
    """Deterministic Observation ID, so replaying a message never creates a duplicate."""
    legacy = LEGACY_RESULT_IDS.get(tuple(source_key))
    if legacy:
        return legacy
    return "lab-" + str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(source_key)))


def convert(raw_message):
    """Return the FHIR Observation for one supported ORU^R01 message, or raise ValueError."""
    message = parse_message(raw_message, find_groups=False)

    if message.msh.msh_9.to_er7() != "ORU^R01^ORU_R01":
        raise ValueError("Expected an ORU lab message")

    if len([s for s in message.children if s.name == "OBX"]) != 1:
        raise ValueError("This converter supports exactly one OBX result")

    mrn = message.pid.pid_3.cx_1.to_er7()
    authority = message.pid.pid_3.cx_4.to_er7()
    patient_id = PATIENT_INDEX.get((authority, mrn))
    if patient_id is None:
        raise ValueError("Patient is not in the configured patient index")

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

    return {
        "resourceType": "Observation",
        "id": result_id(source_key),
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
        "subject": {"reference": "Patient/" + patient_id},
        "effectiveDateTime": measured_at,
        "valueQuantity": {
            "value": value,
            "unit": obx.obx_6.ce_1.to_er7(),
            "system": "http://unitsofmeasure.org",
            "code": obx.obx_6.ce_1.to_er7(),
        },
    }


def main():
    source = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else SAMPLES / "lab-002.hl7"
    observation = convert(source.read_bytes().decode("utf-8"))
    path = source.with_suffix(".fhir.json")
    path.write_text(json.dumps(observation, indent=2), encoding="utf-8")
    print("Saved:", path)
    print(json.dumps(observation, indent=2))


if __name__ == "__main__":
    main()
