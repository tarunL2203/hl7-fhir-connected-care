"""Single-user synthetic HL7 lab load and controlled protected-local snapshot refresh.
Uses the existing converter; no AWS calls, tokens, or authorization changes.
"""
import ast
import fcntl
import hashlib
import json
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent
BASE='http://localhost:8080'
SECURE='firely-learning-local-secure'
APPOINTMENT='siu-appointment-17d6d563-4f77-5aac-b49b-2367195f7423'
OLD_LABS=['demo-glucose-002','lab-760b9ffe-19ca-5dbb-b2ef-8bb12d2cf2d4']
ORDER='SYN-ORDER-PORTAL-004'
SOURCE_KEY=['DEMO','TRAINING','DEMO','SYN002','DEMO',ORDER,'1']
LAB_ID='lab-'+str(uuid.uuid5(uuid.NAMESPACE_URL,json.dumps(SOURCE_KEY)))

class UpdateError(Exception):pass

def command(args):
    try:result=subprocess.run(args,capture_output=True,text=True,timeout=75)
    except (OSError,subprocess.TimeoutExpired):raise UpdateError('Local command unavailable or timed out') from None
    if result.returncode:raise UpdateError('Local command failed: '+' '.join(args[:2]))
    return result.stdout

def request(path,resource=None,timeout=20):
    data=json.dumps(resource).encode() if resource is not None else None
    headers={'Accept':'application/fhir+json'}
    if data is not None:headers['Content-Type']='application/fhir+json'
    try:
        with urlopen(Request(BASE+'/'+path,data=data,headers=headers,method='PUT' if data is not None else 'GET'),timeout=timeout) as response:
            return response.status,json.loads(response.read())
    except HTTPError as error:
        return error.code,None

def wait_source_ready():
    # Docker start confirms the process started, not that FHIR reads are ready.
    deadline=time.monotonic()+90
    attempt=0
    while time.monotonic()<deadline:
        try:
            status,resource=request('Patient/demo-patient-002',timeout=3)
            if status==200 and resource.get('resourceType')=='Patient' and resource.get('id')=='demo-patient-002':
                print('PASS: restarted source Firely accepts patient reads.',flush=True)
                return
        except (OSError,ValueError):
            pass
        if attempt%10==0:
            print('Waiting for source Firely on localhost:8080…',flush=True)
        attempt+=1
        time.sleep(2)
    raise UpdateError('Source Firely did not become readable within 90 seconds; protected copy will be restored')

def local_ref(value):
    for base in ('http://localhost:8080/','http://localhost:8081/'):
        if isinstance(value,str) and value.startswith(base):return value[len(base):]
    return value

def converted_fields_match(stored,converted):
    if not isinstance(stored,dict):return False
    for field,expected in converted.items():
        actual=stored.get(field)
        if field=='subject':
            actual=dict(actual or {})
            if 'reference' in actual:actual['reference']=local_ref(actual['reference'])
        if actual!=expected:return False
    return True

def snapshot(paths):
    values={}
    for path in paths:
        status,resource=request(path)
        if status!=200 or resource.get('resourceType','')+'/'+resource.get('id','')!=path:
            raise UpdateError('Source read failed: '+path+' (HTTP '+str(status)+')')
        values[path]=resource
    return values

def wait_ready():
    for attempt in range(45):
        try:
            with urlopen('http://localhost:8081/$readiness',timeout=3) as response:
                if response.status==200:return
        except (OSError,HTTPError):pass
        if attempt in (0,10,20,30,40):print('Waiting for protected local Firely…',flush=True)
        time.sleep(2)
    raise UpdateError('Protected local Firely did not become ready')

def anonymous_blocked(paths):
    for path in paths:
        try:
            with urlopen('http://localhost:8081/'+path,timeout=5) as response:status=response.status
        except HTTPError as error:status=error.code
        if status!=401:raise UpdateError('Protected resource did not reject anonymous reads: '+path)

def main():
    if hashlib.sha256((ROOT/'convert_lab.py').read_bytes()).hexdigest()!=CONVERTER_SHA:
        raise UpdateError('Converter differs from the reviewed copy; no data was loaded')
    mode_path=ROOT/'worklist/spec/v2/local-integration.json'
    mode=json.loads(mode_path.read_text())
    if mode.get('mode')!='local-secure-copy':raise UpdateError('Expected protected local-copy mode')
    handler=ROOT/'worklist/document_viewer_server.py'
    handler_before=handler.read_text()
    if NEW_VERIFY in handler_before:handler_after=handler_before
    elif handler_before.count(OLD_VERIFY)==1:handler_after=handler_before.replace(OLD_VERIFY,NEW_VERIFY,1)
    else:raise UpdateError('Verification code differs; no data was loaded')
    ast.parse(handler_after)
    for name in ('firely-learning',SECURE):
        item=json.loads(command(['docker','inspect',name]))[0]
        if item['State']['Status']!='running':raise UpdateError('Start existing container first: docker start '+name)
        data=[m['Source'] for m in item['Mounts'] if m['Destination']=='/app/data']
        expected=ROOT/('data' if name=='firely-learning' else 'local-secure-data')
        if data!=[str(expected)]:raise UpdateError('Data mount differs from the verified setup')
    secure=json.loads(command(['docker','inspect',SECURE]))[0]
    env=dict(value.split('=',1) for value in secure['Config'].get('Env',[]))
    if env.get('VONK_Repository')!='SQLite' or env.get('VONK_SmartAuthorizationOptions__EnforceAccessPolicies','').lower()!='true':
        raise UpdateError('Protected SQLite settings differ; no data was loaded')
    # Check the existing patient identity before using the converter's training mapping.
    status,patient=request('Patient/demo-patient-002')
    if status!=200 or not any(i.get('system')=='https://example.org/training/mrn' and i.get('value')=='SYN002' for i in patient.get('identifier',[])):
        raise UpdateError('Training patient identity did not match')
    original_paths=['Patient/demo-patient-002']+['Observation/'+id for id in OLD_LABS]+['Appointment/'+APPOINTMENT]
    original=snapshot(original_paths)
    source=ROOT/'samples/lab-portal-update-004.hl7'
    if source.exists() and source.read_bytes()!=HL7.encode():raise UpdateError('New sample filename already has different contents')
    source.write_bytes(HL7.encode())
    command([sys.executable,str(ROOT/'convert_lab.py'),str(source)])
    converted=json.loads(source.with_suffix('.fhir.json').read_text())
    if (converted.get('resourceType')!='Observation' or converted.get('id')!=LAB_ID
        or converted.get('subject')!={'reference':'Patient/demo-patient-002'}
        or converted.get('valueQuantity',{}).get('value')!=110
        or converted.get('valueQuantity',{}).get('code')!='mg/dL'
        or converted.get('effectiveDateTime')!='2026-10-02T09:00:00-04:00'):
        raise UpdateError('Converted fields differ from the new synthetic fixture')
    print('PASS: existing HL7 converter produced',LAB_ID,flush=True)
    status,stored=request('Observation/'+LAB_ID)
    created=0
    if status==404:
        status,_=request('Observation/'+LAB_ID,converted)
        if status!=201:raise UpdateError('New lab creation did not return HTTP 201; stop here')
        created=1
        print('Lab created: HTTP 201',flush=True)
    elif status==200:
        if not converted_fields_match(stored,converted):raise UpdateError('Existing lab ID contains different data; no overwrite performed')
        print('UNCHANGED: existing lab matches; no FHIR write performed.',flush=True)
    else:raise UpdateError('Lab existence check returned HTTP '+str(status))
    status,stored=request('Observation/'+LAB_ID)
    if status!=200 or not converted_fields_match(stored,converted):raise UpdateError('Loaded lab read-back differs from conversion')
    if snapshot(original_paths)!=original:raise UpdateError('An original resource changed during this run; refresh stopped')
    paths=original_paths+['Observation/'+LAB_ID]
    current=snapshot(paths)
    previous_snapshot=Path(mode['checkpoint'])/'source-resources.json'
    if (mode.get('expected_lab_ids')==OLD_LABS+[LAB_ID] and previous_snapshot.is_file()
        and json.loads(previous_snapshot.read_text())==current and handler_before==handler_after):
        anonymous_blocked(paths)
        print('PASS: protected snapshot already current; no database refresh needed.',flush=True)
        print('Resources created this run:',created)
        print('Rerun check complete: expected 0 new resources and 3 qualifying results.')
        return
    checkpoint=ROOT/'checkpoints'/('lab-refresh-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    checkpoint.mkdir(parents=True)
    shutil.copy2(mode_path,checkpoint/'local-integration-before.json')
    shutil.copy2(handler,checkpoint/'document_viewer_server-before.py')
    (checkpoint/'source-resources.json').write_text(json.dumps(current,indent=2)+'\n')
    (checkpoint/'converted-lab.json').write_text(json.dumps(converted,indent=2)+'\n')
    (checkpoint/'source.hl7').write_bytes(source.read_bytes())
    destination=ROOT/'local-secure-data'
    pending=ROOT/('local-secure-data-pending-'+checkpoint.name)
    old_data=checkpoint/'secure-data-before'
    swapped=False
    try:
        command(['docker','stop',SECURE])
        command(['docker','stop','firely-learning'])
        try:shutil.copytree(ROOT/'data',pending)
        finally:command(['docker','start','firely-learning'])
        wait_source_ready()
        if snapshot(paths)!=current:raise UpdateError('Source changed during copy; no protected snapshot replacement performed')
        destination.rename(old_data)
        try:pending.rename(destination)
        except Exception:
            old_data.rename(destination)
            raise
        swapped=True
        command(['docker','start',SECURE])
        wait_ready()
        anonymous_blocked(paths)
        handler.write_text(handler_after)
        updated={**mode,'checkpoint':str(checkpoint),'expected_lab_ids':OLD_LABS+[LAB_ID]}
        mode_path.write_text(json.dumps(updated,indent=2)+'\n')
        (checkpoint/'refresh-evidence.json').write_text(json.dumps({
            'mode':'controlled_local_snapshot_refresh','resource_count':len(current),'new_lab_id':LAB_ID,
            'created_this_run':created,'source_hl7_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'converter_sha256':CONVERTER_SHA,'anonymous_reads_rejected':True,
            'authenticated_portal_readback':'pending normal reviewer login',
        },indent=2)+'\n')
    except Exception:
        if swapped:
            try:command(['docker','stop',SECURE])
            except UpdateError:pass
            if destination.exists():destination.rename(checkpoint/'failed-new-secure-data')
            old_data.rename(destination)
        shutil.copy2(checkpoint/'local-integration-before.json',mode_path)
        shutil.copy2(checkpoint/'document_viewer_server-before.py',handler)
        try:command(['docker','start',SECURE])
        except UpdateError:pass
        print('STOP: previous portal configuration and protected snapshot restored.',flush=True)
        print('The source lab may already exist on 8080; rerunning will check it before any write.',flush=True)
        raise
    print('PASS: protected snapshot refreshed; all 5 resources reject anonymous reads.',flush=True)
    print('Checkpoint:',checkpoint)
    print('Resources created this run:',created)
    print('REFRESH COMPLETE. Restart the viewer, sign in, load Ravi, then run verification.')
    print('Expected: 3 lab rows, including 110 mg/dL; 3 qualifying results; resource_count 5.')


CONVERTER_SHA = 'fb69ae2cdc943c6d067fb23d43614784433f77b4fa132ccc3b3aeed300aaf27a'
HL7 = 'MSH|^~\\&|DEMO|TRAINING|FIRELY|LOCAL|20261002090000-0400||ORU^R01^ORU_R01|SYN-LAB-PORTAL-004|T|2.5\rPID|1||SYN002^^^DEMO^MR||Demo^Ravi||19850512|M\rOBR|1||SYN-ORDER-PORTAL-004^DEMO|2345-7^Glucose serum or plasma^LN|||20261002090000-0400\rOBX|1|NM|2345-7^Glucose serum or plasma^LN||110|mg/dL^mg/dL^UCUM|||||F\r'
OLD_VERIFY = '        if path == "/local-integration/verify" and local_mode():\n            stage = "load_snapshot"\n            diagnostic = {}\n            try:\n                mode = json.loads((ROOT / "spec/v2/local-integration.json").read_text())\n                checkpoint = Path(mode["checkpoint"])\n                expected = json.loads((checkpoint / "source-resources.json").read_text())\n                def read_resources(label):\n                    nonlocal stage\n                    records = {}\n                    for key in expected:\n                        stage = label + ":" + key\n                        records[key] = get_json(BASE + "/" + key)\n                    return records\n                first = read_resources("authenticated_read_1")\n                second = read_resources("authenticated_read_2")\n                diagnostic["two_reads_agree"] = first == second\n                def different_fields(left, right, prefix=""):\n                    if isinstance(left, dict) and isinstance(right, dict):\n                        paths = []\n                        for key in sorted(set(left) | set(right)):\n                            path = prefix + ("." if prefix else "") + key\n                            if key not in left or key not in right:\n                                paths.append(path)\n                            else:\n                                paths.extend(different_fields(left[key], right[key], path))\n                        return paths\n                    if isinstance(left, list) and isinstance(right, list):\n                        if len(left) != len(right):\n                            return [prefix + ".length"]\n                        return [path for index, (a, b) in enumerate(zip(left, right))\n                                for path in different_fields(a, b, prefix + "[" + str(index) + "]")]\n                    return [] if left == right else [prefix]\n                diagnostic["snapshot_differences"] = {\n                    key: different_fields(expected[key], first[key])[:50]\n                    for key in expected if expected[key] != first[key]\n                }\n                stage = "portal_summary"\n                data = summary("demo-patient-002")\n                diagnostic["returned_observation_ids"] = [r["id"] for r in data["observations"]]\n                appointment_id = "siu-appointment-17d6d563-4f77-5aac-b49b-2367195f7423"\n                assessments = [a for a in data["assessments"] if a["appointment_id"] == appointment_id]\n                diagnostic["assessment_count"] = len(assessments)\n                stage = "appointment_assessment"\n                if len(assessments) != 1:\n                    raise RuntimeError("assessment_count")\n                diagnostic["assessment_outcome"] = assessments[0]["outcome"]\n                requirements = assessments[0]["requirements"]\n                diagnostic["matched_record_ids"] = [r.get("matched_record_ids", []) for r in requirements]\n                diagnostic["requirement_outcomes"] = [r.get("outcome") for r in requirements]\n                expected_labs = {"demo-glucose-002", "lab-760b9ffe-19ca-5dbb-b2ef-8bb12d2cf2d4"}\n                if assessments[0]["outcome"] != "information_complete" or len(requirements) != 1 or set(requirements[0]["matched_record_ids"]) != expected_labs:\n                    raise RuntimeError("qualifying_results")\n                stage = "snapshot_comparison"\n                def normalize_local_patient_references(resource):\n                    # Normalize only patient links in their FHIR reference fields.\n                    # Never change IDs, clinical values, timestamps, metadata or other URLs.\n                    import copy\n                    value = copy.deepcopy(resource)\n                    def normalize(reference):\n                        if not isinstance(reference, str):\n                            return reference\n                        relative = reference\n                        for base in ("http://localhost:8080/", "http://localhost:8081/"):\n                            if reference.startswith(base):\n                                relative = reference[len(base):]\n                                break\n                        return relative if re.fullmatch(r"Patient/[A-Za-z0-9.-]{1,64}", relative) else reference\n                    if value.get("resourceType") == "Observation":\n                        subject = value.get("subject")\n                        if isinstance(subject, dict) and "reference" in subject:\n                            subject["reference"] = normalize(subject["reference"])\n                    elif value.get("resourceType") == "Appointment":\n                        for participant in value.get("participant", []):\n                            actor = participant.get("actor")\n                            if isinstance(actor, dict) and "reference" in actor:\n                                actor["reference"] = normalize(actor["reference"])\n                    return value\n                normalized_expected = {key: normalize_local_patient_references(value) for key, value in expected.items()}\n                normalized_first = {key: normalize_local_patient_references(value) for key, value in first.items()}\n                diagnostic["snapshot_matches_after_local_reference_normalization"] = normalized_first == normalized_expected\n                if first != second or normalized_first != normalized_expected:\n                    raise RuntimeError("snapshot_mismatch")\n                from datetime import datetime, timezone\n                from hashlib import sha256\n                report = {"passed": True, "authenticated": True, "resource_count": len(first),\n                    "two_reads_agree": True, "original_snapshot_matches": first == expected,\n                    "snapshot_matches_after_local_reference_normalization": True,\n                    "comparison_mode": "all fields match after normalizing exact localhost:8080/8081 patient references",\n                    "normalized_reference_fields": diagnostic["snapshot_differences"],\n                    "appointment_id": appointment_id, "qualifying_glucose_count": 2,\n                    "outcome": "information_complete", "documents": "deferred",\n                    "checked_at": datetime.now(timezone.utc).isoformat(),\n                    "payload_hashes": {key: sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()\n                                       for key, value in first.items()}}\n                stage = "save_evidence"\n                evidence_dir = ROOT / "evidence"\n                evidence_dir.mkdir(parents=True, exist_ok=True)\n                name = "local-portal-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json"\n                (evidence_dir / name).write_text(json.dumps(report, indent=2) + "\\n")\n                self.send_json(200, report)\n            except Exception as error:\n                report = {"passed": False, "error": "local_bridge_verification_failed",\n                          "failed_step": stage, "error_type": type(error).__name__,\n                          "diagnostic": diagnostic}\n                status = getattr(error, "code", None)\n                if isinstance(status, int) and 400 <= status <= 599:\n                    report["upstream_http_status"] = status\n                self.send_json(502, report)\n            return\n\n'
NEW_VERIFY = '        if path == "/local-integration/verify" and local_mode():\n            stage = "load_snapshot"\n            diagnostic = {}\n            try:\n                mode = json.loads((ROOT / "spec/v2/local-integration.json").read_text())\n                checkpoint = Path(mode["checkpoint"])\n                expected = json.loads((checkpoint / "source-resources.json").read_text())\n                def read_resources(label):\n                    nonlocal stage\n                    records = {}\n                    for key in expected:\n                        stage = label + ":" + key\n                        records[key] = get_json(BASE + "/" + key)\n                    return records\n                first = read_resources("authenticated_read_1")\n                second = read_resources("authenticated_read_2")\n                diagnostic["two_reads_agree"] = first == second\n                def different_fields(left, right, prefix=""):\n                    if isinstance(left, dict) and isinstance(right, dict):\n                        paths = []\n                        for key in sorted(set(left) | set(right)):\n                            path = prefix + ("." if prefix else "") + key\n                            if key not in left or key not in right:\n                                paths.append(path)\n                            else:\n                                paths.extend(different_fields(left[key], right[key], path))\n                        return paths\n                    if isinstance(left, list) and isinstance(right, list):\n                        if len(left) != len(right):\n                            return [prefix + ".length"]\n                        return [path for index, (a, b) in enumerate(zip(left, right))\n                                for path in different_fields(a, b, prefix + "[" + str(index) + "]")]\n                    return [] if left == right else [prefix]\n                diagnostic["snapshot_differences"] = {\n                    key: different_fields(expected[key], first[key])[:50]\n                    for key in expected if expected[key] != first[key]\n                }\n                stage = "portal_summary"\n                data = summary("demo-patient-002")\n                diagnostic["returned_observation_ids"] = [r["id"] for r in data["observations"]]\n                appointment_id = "siu-appointment-17d6d563-4f77-5aac-b49b-2367195f7423"\n                assessments = [a for a in data["assessments"] if a["appointment_id"] == appointment_id]\n                diagnostic["assessment_count"] = len(assessments)\n                stage = "appointment_assessment"\n                if len(assessments) != 1:\n                    raise RuntimeError("assessment_count")\n                diagnostic["assessment_outcome"] = assessments[0]["outcome"]\n                requirements = assessments[0]["requirements"]\n                diagnostic["matched_record_ids"] = [r.get("matched_record_ids", []) for r in requirements]\n                diagnostic["requirement_outcomes"] = [r.get("outcome") for r in requirements]\n                expected_labs = set(mode.get("expected_lab_ids", ["demo-glucose-002", "lab-760b9ffe-19ca-5dbb-b2ef-8bb12d2cf2d4"]))\n                if assessments[0]["outcome"] != "information_complete" or len(requirements) != 1 or set(requirements[0]["matched_record_ids"]) != expected_labs:\n                    raise RuntimeError("qualifying_results")\n                stage = "snapshot_comparison"\n                def normalize_local_patient_references(resource):\n                    # Normalize only patient links in their FHIR reference fields.\n                    # Never change IDs, clinical values, timestamps, metadata or other URLs.\n                    import copy\n                    value = copy.deepcopy(resource)\n                    def normalize(reference):\n                        if not isinstance(reference, str):\n                            return reference\n                        relative = reference\n                        for base in ("http://localhost:8080/", "http://localhost:8081/"):\n                            if reference.startswith(base):\n                                relative = reference[len(base):]\n                                break\n                        return relative if re.fullmatch(r"Patient/[A-Za-z0-9.-]{1,64}", relative) else reference\n                    if value.get("resourceType") == "Observation":\n                        subject = value.get("subject")\n                        if isinstance(subject, dict) and "reference" in subject:\n                            subject["reference"] = normalize(subject["reference"])\n                    elif value.get("resourceType") == "Appointment":\n                        for participant in value.get("participant", []):\n                            actor = participant.get("actor")\n                            if isinstance(actor, dict) and "reference" in actor:\n                                actor["reference"] = normalize(actor["reference"])\n                    return value\n                normalized_expected = {key: normalize_local_patient_references(value) for key, value in expected.items()}\n                normalized_first = {key: normalize_local_patient_references(value) for key, value in first.items()}\n                diagnostic["snapshot_matches_after_local_reference_normalization"] = normalized_first == normalized_expected\n                if first != second or normalized_first != normalized_expected:\n                    raise RuntimeError("snapshot_mismatch")\n                from datetime import datetime, timezone\n                from hashlib import sha256\n                report = {"passed": True, "authenticated": True, "resource_count": len(first),\n                    "two_reads_agree": True, "original_snapshot_matches": first == expected,\n                    "snapshot_matches_after_local_reference_normalization": True,\n                    "comparison_mode": "all fields match after normalizing exact localhost:8080/8081 patient references",\n                    "normalized_reference_fields": diagnostic["snapshot_differences"],\n                    "appointment_id": appointment_id, "qualifying_glucose_count": len(expected_labs),\n                    "outcome": "information_complete", "documents": "deferred",\n                    "checked_at": datetime.now(timezone.utc).isoformat(),\n                    "payload_hashes": {key: sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()\n                                       for key, value in first.items()}}\n                stage = "save_evidence"\n                evidence_dir = ROOT / "evidence"\n                evidence_dir.mkdir(parents=True, exist_ok=True)\n                name = "local-portal-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json"\n                (evidence_dir / name).write_text(json.dumps(report, indent=2) + "\\n")\n                self.send_json(200, report)\n            except Exception as error:\n                report = {"passed": False, "error": "local_bridge_verification_failed",\n                          "failed_step": stage, "error_type": type(error).__name__,\n                          "diagnostic": diagnostic}\n                status = getattr(error, "code", None)\n                if isinstance(status, int) and 400 <= status <= 599:\n                    report["upstream_http_status"] = status\n                self.send_json(502, report)\n            return\n\n'

if __name__=='__main__':
    try:
        lock_path=ROOT/'checkpoints/lab-update.lock'
        lock_path.parent.mkdir(parents=True,exist_ok=True)
        with lock_path.open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            main()
    except UpdateError as error:
        print('STOP:',str(error));sys.exit(1)
    except Exception as error:
        print('STOP: local update failed:',type(error).__name__);sys.exit(1)
