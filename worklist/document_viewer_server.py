"""Portal routes for verified document retrieval, local-mode verification and batch export."""

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from viewer_server import ViewerHandler
from summary_api import ROOT, summary
from auth_fhir import BASE, get_json, search
from evaluator_v2 import patient_reference


def local_mode():
    path = ROOT / "spec/v2/local-integration.json"
    return path.is_file() and json.loads(path.read_text()).get("mode") == "local-secure-copy"


def configuration():
    return json.loads((ROOT / "spec/v2/document-storage.json").read_text())


class DocumentHandler(ViewerHandler):
    def do_GET(self):
        path = urlsplit(self.path).path

        if path == "/local-integration/export" and local_mode():
            try:
                from portal_batch_export import build_export

                filename, data = build_export()
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", 'attachment; filename="' + filename + '"')
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as error:
                self.send_json(
                    502,
                    {
                        "error": "authenticated_export_failed",
                        "error_type": type(error).__name__,
                        "diagnostic": getattr(error, "safe_diagnostic", {}),
                        "check_message": str(error)
                        if str(error)
                        in (
                            "Authenticated session required",
                            "Unexpected protected FHIR source",
                            "Five-resource refresh not configured",
                            "Snapshot cohort differs",
                            "Authenticated reads or original snapshot differ",
                            "Assessment incomplete",
                            "Qualifying results differ",
                            "Converted source differs from protected resource",
                        )
                        else "Unclassified error",
                    },
                )
            return

        if path == "/local-integration/verify" and local_mode():
            stage = "load_snapshot"
            diagnostic = {}
            try:
                mode = json.loads((ROOT / "spec/v2/local-integration.json").read_text())
                checkpoint = Path(mode["checkpoint"])
                expected = json.loads((checkpoint / "source-resources.json").read_text())

                def read_resources(label):
                    nonlocal stage
                    records = {}
                    for key in expected:
                        stage = label + ":" + key
                        records[key] = get_json(BASE + "/" + key)
                    return records

                first = read_resources("authenticated_read_1")
                second = read_resources("authenticated_read_2")
                diagnostic["two_reads_agree"] = first == second

                def different_fields(left, right, prefix=""):
                    if isinstance(left, dict) and isinstance(right, dict):
                        paths = []
                        for key in sorted(set(left) | set(right)):
                            path = prefix + ("." if prefix else "") + key
                            if key not in left or key not in right:
                                paths.append(path)
                            else:
                                paths.extend(different_fields(left[key], right[key], path))
                        return paths
                    if isinstance(left, list) and isinstance(right, list):
                        if len(left) != len(right):
                            return [prefix + ".length"]
                        return [
                            path
                            for index, (a, b) in enumerate(zip(left, right))
                            for path in different_fields(a, b, prefix + "[" + str(index) + "]")
                        ]
                    return [] if left == right else [prefix]

                diagnostic["snapshot_differences"] = {
                    key: different_fields(expected[key], first[key])[:50]
                    for key in expected
                    if expected[key] != first[key]
                }
                stage = "portal_summary"
                data = summary("demo-patient-002")
                diagnostic["returned_observation_ids"] = [r["id"] for r in data["observations"]]
                appointment_id = "siu-appointment-17d6d563-4f77-5aac-b49b-2367195f7423"
                assessments = [
                    a for a in data["assessments"] if a["appointment_id"] == appointment_id
                ]
                diagnostic["assessment_count"] = len(assessments)
                stage = "appointment_assessment"
                if len(assessments) != 1:
                    raise RuntimeError("assessment_count")
                diagnostic["assessment_outcome"] = assessments[0]["outcome"]
                requirements = assessments[0]["requirements"]
                diagnostic["matched_record_ids"] = [
                    r.get("matched_record_ids", []) for r in requirements
                ]
                diagnostic["requirement_outcomes"] = [r.get("outcome") for r in requirements]
                expected_labs = set(
                    mode.get(
                        "expected_lab_ids",
                        ["demo-glucose-002", "lab-760b9ffe-19ca-5dbb-b2ef-8bb12d2cf2d4"],
                    )
                )
                if (
                    assessments[0]["outcome"] != "information_complete"
                    or len(requirements) != 1
                    or set(requirements[0]["matched_record_ids"]) != expected_labs
                ):
                    raise RuntimeError("qualifying_results")
                stage = "snapshot_comparison"

                def normalize_local_patient_references(resource):
                    # Normalize only patient links in their FHIR reference fields.
                    # Never change IDs, clinical values, timestamps, metadata or other URLs.
                    import copy

                    value = copy.deepcopy(resource)

                    def normalize(reference):
                        if not isinstance(reference, str):
                            return reference
                        relative = reference
                        for base in ("http://localhost:8080/", "http://localhost:8081/"):
                            if reference.startswith(base):
                                relative = reference[len(base) :]
                                break
                        return (
                            relative
                            if re.fullmatch(r"Patient/[A-Za-z0-9.-]{1,64}", relative)
                            else reference
                        )

                    if value.get("resourceType") == "Observation":
                        subject = value.get("subject")
                        if isinstance(subject, dict) and "reference" in subject:
                            subject["reference"] = normalize(subject["reference"])
                    elif value.get("resourceType") == "Appointment":
                        for participant in value.get("participant", []):
                            actor = participant.get("actor")
                            if isinstance(actor, dict) and "reference" in actor:
                                actor["reference"] = normalize(actor["reference"])
                    return value

                normalized_expected = {
                    key: normalize_local_patient_references(value)
                    for key, value in expected.items()
                }
                normalized_first = {
                    key: normalize_local_patient_references(value) for key, value in first.items()
                }
                diagnostic["snapshot_matches_after_local_reference_normalization"] = (
                    normalized_first == normalized_expected
                )
                if first != second or normalized_first != normalized_expected:
                    raise RuntimeError("snapshot_mismatch")
                from datetime import datetime, timezone
                from hashlib import sha256

                report = {
                    "passed": True,
                    "authenticated": True,
                    "resource_count": len(first),
                    "two_reads_agree": True,
                    "original_snapshot_matches": first == expected,
                    "snapshot_matches_after_local_reference_normalization": True,
                    "comparison_mode": "all fields match after normalizing exact localhost:8080/8081 patient references",
                    "normalized_reference_fields": diagnostic["snapshot_differences"],
                    "appointment_id": appointment_id,
                    "qualifying_glucose_count": len(expected_labs),
                    "outcome": "information_complete",
                    "documents": "deferred",
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "payload_hashes": {
                        key: sha256(
                            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
                        ).hexdigest()
                        for key, value in first.items()
                    },
                }
                stage = "save_evidence"
                evidence_dir = ROOT / "evidence"
                evidence_dir.mkdir(parents=True, exist_ok=True)
                name = (
                    "local-portal-"
                    + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                    + ".json"
                )
                (evidence_dir / name).write_text(json.dumps(report, indent=2) + "\n")
                self.send_json(200, report)
            except Exception as error:
                report = {
                    "passed": False,
                    "error": "local_bridge_verification_failed",
                    "failed_step": stage,
                    "error_type": type(error).__name__,
                    "diagnostic": diagnostic,
                }
                status = getattr(error, "code", None)
                if isinstance(status, int) and 400 <= status <= 599:
                    report["upstream_http_status"] = status
                self.send_json(502, report)
            return

        summary_match = re.fullmatch(r"/patients/([A-Za-z0-9.-]{1,64})/summary", path)
        if summary_match:
            try:
                patient_id = summary_match.group(1)
                data = summary(patient_id)
                if local_mode():
                    data["documents"] = []
                    data["document_status"] = "Document downloads are deferred until the AWS phase."
                    self.send_json(200, data)
                    return
                query = urlencode({"subject": "Patient/" + patient_id})
                documents = search("DocumentReference?" + query, "DocumentReference")
                policy = json.loads((ROOT / "spec/v2/policy.json").read_text())
                config = configuration()
                allowed_ids = {d["document_reference_id"] for d in config["documents"]}

                data["documents"] = []
                for document in documents:
                    if (
                        patient_reference(document.get("subject", {}).get("reference"), policy)
                        != "Patient/" + patient_id
                    ):
                        raise RuntimeError("Document patient link mismatch")

                    attachment = document["content"][0]["attachment"]
                    can_open = (
                        patient_id == config["patient_id"]
                        and document["id"] in allowed_ids
                        and document.get("status") == "current"
                    )
                    data["documents"].append(
                        {
                            "id": document["id"],
                            "title": attachment.get("title", document["id"]),
                            "content_type": attachment.get("contentType"),
                            "open_path": (
                                "/patients/" + patient_id + "/documents/" + document["id"]
                                if can_open
                                else None
                            ),
                        }
                    )
                data["supported_record_types"].append("DocumentReference")
                self.send_json(200, data)
            except Exception:
                self.send_json(
                    502,
                    {"error": "summary_or_documents_not_completed", "assessment_completed": False},
                )
            return

        document_match = re.fullmatch(
            r"/patients/([A-Za-z0-9.-]{1,64})/documents/([A-Za-z0-9.-]{1,64})", path
        )
        if not document_match:
            super().do_GET()
            return

        if local_mode():
            self.send_json(503, {"error": "documents_deferred_to_aws_phase"})
            return
        patient_id, document_id = document_match.groups()
        config = configuration()
        document = next(
            (d for d in config["documents"] if d["document_reference_id"] == document_id), None
        )
        if patient_id != config["patient_id"] or document is None:
            self.send_json(403, {"error": "document_patient_or_registry_mismatch"})
            return

        try:
            policy = json.loads((ROOT / "spec/v2/policy.json").read_text())
            reference = get_json(BASE + "/DocumentReference/" + document_id)
            attachment = reference["content"][0]["attachment"]
            expected_url = (
                "https://"
                + config["bucket"]
                + ".s3."
                + config["region"]
                + ".amazonaws.com/"
                + document["key"]
            )
            if (
                reference.get("status") != "current"
                or patient_reference(reference.get("subject", {}).get("reference"), policy)
                != "Patient/" + patient_id
                or attachment.get("url") != expected_url
                or attachment.get("contentType") != document["content_type"]
                or attachment.get("size") != document["size_bytes"]
            ):
                raise RuntimeError("Document reference does not match registry")

            aws = shutil.which("aws")
            if not aws:
                raise RuntimeError("AWS CLI unavailable")

            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "object"
                completed = subprocess.run(
                    [
                        aws,
                        "s3api",
                        "get-object",
                        "--profile",
                        config["aws_profile"],
                        "--region",
                        config["region"],
                        "--bucket",
                        config["bucket"],
                        "--key",
                        document["key"],
                        "--no-cli-pager",
                        str(output),
                    ],
                    capture_output=True,
                    timeout=60,
                    check=False,
                )
                if completed.returncode != 0:
                    raise RuntimeError("Private S3 retrieval failed")
                content = output.read_bytes()

            if (
                len(content) != document["size_bytes"]
                or hashlib.sha256(content).hexdigest() != document["sha256"]
            ):
                raise RuntimeError("Downloaded content verification failed")

        except Exception:
            self.send_json(502, {"error": "document_retrieval_or_verification_failed"})
            return

        self.send_response(200)
        self.send_header("Content-Type", document["content_type"])
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8082), DocumentHandler)
    print("Document viewer: http://localhost:8082", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
