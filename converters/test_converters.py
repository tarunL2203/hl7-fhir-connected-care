"""Offline tests for the HL7 v2 -> FHIR converters."""

import json
import unittest
from pathlib import Path

import convert_admission
import convert_lab

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def sample(name):
    return (SAMPLES / name).read_bytes().decode("utf-8")


def committed(name):
    return json.loads((SAMPLES / name).read_text())


class LabConversionTests(unittest.TestCase):
    def test_reproduces_committed_observations(self):
        for name in ("lab-002", "lab-003", "lab-portal-update-004"):
            with self.subTest(name):
                self.assertEqual(
                    convert_lab.convert(sample(name + ".hl7")), committed(name + ".fhir.json")
                )

    def test_replay_keeps_the_id_and_a_new_order_gets_a_new_one(self):
        message = sample("lab-003.hl7")
        first = convert_lab.convert(message)
        self.assertEqual(convert_lab.convert(message)["id"], first["id"])
        other_order = convert_lab.convert(message.replace("SYN-ORDER-003", "SYN-ORDER-099"))
        self.assertNotEqual(other_order["id"], first["id"])

    def test_rejects_unsupported_results(self):
        message = sample("lab-003.hl7")
        cases = {
            "preliminary status": (message.replace("|||||F", "|||||P"), "final numeric"),
            "text value type": (message.replace("OBX|1|NM|", "OBX|1|ST|"), "final numeric"),
            "non-LOINC code": (message.replace("^LN||102", "^L||102"), "LOINC"),
            "non-UCUM units": (message.replace("mg/dL^UCUM", "mg/dL^ISO+"), "UCUM"),
            "non-finite value": (message.replace("||102|", "||nan|"), "finite"),
            "unknown patient": (message.replace("SYN002^^^DEMO", "SYN999^^^DEMO"), "patient index"),
            "second result": (
                message.rstrip("\r") + "\r" + message.split("\r")[3] + "\r",
                "one OBX",
            ),
            "time without offset": (
                message.replace("LN|||20261001100000-0400", "LN|||20261001100000"),
                "does not match format",
            ),
        }
        for label, (variant, reason) in cases.items():
            with self.subTest(label):
                self.assertNotEqual(variant, message)
                with self.assertRaisesRegex(ValueError, reason):
                    convert_lab.convert(variant)


class AdmissionConversionTests(unittest.TestCase):
    def setUp(self):
        self.searches = []

    def firely_returning(self, *patients):
        def search(system, identifier):
            self.searches.append((system, identifier))
            return {
                "resourceType": "Bundle",
                "total": len(patients),
                "entry": [{"resource": patient} for patient in patients],
            }

        return search

    def test_existing_patient_keeps_its_id(self):
        existing = {"resourceType": "Patient", "id": "demo-patient-002"}
        patient = convert_admission.convert(
            sample("admission-002.hl7"), self.firely_returning(existing)
        )
        self.assertEqual(patient, committed("admission-002.fhir.json"))

    def test_new_patient_gets_a_deterministic_id(self):
        patient = convert_admission.convert(sample("admission-003.hl7"), self.firely_returning())
        self.assertEqual(patient, committed("admission-003.fhir.json"))

    def test_matching_uses_the_identifier_never_the_name(self):
        convert_admission.convert(sample("admission-003.hl7"), self.firely_returning())
        self.assertEqual(self.searches, [("https://example.org/training/mrn", "SYN003")])

    def test_duplicate_identifier_is_rejected(self):
        twins = ({"resourceType": "Patient", "id": "a"}, {"resourceType": "Patient", "id": "b"})
        with self.assertRaisesRegex(ValueError, "Duplicate identifier"):
            convert_admission.convert(sample("admission-002.hl7"), self.firely_returning(*twins))

    def test_other_identifier_authorities_are_rejected(self):
        message = sample("admission-002.hl7").replace("^^^DEMO^MR", "^^^OTHER^MR")
        with self.assertRaisesRegex(ValueError, "identifier authority"):
            convert_admission.convert(message, self.firely_returning())
        self.assertEqual(self.searches, [])


if __name__ == "__main__":
    unittest.main()
