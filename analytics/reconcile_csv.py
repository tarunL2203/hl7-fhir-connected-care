"""Reconcile actual downloaded Snowflake RAW results with the local manifest.

Use CSV from SELECT payload, resource_type, resource_id, batch_id,
source_filename, file_row_number, loaded_at FROM <RAW table> WHERE batch_id=...
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def reconcile(batch, result):
    manifest = json.loads((batch / "manifest.json").read_text())
    expected = {}
    for f in manifest["files"]:
        for line_number, line in enumerate((batch / f["filename"]).read_text().splitlines(), 1):
            r = json.loads(line)
            expected[(r["resourceType"], r["id"])] = (r, f["filename"], line_number)
    with result.open() as source:
        actual = list(csv.DictReader(source))
    actual = [{k.lower(): v for k, v in row.items()} for row in actual]
    counts = Counter()
    seen = set()
    for row in actual:
        key = row["resource_type"], row["resource_id"]
        assert key not in seen, "duplicate_batch_resource"
        seen.add(key)
        payload, filename, line_number = expected[key]
        assert json.loads(row["payload"]) == payload, "raw_payload_mismatch"
        assert row["batch_id"] == manifest["batch_id"], "batch_mismatch"
        assert row["source_filename"].endswith('/' + filename) or row["source_filename"] == filename
        assert int(row["file_row_number"]) == line_number, "source_row_mismatch"
        assert row["loaded_at"], "missing_load_timestamp"
        counts[row["resource_type"]] += 1
    assert seen == set(expected), "missing_or_extra_resource"
    assert dict(counts) == manifest["counts"], "count_mismatch"
    return {"passed": True, "actual_snowflake_result_csv": str(result), "batch_id": manifest["batch_id"],
            "rows": len(actual), "counts": dict(counts), "ids_match": True, "complete_payloads_match": True,
            "file_row_numbers_match": True, "duplicate_count": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("batch", type=Path)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    evidence = reconcile(args.batch, args.csv)
    args.evidence.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
