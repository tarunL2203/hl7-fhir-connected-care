"""Focused synthetic SIU^S12 -> FHIR appointment demonstration.

Run from the existing firely-learning project folder with its Python interpreter.
Uses the standard library only. This intentionally supports the fixture below,
not a general HL7 feed or complete HL7/FHIR profile validation.
"""
import argparse
import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import NAMESPACE_URL, uuid5

BASE = "http://localhost:8080/"
ACCEPT = {"Accept": "application/fhir+json; fhirVersion=4.0"}
MRN_SYSTEM = "https://example.org/training/mrn"
APPT_SYSTEM = "https://example.org/training/appointment"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def segment(name, count, fields):
    values = [""] * (count + 1)
    values[0] = name
    for position, value in fields.items():
        values[position] = value
    return "|".join(values)


def fixture():
    # SCH-11 is TQ: component 4=start, component 5=end.
    return ("\r".join([
        "MSH|^~\\&|DEMO|TRAINING|FIRELY|LOCAL|20261007160000+0000||SIU^S12^SIU_S12|SYN-SIU-BRIDGE-001|T|2.5.1",
        segment("SCH", 25, {
            1: "SYN-PLACER-BRIDGE-001^DEMO",
            2: "SYN-APPT-BRIDGE-001^DEMO",
            6: "demo-glucose-review^Glucose review^L",
            7: "demo-glucose-review^Glucose review^L",
            9: "30", 10: "min^minutes^UCUM",
            11: "^^30^20261006130000+0000^20261006133000+0000",
            25: "Booked^Booked^HL70278",
        }),
        segment("PID", 8, {
            1: "1", 3: "SYN002^^^DEMO^MR", 5: "Demo^Ravi",
            7: "19850512", 8: "M",
        }),
        "RGS|1",
        segment("AIS", 8, {
            1: "1", 3: "demo-glucose-review^Glucose review^L",
            4: "20261006130000+0000", 7: "30",
            8: "min^minutes^UCUM",
        }),
    ]) + "\r").encode("utf-8")


def timestamp(value):
    require(bool(re.fullmatch(r"[0-9]{14}[+-][0-9]{4}", value)),
            "Appointment timestamps must include seconds and an explicit offset.")
    return datetime.strptime(value, "%Y%m%d%H%M%S%z")


def convert(raw, patient_id):
    text = raw.decode("utf-8").replace("\r\n", "\r").replace("\n", "\r")
    rows = [line.split("|") for line in text.split("\r") if line]
    require([row[0] for row in rows] == ["MSH", "SCH", "PID", "RGS", "AIS"],
            "Only the fixture's single SCH/PID/RGS/AIS structure is supported.")
    msh, sch, pid, rgs, ais = rows
    require(len(msh) >= 12 and msh[1] == "^~\\&", "Unsupported encoding delimiters.")
    require(msh[8] == "SIU^S12^SIU_S12" and msh[11] == "2.5.1",
            "Only SIU^S12 version 2.5.1 new-booking messages are supported.")
    require(msh[10] == "T" and msh[2:4] == ["DEMO", "TRAINING"],
            "Only the synthetic training sender is supported.")
    require(len(sch) >= 26 and len(pid) >= 9 and len(ais) >= 9,
            "Required fixture fields are missing.")
    require(not any("~" in field or "\\" in field for row in rows[1:] for field in row[1:]),
            "Repeating fields and escaped content are outside this fixture converter.")
    mrn = pid[3].split("^")
    require(len(mrn) == 5 and mrn == ["SYN002", "", "", "DEMO", "MR"],
            "Patient identifier is outside the SYN002/DEMO fixture.")
    require(bool(re.fullmatch(r"[A-Za-z0-9.-]{1,64}", patient_id)), "Invalid patient ID.")
    require(sch[25].split("^")[0] == "Booked", "Only booked appointments are supported.")
    timing = sch[11].split("^")
    require(len(timing) == 5 and timing[:3] == ["", "", "30"],
            "Expected one 30-minute timing interval in SCH-11.")
    start, end = timestamp(timing[3]), timestamp(timing[4])
    require(end > start, "Appointment end must be after start.")
    require((end - start).total_seconds() == 1800 and sch[9] == "30"
            and sch[10] == "min^minutes^UCUM", "Duration fields disagree.")
    require(timestamp(ais[4]) == start and ais[7:9] == ["30", "min^minutes^UCUM"],
            "AIS service timing disagrees with SCH.")
    require(sch[7] == ais[3] == "demo-glucose-review^Glucose review^L",
            "Unsupported or inconsistent appointment service.")
    filler = sch[2].split("^")
    require(len(filler) == 2 and all(filler) and filler[1] == "DEMO",
            "A DEMO filler appointment identifier is required.")
    source_key = json.dumps([msh[2], msh[3], *filler], separators=(",", ":"))
    appointment_id = "siu-appointment-" + str(uuid5(NAMESPACE_URL, source_key))
    return {
        "resourceType": "Appointment", "id": appointment_id,
        "meta": {"tag": [{"system": "https://example.org/fixture-label", "code": "synthetic"}]},
        "identifier": [{"system": APPT_SYSTEM, "value": filler[0]}],
        "status": "booked", "description": "Synthetic glucose review",
        "serviceType": [{"coding": [{"system": "https://example.org/synthetic-visit-types",
                                      "code": "demo-glucose-review", "display": "Glucose review"}]}],
        "start": start.isoformat(), "end": end.isoformat(), "minutesDuration": 30,
        "participant": [{"actor": {"reference": "Patient/" + patient_id}, "status": "accepted"}],
    }


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(resource):
    return json.dumps(resource, sort_keys=True, separators=(",", ":")).encode("utf-8")


def request_json(path, data=None, method="GET"):
    headers = dict(ACCEPT)
    if data is not None:
        headers["Content-Type"] = "application/fhir+json; fhirVersion=4.0"
    request = Request(BASE + path, data=None if data is None else encode(data),
                      method=method, headers=headers)
    with urlopen(request, timeout=30) as response:
        body = response.read()
        return (json.loads(body) if body else None), response.status


def compare(expected, actual):
    require(actual.get("resourceType") == expected["resourceType"]
            and actual.get("id") == expected["id"], "Resource identity differs.")
    normalized = copy.deepcopy(actual)
    references = []
    if "subject" in normalized:
        references.append(normalized["subject"])
    references.extend(p.get("actor", {}) for p in normalized.get("participant", []))
    for reference in references:
        value = reference.get("reference", "")
        if value.startswith(BASE):
            reference["reference"] = value[len(BASE):]
    for key, value in expected.items():
        if key == "meta":
            # Firely adds its version and update time; retain and compare our tags.
            for tag in value.get("tag", []):
                require(tag in normalized.get("meta", {}).get("tag", []), "Synthetic tag missing.")
        else:
            require(normalized.get(key) == value, expected["id"] + " differs in " + key)


def self_test():
    raw = fixture()
    result = convert(raw, "demo-patient-002")
    require(result["start"] == "2026-10-06T13:00:00+00:00", "Start mapping failed.")
    require(result["end"] == "2026-10-06T13:30:00+00:00", "End mapping failed.")
    require(result["participant"][0]["actor"]["reference"] == "Patient/demo-patient-002",
            "Patient mapping failed.")
    # A retransmission gets the same ID, even if its message control ID changes.
    repeat = raw.replace(b"SYN-SIU-BRIDGE-001", b"SYN-SIU-BRIDGE-REPEAT")
    require(convert(repeat, "demo-patient-002")["id"] == result["id"], "Stable identity failed.")
    for bad in [raw.replace(b"SYN002", b"SYN999"), raw.replace(b"SIU^S12", b"SIU^S15"),
                raw.replace(b"20261006133000+0000", b"20261006123000+0000"),
                raw.replace(b"20261006130000+0000", b"20261006130000")]:
        try:
            convert(bad, "demo-patient-002")
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid fixture was accepted.")
    stored = copy.deepcopy(result)
    stored["meta"]["versionId"] = "test-version"
    stored["participant"][0]["actor"]["reference"] = BASE + "Patient/demo-patient-002"
    compare(result, stored)
    stored["participant"][0]["actor"]["reference"] = "http://other-server/Patient/demo-patient-002"
    try:
        compare(result, stored)
    except ValueError:
        pass
    else:
        raise AssertionError("A different reference base was accepted.")
    print("PASS: offline mapping, stable ID, timestamp and reference checks.")


def run(root):
    sample_names = ["admission-002.fhir.json", "lab-002.fhir.json", "lab-003.fhir.json"]
    sample_paths = [root / "samples" / name for name in sample_names]
    expected = [json.loads(path.read_text()) for path in sample_paths]
    require(expected[0]["resourceType"] == "Patient", "Patient conversion is missing.")
    patient_id = expected[0]["id"]
    query = urlencode({"identifier": MRN_SYSTEM + "|SYN002", "_count": "2"})
    bundle, _ = request_json("Patient?" + query)
    require(bundle.get("resourceType") == "Bundle", "Patient search did not return a Bundle.")
    matches = [entry["resource"] for entry in bundle.get("entry", [])
               if entry.get("resource", {}).get("resourceType") == "Patient"]
    require(len(matches) == 1 and bundle.get("total", 1) == 1
            and not any(link.get("relation") == "next" for link in bundle.get("link", [])),
            "Patient identifier must resolve to exactly one patient.")
    require(matches[0]["id"] == patient_id, "Patient search disagrees with the admission conversion.")
    require(any(i.get("system") == MRN_SYSTEM and i.get("value") == "SYN002"
                for i in matches[0].get("identifier", [])), "Patient identifier mismatch.")
    # Check existing converted resources before creating a new appointment.
    for converted in expected:
        stored, _ = request_json(converted["resourceType"] + "/" + converted["id"])
        compare(converted, stored)
    print("PASS: patient identity and existing patient/labs verified.")

    source = root / "samples" / "appointment-bridge-001.hl7"
    raw = fixture()
    if source.exists():
        require(source.read_bytes() == raw, "Existing scheduling sample differs; review it first.")
    else:
        source.write_bytes(raw)
    appointment = convert(source.read_bytes(), patient_id)
    converted_path = source.with_suffix(".fhir.json")
    if converted_path.exists():
        require(json.loads(converted_path.read_text()) == appointment,
                "Existing converted appointment differs; review it first.")
    else:
        converted_path.write_text(json.dumps(appointment, indent=2) + "\n")
    print("PASS: SIU^S12 converted to Appointment/" + appointment["id"])

    path = "Appointment/" + appointment["id"]
    try:
        stored, _ = request_json(path)
    except HTTPError as error:
        if error.code != 404:
            raise
        # Single-user demonstration: a new deterministic ID, no existing update.
        _, status = request_json(path, data=appointment, method="PUT")
        require(status == 201, "Expected a newly created appointment (HTTP 201); review result.")
        print("Appointment created: HTTP 201")
        stored, _ = request_json(path)
    else:
        print("Appointment already exists; no update performed.")
    compare(appointment, stored)
    print("PASS: appointment read-back matches conversion.")

    expected.append(appointment)
    sample_paths.append(converted_path)
    source_paths = [root / "samples" / name.replace(".fhir.json", ".hl7") for name in sample_names]
    source_paths.append(source)
    # Verify source availability before emitting any export.
    for source_path in source_paths:
        require(source_path.is_file(), "Missing HL7 source: " + str(source_path))
    exported = [request_json(r["resourceType"] + "/" + r["id"])[0] for r in expected]
    for converted, stored in zip(expected, exported):
        compare(converted, stored)
    second = [request_json(r["resourceType"] + "/" + r["id"])[0] for r in expected]
    require(exported == second, "Firely changed between reads; rerun the script.")
    batch_id = "hl7-appointment-bridge-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = root / "analytics" / "batches" / batch_id
    output.mkdir(parents=True, exist_ok=False)
    files = {}
    for resource_type in ["Patient", "Observation", "Appointment"]:
        rows = [r for r in exported if r["resourceType"] == resource_type]
        data = b"".join(encode(r) + b"\n" for r in rows)
        filename = resource_type + ".ndjson"
        (output / filename).write_bytes(data)
        files[filename] = {"rows": len(rows), "sha256": sha(data)}
    lineage = []
    for source_path, converted_path, resource in zip(source_paths, sample_paths, exported):
        lineage.append({"hl7_file": str(source_path.relative_to(root)),
                        "hl7_sha256": sha(source_path.read_bytes()),
                        "converted_file": str(converted_path.relative_to(root)),
                        "converted_sha256": sha(converted_path.read_bytes()),
                        "resource_type": resource["resourceType"], "resource_id": resource["id"],
                        "firely_version": resource.get("meta", {}).get("versionId"),
                        "exported_payload_sha256": sha(encode(resource))})
    manifest = {"batch_id": batch_id, "source_base_url": BASE,
                "route": "HL7-derived local Firely resources to Snowflake internal stage",
                "consistency": "two matching reads; not a locked snapshot",
                "comparison": "converted fields match; exact local reference base normalized",
                "scope": "synthetic single-patient SIU S12 booking fixture; not full profile validation",
                "converter_sha256": sha(Path(__file__).read_bytes()),
                "files": files, "lineage": lineage}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("PASS: all four converted resources match Firely and two reads agree.")
    print("Batch ID:", batch_id)
    print("Export folder:", output)
    for filename, info in files.items():
        print(filename + ": " + str(info["rows"]) + " row(s)")
    print("manifest.json: source hashes and resource lineage")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="Offline tests; no Firely reads/writes")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    root = args.project_root.resolve()
    require((root / "samples" / "admission-002.fhir.json").is_file(),
            "Run from your existing firely-learning folder.")
    self_test()
    run(root)


if __name__ == "__main__":
    try:
        main()
    except HTTPError as error:
        print("STOP: HTTP", error.code, error.read().decode("utf-8", errors="replace"))
        raise SystemExit(1)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print("STOP:", error)
        raise SystemExit(1)
