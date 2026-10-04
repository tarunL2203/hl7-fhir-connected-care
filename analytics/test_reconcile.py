"""Offline negative checks for the CSV reconciliation gate, not cloud evidence."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from reconcile_csv import reconcile


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        resource = {"resourceType": "Patient", "id": "synthetic-test"}
        (self.root / "patient.ndjson").write_text(json.dumps(resource) + "\n")
        (self.root / "manifest.json").write_text(json.dumps({"batch_id": "test", "counts": {"Patient": 1},
            "files": [{"filename": "patient.ndjson"}]}))
        self.row = {"PAYLOAD": json.dumps(resource), "RESOURCE_TYPE": "Patient", "RESOURCE_ID": "synthetic-test",
            "BATCH_ID": "test", "SOURCE_FILENAME": "test/patient.ndjson", "FILE_ROW_NUMBER": "1",
            "LOADED_AT": "2026-10-04T00:00:00Z"}

    def write(self, rows):
        path = self.root / "simulated-result.csv"
        with path.open("w") as f:
            writer = csv.DictWriter(f, fieldnames=self.row)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_accepts_matching_payload(self):
        self.assertTrue(reconcile(self.root, self.write([self.row]))["passed"])

    def test_rejects_duplicate(self):
        with self.assertRaisesRegex(AssertionError, "duplicate"):
            reconcile(self.root, self.write([self.row, self.row]))

    def test_rejects_missing(self):
        with self.assertRaisesRegex(AssertionError, "missing"):
            reconcile(self.root, self.write([]))

    def test_rejects_altered_payload(self):
        row = dict(self.row, PAYLOAD='{"resourceType":"Patient","id":"synthetic-test","active":false}')
        with self.assertRaisesRegex(AssertionError, "payload"):
            reconcile(self.root, self.write([row]))


if __name__ == "__main__":
    unittest.main()
