"""Bounded synthetic export using the existing normal OIDC/PKCE viewer server.

No credential input, browser-cookie extraction, token persistence or auth bypass.
Run only while port 8082 is free, then sign in through the normal viewer.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import threading
import time
from urllib.parse import urlencode, urljoin
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worklist"))
from auth_fhir import ACCESS_TOKEN, BASE, get_json
from authenticated_viewer_server import create_server
from evaluator_v2 import patient_reference

# Exact IDs established by the saved successful real reviewer verification.
PATIENTS = ("demo-patient-002", "fixture-v2-p02")
POLICY = json.loads((ROOT / "worklist/spec/v2/policy.json").read_text())


def require(ok, code):
    if not ok:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def bounded_search(path, kind, reader=get_json):
    url = BASE + "/" + path
    seen, records = set(), {}
    while url:
        require(url not in seen and len(seen) < 100, "pagination_limit_or_cycle")
        seen.add(url)
        bundle = reader(url)  # Existing reader enforces token and local FHIR origin.
        require(bundle.get("resourceType") == "Bundle" and bundle.get("type") == "searchset", "invalid_search_bundle")
        for entry in bundle.get("entry", []):
            r = entry.get("resource", {})
            require(r.get("resourceType") == kind, "unexpected_search_resource")
            rid = r.get("id", "")
            require(bool(re.fullmatch(r"[A-Za-z0-9.-]{1,64}", rid)), "invalid_resource_id")
            require(rid not in records or records[rid] == r, "conflicting_page_record")
            records[rid] = r
            require(len(records) <= 1000, "cohort_resource_limit")
        next_urls = [x["url"] for x in bundle.get("link", []) if x.get("relation") == "next"]
        require(len(next_urls) <= 1, "ambiguous_next_link")
        url = urljoin(url, next_urls[0]) if next_urls else None
    return list(records.values()), len(seen)


def validate(resources):
    expected = {"Patient/" + p for p in PATIENTS}
    require({r["id"] for r in resources["Patient"]} == set(PATIENTS), "patient_cohort_mismatch")
    exceptions = []
    for kind, rows in resources.items():
        require(len({r["id"] for r in rows}) == len(rows), "duplicate_resource")
        for r in rows:
            require(r.get("resourceType") == kind, "type_mismatch")
            if kind == "Observation":
                require(patient_reference(r.get("subject", {}).get("reference"), POLICY) in expected, "observation_outside_cohort")
            elif kind == "Appointment":
                refs = [p.get("actor", {}).get("reference") for p in r.get("participant", [])]
                patients = [patient_reference(ref, POLICY) for ref in refs]
                require(any(ref in expected for ref in patients), "appointment_outside_cohort")
                for ref, resolved in zip(refs, patients):
                    if resolved and resolved not in expected:
                        raise ValueError("appointment_contains_other_patient")
                    if not resolved:
                        exceptions.append({"resource": kind + "/" + r["id"], "reference": ref,
                                           "reason": "non-cohort-patient actor; not exported or resolved"})
    return exceptions


def extract():
    resources = {k: {} for k in ("Patient", "Observation", "Appointment")}
    searches = []
    for pid in PATIENTS:
        r = get_json(BASE + "/Patient/" + pid)
        require(r.get("id") == pid and r.get("resourceType") == "Patient", "patient_read_mismatch")
        resources["Patient"][pid] = r
        for kind, parameter in [("Observation", "subject"), ("Appointment", "actor")]:
            path = kind + "?" + urlencode({parameter: "Patient/" + pid, "_count": "1"})
            rows, pages = bounded_search(path, kind)
            searches.append({"path": path, "pages": pages, "records": len(rows)})
            for row in rows:
                old = resources[kind].get(row["id"])
                require(old is None or old == row, "conflicting_cohort_record")
                resources[kind][row["id"]] = row
    return {k: sorted(v.values(), key=lambda r: r["id"]) for k, v in resources.items()}, searches


def save_export():
    started = datetime.now(timezone.utc)
    resources, searches = extract()
    exceptions = validate(resources)
    # Independent second authorized read catches paging/source changes during export.
    second, _ = extract()
    require(canonical(resources) == canonical(second), "source_changed_during_extract")
    batch = "synthetic-" + started.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    directory = ROOT / "analytics/batches" / batch
    directory.mkdir(parents=True, mode=0o700)
    files, counts, ids = [], {}, {}
    for kind, rows in resources.items():
        data = ("".join(canonical(r) + "\n" for r in rows)).encode()
        name = kind.lower() + ".ndjson"
        (directory / name).write_bytes(data)
        reread = [json.loads(line) for line in data.splitlines()]
        require(reread == rows, "ndjson_roundtrip_failed")
        files.append({"filename": name, "resource_type": kind, "bytes": len(data), "sha256": digest(data)})
        counts[kind] = len(rows)
        ids[kind] = [r["id"] for r in rows]
    manifest = {"batch_id": batch, "extracted_at_utc": started.isoformat(), "synthetic_data_only": True,
                "patient_ids": list(PATIENTS), "scope": list(resources), "counts": counts, "ids": ids,
                "files": files, "searches": searches, "source": BASE,
                "source_comparison": {"second_authorized_read_identical": True},
                "reference_exceptions": exceptions,
                "excluded": ["DocumentReference and PDF/image bodies", "Other patients and unrelated resources"],
                "snapshot_consistency": "Two matching reads; not a transactionally locked FHIR snapshot"}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    evidence = {"live": True, "authorized_normal_reviewer_session": True, "batch_id": batch,
                "counts": counts, "ids": ids, "source_comparison_passed": True, "pagination": searches,
                "manifest_sha256": digest((directory / "manifest.json").read_bytes())}
    (ROOT / "analytics/evidence" / (batch + "-extract.json")).write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2), flush=True)
    print("Export: " + str(directory), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--login-timeout", type=int, default=600)
    args = parser.parse_args()
    db = ROOT / "worklist/data/worklist.sqlite"
    before = digest(db.read_bytes())
    server = create_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("Normal viewer ready. Sign in at https://localhost:8082/auth/login", flush=True)
    print("Waiting for normal verified reviewer login; no credentials are saved.", flush=True)
    try:
        deadline = time.monotonic() + args.login_timeout
        session = None
        while time.monotonic() < deadline:
            with server.auth.lock:
                server.auth.prune()
                session = next(iter(server.auth.sessions.values()), None)
            if session:
                break
            time.sleep(0.3)
        require(session is not None, "reviewer_login_timeout")
        context = ACCESS_TOKEN.set(session["access_token"])
        try:
            save_export()
        finally:
            ACCESS_TOKEN.reset(context)
        require(digest(db.read_bytes()) == before, "worklist_changed")
        print("Read-only export complete; worklist unchanged. Viewer remains available.", flush=True)
        session = None
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    except Exception as error:
        print("Export stopped: " + type(error).__name__, flush=True)
        raise SystemExit(1) from None
    finally:
        server.shutdown()
        server.server_close()
        with server.auth.lock:
            server.auth.sessions.clear()
            server.auth.pending.clear()


if __name__ == "__main__":
    main()
