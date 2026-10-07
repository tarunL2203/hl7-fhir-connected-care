"""Compare a downloaded Snowflake CSV to an existing Firely batch export.

Run from firely-learning:
 document-tools-venv/bin/python reconcile_bridge.py analytics/batches/BATCH ~/Downloads/EXPORT.csv
"""
import csv
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path


def check(condition, message):
    if not condition:
        raise ValueError(message)


def reconcile(batch, csv_path, project_root):
    manifest = json.loads((batch / "manifest.json").read_text())
    batch_id = manifest["batch_id"]
    expected = {}
    for filename, info in manifest["files"].items():
        check(Path(filename).name == filename, "Manifest filename must be a basename")
        data = (batch / filename).read_bytes()
        check(hashlib.sha256(data).hexdigest() == info["sha256"], "Export file hash differs: " + filename)
        lines = data.decode("utf-8").splitlines()
        check(len(lines) == info["rows"], "Export row count differs: " + filename)
        for row_number, line in enumerate(lines, 1):
            payload = json.loads(line)
            key = (payload["resourceType"], payload["id"])
            check(key not in expected, "Duplicate exported resource ID")
            expected[key] = (payload, filename, row_number)
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        check(reader.fieldnames is not None, "CSV has no header")
        required = {"BATCH_ID", "RESOURCE_TYPE", "RESOURCE_ID", "SOURCE_FILENAME", "FILE_ROW_NUMBER", "PAYLOAD_JSON"}
        check(required.issubset({name.upper() for name in reader.fieldnames}), "CSV is missing required columns")
        rows = [{key.upper(): value for key, value in row.items()} for row in reader]
    check(len(rows) == len(expected), "Loaded count differs from export")
    seen = set()
    for row in rows:
        key = (row["RESOURCE_TYPE"], row["RESOURCE_ID"])
        check(row["BATCH_ID"] == batch_id, "Wrong batch ID")
        check(key in expected, "Unexpected loaded resource")
        check(key not in seen, "Duplicate loaded resource")
        seen.add(key)
        payload, filename, row_number = expected[key]
        check(json.loads(row["PAYLOAD_JSON"]) == payload, "Payload differs: " + str(key))
        check(Path(row["SOURCE_FILENAME"]).name == filename, "Source filename differs")
        check(Decimal(row["FILE_ROW_NUMBER"]) == row_number, "Source row number differs")
        print("MATCH:", "/".join(key))
    check(seen == set(expected), "Exported resources are missing")
    # Independently verify source-file hashes when these files are available.
    for item in manifest.get("lineage", []):
        for field, hash_field in [("hl7_file", "hl7_sha256"), ("converted_file", "converted_sha256")]:
            path = Path(item[field])
            if not path.is_absolute():
                path = project_root / path
            check(path.is_file(), "Source file missing: " + str(path))
            check(hashlib.sha256(path.read_bytes()).hexdigest() == item[hash_field],
                  "Source hash differs: " + str(path))
    print(f"PASS: all {len(expected)} payloads and source rows match the Firely export.")
    print("PASS: available HL7 and converted source files match manifest hashes.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: reconcile_bridge.py BATCH_DIRECTORY SNOWFLAKE_CSV")
    try:
        reconcile(Path(sys.argv[1]).expanduser(), Path(sys.argv[2]).expanduser(), Path.cwd())
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise SystemExit("FAIL: " + str(error))
