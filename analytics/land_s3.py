"""Upload a validated synthetic batch to the existing private bucket; verify bytes."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
BUCKET = os.environ.get("S3_BUCKET", "<S3_BUCKET>")
PROFILE = "firely-learning"


class CloudError(Exception):
    pass


def aws(*args):
    result = subprocess.run(
        [
            "aws",
            *args,
            "--profile",
            PROFILE,
            "--region",
            "us-east-2",
            "--output",
            "json",
            "--no-cli-pager",
        ],
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        match = re.search(rb"An error occurred \(([^)]+)\)", result.stderr)
        code = match.group(1).decode() if match else "aws_command_failed"
        raise CloudError(code)
    return json.loads(result.stdout or "{}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("batch")
    args = parser.parse_args()
    directory = Path(args.batch).resolve()
    assert directory.parent == ROOT / "analytics/batches", "batch_outside_export_directory"
    manifest = json.loads((directory / "manifest.json").read_text())
    batch = manifest["batch_id"]
    assert batch == directory.name and re.fullmatch(r"synthetic-[0-9TZ]+-[a-f0-9]{8}", batch)
    assert manifest["synthetic_data_only"] is True
    prefix = "analytics-demo/" + batch + "/"
    evidence = {
        "live": True,
        "at": datetime.now(timezone.utc).isoformat(),
        "bucket": BUCKET,
        "prefix": prefix,
        "objects": [],
        "passed": False,
    }
    try:
        block = aws("s3api", "get-public-access-block", "--bucket", BUCKET)[
            "PublicAccessBlockConfiguration"
        ]
        assert all(
            block.get(k) is True
            for k in (
                "BlockPublicAcls",
                "IgnorePublicAcls",
                "BlockPublicPolicy",
                "RestrictPublicBuckets",
            )
        )
        ownership = aws("s3api", "get-bucket-ownership-controls", "--bucket", BUCKET)
        assert (
            ownership["OwnershipControls"]["Rules"][0]["ObjectOwnership"] == "BucketOwnerEnforced"
        )
        evidence["public_access_block"] = block
        entries = manifest["files"] + [{"filename": "manifest.json"}]
        for entry in entries:
            filename = entry["filename"]
            assert Path(filename).name == filename
            path = directory / filename
            data = path.read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            if filename != "manifest.json":
                assert (
                    sha == entry["sha256"] and len(data) == entry["bytes"]
                ), "local_integrity_mismatch"
                rows = [json.loads(line) for line in data.splitlines()]
                kind = entry["resource_type"]
                assert len(rows) == manifest["counts"][kind]
                assert sorted(r["id"] for r in rows) == sorted(manifest["ids"][kind])
                assert all(r["resourceType"] == kind for r in rows)
            key = prefix + filename
            try:
                head = aws("s3api", "head-object", "--bucket", BUCKET, "--key", key)
                existed = True
            except CloudError as error:
                if str(error) not in ("404", "NoSuchKey", "NotFound"):
                    raise
                existed = False
                aws(
                    "s3api",
                    "put-object",
                    "--bucket",
                    BUCKET,
                    "--key",
                    key,
                    "--body",
                    str(path),
                    "--if-none-match",
                    "*",
                    "--server-side-encryption",
                    "AES256",
                    "--checksum-algorithm",
                    "SHA256",
                    "--checksum-sha256",
                    base64.b64encode(hashlib.sha256(data).digest()).decode(),
                    "--content-type",
                    "application/json" if filename == "manifest.json" else "application/x-ndjson",
                )
                head = aws("s3api", "head-object", "--bucket", BUCKET, "--key", key)
            assert head["ContentLength"] == len(data)
            assert head.get("ServerSideEncryption") == "AES256"
            with tempfile.TemporaryDirectory() as tmp:
                downloaded = Path(tmp) / "object"
                aws("s3api", "get-object", "--bucket", BUCKET, "--key", key, str(downloaded))
                assert (
                    hashlib.sha256(downloaded.read_bytes()).hexdigest() == sha
                ), "download_hash_mismatch"
            evidence["objects"].append(
                {
                    "key": key,
                    "bytes": len(data),
                    "sha256": sha,
                    "download_sha256_matches": True,
                    "encryption": "AES256",
                    "already_existed": existed,
                }
            )
        evidence["passed"] = True
    except Exception as error:
        evidence["failure"] = str(error) if isinstance(error, CloudError) else type(error).__name__
    destination = ROOT / "analytics/evidence" / (batch + "-s3.json")
    destination.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    raise SystemExit(0 if evidence["passed"] else 1)


if __name__ == "__main__":
    main()
