
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

def configuration():
    return json.loads(
        (ROOT / "spec/v2/document-storage.json").read_text()
    )

class DocumentHandler(ViewerHandler):
    def do_GET(self):
        path = urlsplit(self.path).path

        summary_match = re.fullmatch(
            r"/patients/([A-Za-z0-9.-]{1,64})/summary", path
        )
        if summary_match:
            try:
                patient_id = summary_match.group(1)
                data = summary(patient_id)
                query = urlencode({"subject": "Patient/" + patient_id})
                documents = search("DocumentReference?" + query, "DocumentReference")
                policy = json.loads((ROOT / "spec/v2/policy.json").read_text())
                config = configuration()
                allowed_ids = {
                    d["document_reference_id"] for d in config["documents"]
                }

                data["documents"] = []
                for document in documents:
                    if patient_reference(
                        document.get("subject", {}).get("reference"), policy
                    ) != "Patient/" + patient_id:
                        raise RuntimeError("Document patient link mismatch")

                    attachment = document["content"][0]["attachment"]
                    can_open = (
                        patient_id == config["patient_id"]
                        and document["id"] in allowed_ids
                        and document.get("status") == "current"
                    )
                    data["documents"].append({
                        "id": document["id"],
                        "title": attachment.get("title", document["id"]),
                        "content_type": attachment.get("contentType"),
                        "open_path": (
                            "/patients/" + patient_id + "/documents/" + document["id"]
                            if can_open else None
                        )
                    })
                data["supported_record_types"].append("DocumentReference")
                self.send_json(200, data)
            except Exception:
                self.send_json(502, {
                    "error": "summary_or_documents_not_completed",
                    "assessment_completed": False
                })
            return

        document_match = re.fullmatch(
            r"/patients/([A-Za-z0-9.-]{1,64})/documents/([A-Za-z0-9.-]{1,64})",
            path
        )
        if not document_match:
            super().do_GET()
            return

        patient_id, document_id = document_match.groups()
        config = configuration()
        document = next(
            (d for d in config["documents"]
             if d["document_reference_id"] == document_id), None
        )
        if patient_id != config["patient_id"] or document is None:
            self.send_json(403, {"error": "document_patient_or_registry_mismatch"})
            return

        try:
            policy = json.loads((ROOT / "spec/v2/policy.json").read_text())
            reference = get_json(BASE + "/DocumentReference/" + document_id)
            attachment = reference["content"][0]["attachment"]
            expected_url = (
                "https://" + config["bucket"] + ".s3."
                + config["region"] + ".amazonaws.com/" + document["key"]
            )
            if (
                reference.get("status") != "current"
                or patient_reference(
                    reference.get("subject", {}).get("reference"), policy
                ) != "Patient/" + patient_id
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
                completed = subprocess.run([
                    aws, "s3api", "get-object",
                    "--profile", config["aws_profile"],
                    "--region", config["region"],
                    "--bucket", config["bucket"],
                    "--key", document["key"],
                    "--no-cli-pager", str(output)
                ], capture_output=True, timeout=60)
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
