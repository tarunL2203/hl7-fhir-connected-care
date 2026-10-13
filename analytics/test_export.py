"""Offline guardrail tests; these are not live ingestion evidence."""
import unittest
from export_cohort import bounded_search, validate, BASE, PATIENTS


class ExportTests(unittest.TestCase):
    def test_follows_next_and_deduplicates(self):
        resource = {"resourceType": "Observation", "id": "obs"}
        pages = {
            BASE
            + "/Observation": {
                "resourceType": "Bundle",
                "type": "searchset",
                "entry": [{"resource": resource}],
                "link": [{"relation": "next", "url": "?page=2"}],
            },
            BASE
            + "/Observation?page=2": {
                "resourceType": "Bundle",
                "type": "searchset",
                "entry": [{"resource": resource}],
            },
        }
        rows, count = bounded_search("Observation", "Observation", pages.__getitem__)
        self.assertEqual(rows, [resource])
        self.assertEqual(count, 2)

    def test_rejects_cycle(self):
        with self.assertRaisesRegex(ValueError, "pagination"):
            bounded_search(
                "Observation",
                "Observation",
                lambda _: {
                    "resourceType": "Bundle",
                    "type": "searchset",
                    "link": [{"relation": "next", "url": BASE + "/Observation"}],
                },
            )

    def test_rejects_operation_outcome(self):
        with self.assertRaisesRegex(ValueError, "unexpected"):
            bounded_search(
                "Observation",
                "Observation",
                lambda _: {
                    "resourceType": "Bundle",
                    "type": "searchset",
                    "entry": [{"resource": {"resourceType": "OperationOutcome"}}],
                },
            )

    def test_rejects_outside_patient(self):
        with self.assertRaisesRegex(ValueError, "outside_cohort"):
            validate(
                {
                    "Patient": [{"resourceType": "Patient", "id": p} for p in PATIENTS],
                    "Observation": [
                        {
                            "resourceType": "Observation",
                            "id": "x",
                            "subject": {"reference": "Patient/other"},
                        }
                    ],
                    "Appointment": [],
                }
            )


if __name__ == "__main__":
    unittest.main()
