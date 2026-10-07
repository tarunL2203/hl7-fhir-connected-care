"""Bounded export through the verified reviewer session. Never exports credentials."""
import copy
import hashlib
import io
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from auth_fhir import ACCESS_TOKEN, BASE, get_json
from summary_api import ROOT, summary

APPOINTMENT='siu-appointment-17d6d563-4f77-5aac-b49b-2367195f7423'
LABS=['demo-glucose-002','lab-760b9ffe-19ca-5dbb-b2ef-8bb12d2cf2d4','lab-60c75c14-03f1-5417-858a-ac1f33afdaa4']
SOURCES={
 'Patient/demo-patient-002':'samples/admission-002.hl7',
 'Observation/demo-glucose-002':'samples/lab-002.hl7',
 'Observation/lab-760b9ffe-19ca-5dbb-b2ef-8bb12d2cf2d4':'samples/lab-003.hl7',
 'Appointment/'+APPOINTMENT:'samples/appointment-bridge-001.hl7',
 'Observation/'+LABS[2]:'samples/lab-portal-update-004.hl7',
}

def fail(reason, **details):
 error=RuntimeError('Export validation failed')
 error.safe_diagnostic={'reason':reason,**details}
 raise error

def digest(data):return hashlib.sha256(data).hexdigest()

def normalized(resource):
 value=copy.deepcopy(resource)
 def ref(reference):
  if not isinstance(reference,str):return reference
  relative=reference
  for base in ('http://localhost:8080/','http://localhost:8081/'):
   if reference.startswith(base):relative=reference[len(base):];break
  return relative if re.fullmatch(r'Patient/[A-Za-z0-9.-]{1,64}',relative) else reference
 if value.get('resourceType')=='Observation':
  value['subject']['reference']=ref(value['subject']['reference'])
 elif value.get('resourceType')=='Appointment':
  for p in value.get('participant',[]):
   actor=p.get('actor',{})
   if 'reference' in actor:actor['reference']=ref(actor['reference'])
 return value

def sql_files(batch_id,stage):
 context='USE ROLE ACCOUNTADMIN;\nUSE WAREHOUSE FIRELY_DEMO_WH;\nUSE DATABASE CHATGPT_LAB;\nUSE SCHEMA FIRELY_RAW_5DD08717;\n'
 table='FHIR_RESOURCE_HL7_PORTAL_REFRESH'
 setup=context+f'''-- Run this first. Expected: stage and table created or already exist.
CREATE STAGE IF NOT EXISTS {stage} FILE_FORMAT=(TYPE=JSON);
CREATE TABLE IF NOT EXISTS {table} LIKE FHIR_RESOURCE_INTERNAL;
-- Upload ONLY Patient.ndjson, Observation.ndjson, Appointment.ndjson to this stage.
LIST @{stage};
-- After uploading: expected 3 named resource files.
'''
 load=context+f'''-- Expected first run: 1 Patient + 3 Observations + 1 Appointment loaded.
-- Rerun this COPY block only: expected 0 additional rows. Keep FORCE=FALSE.
COPY INTO {table}
(payload,resource_type,resource_id,batch_id,source_filename,file_row_number,loaded_at)
FROM (SELECT t.$1,t.$1:resourceType::VARCHAR,t.$1:id::VARCHAR,
'{batch_id}',METADATA$FILENAME,METADATA$FILE_ROW_NUMBER,METADATA$START_SCAN_TIME
FROM @{stage} AS t)
FILES=('Patient.ndjson','Observation.ndjson','Appointment.ndjson')
FILE_FORMAT=(TYPE=JSON) ON_ERROR='ABORT_STATEMENT' FORCE=FALSE;

-- Expected: Appointment 1/1, Observation 3/3, Patient 1/1.
SELECT RESOURCE_TYPE,COUNT(*) AS ROWS_LOADED,COUNT(DISTINCT RESOURCE_ID) AS UNIQUE_IDS
FROM {table} WHERE BATCH_ID='{batch_id}'
GROUP BY RESOURCE_TYPE ORDER BY RESOURCE_TYPE;

-- Expected: 1 row, 3 qualifying results, information_complete.
WITH batch AS (
 SELECT * FROM {table} WHERE BATCH_ID='{batch_id}'
), appointments AS (
 SELECT DISTINCT b.RESOURCE_ID AS APPOINTMENT_ID,b.PAYLOAD:status::VARCHAR AS APPOINTMENT_STATUS,
 TRY_TO_TIMESTAMP_TZ(b.PAYLOAD:start::VARCHAR) AS START_TIME,
 REGEXP_REPLACE(p.VALUE:actor:reference::VARCHAR,'^http://localhost:808[01]/','') AS PATIENT_REFERENCE
 FROM batch b,LATERAL FLATTEN(INPUT=>b.PAYLOAD:participant) p
 WHERE b.RESOURCE_TYPE='Appointment' AND b.RESOURCE_ID='{APPOINTMENT}'
 AND REGEXP_REPLACE(p.VALUE:actor:reference::VARCHAR,'^http://localhost:808[01]/','')='Patient/demo-patient-002'
), observations AS (
 SELECT DISTINCT b.RESOURCE_ID,
 REGEXP_REPLACE(b.PAYLOAD:subject:reference::VARCHAR,'^http://localhost:808[01]/','') AS PATIENT_REFERENCE,
 TRY_TO_TIMESTAMP_TZ(b.PAYLOAD:effectiveDateTime::VARCHAR) AS RESULT_TIME
 FROM batch b,LATERAL FLATTEN(INPUT=>b.PAYLOAD:code:coding) c
 WHERE b.RESOURCE_TYPE='Observation'
 AND c.VALUE:system::VARCHAR='http://loinc.org' AND c.VALUE:code::VARCHAR='2345-7'
 AND b.PAYLOAD:status::VARCHAR IN ('final','amended','corrected')
 AND b.PAYLOAD:valueQuantity:system::VARCHAR='http://unitsofmeasure.org'
 AND b.PAYLOAD:valueQuantity:code::VARCHAR='mg/dL'
 AND TRY_TO_DOUBLE(b.PAYLOAD:valueQuantity:value::VARCHAR) BETWEEN -1e308 AND 1e308
)
SELECT 'demo-patient-002' AS PATIENT_ID,a.APPOINTMENT_ID,a.APPOINTMENT_STATUS,a.START_TIME,
COUNT(DISTINCT o.RESOURCE_ID) AS QUALIFYING_GLUCOSE_COUNT,
CASE WHEN a.APPOINTMENT_STATUS='cancelled' THEN 'not_applicable'
WHEN a.START_TIME IS NULL THEN 'unable_to_assess'
WHEN COUNT(DISTINCT o.RESOURCE_ID)>0 THEN 'information_complete' ELSE 'information_gap' END AS INFORMATION_AVAILABILITY
FROM appointments a LEFT JOIN observations o ON o.PATIENT_REFERENCE=a.PATIENT_REFERENCE
AND o.RESULT_TIME>=DATEADD(day,-7,a.START_TIME) AND o.RESULT_TIME<a.START_TIME
GROUP BY a.APPOINTMENT_ID,a.APPOINTMENT_STATUS,a.START_TIME;
'''
 reconcile=context+f'''-- Run this SELECT alone. Expected 5 rows.
-- Download its CSV as portal-refresh-raw.csv for full reconciliation.
SELECT BATCH_ID,RESOURCE_TYPE,RESOURCE_ID,SOURCE_FILENAME,FILE_ROW_NUMBER,
TO_JSON(PAYLOAD) AS PAYLOAD_JSON FROM {table}
WHERE BATCH_ID='{batch_id}' ORDER BY RESOURCE_TYPE,RESOURCE_ID;
'''
 return {'01_setup.sql':setup,'02_load_and_report.sql':load,'03_reconciliation.sql':reconcile}

def converted_differences(observed, mapped):
 differences=[]
 for field,value in mapped.items():
  actual=observed.get(field)
  if field=='meta' and isinstance(value,dict) and isinstance(actual,dict):
   # Compare every supplied metadata field; permit additional server metadata.
   for name,expected in value.items():
    if name=='tag' and isinstance(expected,list) and isinstance(actual.get(name),list):
     if any(tag not in actual[name] for tag in expected):differences.append('meta.tag')
    elif actual.get(name)!=expected:differences.append('meta.'+name)
  elif actual!=value:differences.append(field)
 return differences

def build_export():
 if not ACCESS_TOKEN.get():fail('authenticated_session_required')
 if BASE!='http://localhost:8081':fail('unexpected_fhir_source')
 project=ROOT.parent
 mode=json.loads((ROOT/'spec/v2/local-integration.json').read_text())
 if mode.get('mode')!='local-secure-copy' or set(mode.get('expected_lab_ids',[]))!=set(LABS):fail('five_resource_refresh_not_configured')
 baseline=json.loads((Path(mode['checkpoint'])/'source-resources.json').read_text())
 if set(baseline)!=set(SOURCES):fail('snapshot_cohort_differs', expected_resource_ids=sorted(SOURCES), snapshot_resource_ids=sorted(baseline))
 started=datetime.now(timezone.utc).isoformat()
 first={key:get_json(BASE+'/'+key) for key in sorted(SOURCES)}
 second={key:get_json(BASE+'/'+key) for key in sorted(SOURCES)}
 finished=datetime.now(timezone.utc).isoformat()
 if first!=second or {k:normalized(v) for k,v in first.items()}!={k:normalized(v) for k,v in baseline.items()}:
  fail('authenticated_reads_or_snapshot_differ', two_reads_agree=first==second, differing_resources=[key for key in first if normalized(first[key])!=normalized(baseline[key])])
 assessment=[a for a in summary('demo-patient-002')['assessments'] if a['appointment_id']==APPOINTMENT]
 if len(assessment)!=1 or assessment[0]['outcome']!='information_complete':fail('assessment_incomplete', assessment_count=len(assessment), outcomes=[value.get('outcome') for value in assessment])
 req=assessment[0]['requirements']
 if len(req)!=1 or set(req[0]['matched_record_ids'])!=set(LABS):fail('qualifying_results_differ', matched_record_ids=[value.get('matched_record_ids',[]) for value in req])
 lineage=[]
 for key,filename in SOURCES.items():
  source=project/filename;converted=source.with_suffix('.fhir.json')
  converted_value=json.loads(converted.read_text())
  observed=normalized(first[key]);mapped=normalized(converted_value)
  if converted_value.get('resourceType','')+'/'+converted_value.get('id','')!=key or converted_differences(observed,mapped):
   fail('converted_source_differs', resource=key, converted_identity=converted_value.get('resourceType','')+'/'+converted_value.get('id',''), differing_fields=converted_differences(observed,mapped))
  lineage.append({'resource':key,'hl7_file':filename,'hl7_sha256':digest(source.read_bytes()),
   'converted_file':str(converted.relative_to(project)),'converted_sha256':digest(converted.read_bytes()),
   'exported_payload_sha256':digest(json.dumps(first[key],sort_keys=True,separators=(',',':')).encode())})
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
 batch_id='hl7-portal-refresh-'+stamp
 stage='FHIR_PORTAL_STAGE_'+stamp.upper()
 files={};file_info={}
 for type in ('Patient','Observation','Appointment'):
  values=[first[key] for key in sorted(first) if first[key].get('resourceType')==type]
  data=('\n'.join(json.dumps(value,separators=(',',':'),ensure_ascii=False) for value in values)+'\n').encode()
  filename=type+'.ndjson';files[filename]=data;file_info[filename]={'rows':len(values),'sha256':digest(data)}
 report={'passed':True,'authenticated':True,'resource_count':5,'two_reads_agree':True,
  'snapshot_matches_after_local_reference_normalization':True,'appointment_id':APPOINTMENT,
  'qualifying_glucose_count':3,'outcome':'information_complete','checked_at':finished,
  'payload_hashes':{key:digest(json.dumps(value,sort_keys=True,separators=(',',':')).encode()) for key,value in first.items()}}
 manifest={'batch_id':batch_id,'source':BASE,'authenticated':True,'read_started_at':started,
  'read_finished_at':finished,'source_consistency':'two equal authenticated reads; not a transactionally locked snapshot',
  'files':file_info,'lineage':lineage,'snowflake_stage':stage,'snowflake_table':'FHIR_RESOURCE_HL7_PORTAL_REFRESH'}
 files['manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
 files['portal-verification.json']=(json.dumps(report,indent=2)+'\n').encode()
 files.update({name:text.encode() for name,text in sql_files(batch_id,stage).items()})
 files['reconcile_bridge.py']=RECONCILER.encode()
 files['START-HERE.txt']=f'''Verified portal export: 1 Patient, 3 Observations, 1 Appointment.
Batch: {batch_id}
Stage: {stage}

1. Unzip this download. Create a new Snowflake SQL worksheet.
2. Paste/run 01_setup.sql. Expected: stage/table created or already exist.
3. Upload ONLY Patient.ndjson, Observation.ndjson, Appointment.ndjson to the named stage, at its root.
   Exclude manifest.json, SQL, Python and evidence files. Expected: 3 staged files.
4. Paste/run 02_load_and_report.sql. Expected counts 1/3/1, and 3 qualifying results -> information_complete.
   Download the final report CSV as portal-refresh-report.csv.
5. Run 03_reconciliation.sql alone. Download CSV as portal-refresh-raw.csv (expected 5 rows).
6. From your Mac project terminal run:
   document-tools-venv/bin/python analytics/batches/{batch_id}/reconcile_bridge.py analytics/batches/{batch_id} ~/Downloads/portal-refresh-raw.csv
   Expected: all 5 full payloads and file row numbers match; source hashes match.
7. Rerun ONLY the COPY block in 02_load_and_report.sql, preserving FORCE=FALSE.
   Expected: 0 additional rows and counts remain 1/3/1.

This batch is ready to load; SQL generation does not prove a Snowflake load.
FHIR resources were read through a verified reviewer session. No tokens/cookies are included.
The local protected service is a controlled snapshot copy, refreshed by a command.
The 30-patient failure-case dataset is a separate synthetic analytics dataset.
'''.encode()
 batch_dir=project/'analytics/batches'/batch_id
 batch_dir.mkdir(parents=True,exist_ok=False)
 try:
  for name,data in files.items():(batch_dir/name).write_bytes(data)
  buffer=io.BytesIO()
  with ZipFile(buffer,'w',ZIP_DEFLATED) as archive:
   for name,data in files.items():archive.writestr(name,data)
  zipped=buffer.getvalue()
  (batch_dir.parent/(batch_id+'.zip')).write_bytes(zipped)
 except Exception:
  shutil.rmtree(batch_dir)
  raise
 return batch_id+'.zip',zipped

RECONCILER = '"""Compare a downloaded Snowflake CSV to an existing Firely batch export.\n\nRun from firely-learning:\n document-tools-venv/bin/python reconcile_bridge.py analytics/batches/BATCH ~/Downloads/EXPORT.csv\n"""\nimport csv\nimport hashlib\nimport json\nimport sys\nfrom decimal import Decimal\nfrom pathlib import Path\n\n\ndef check(condition, message):\n    if not condition:\n        raise ValueError(message)\n\n\ndef reconcile(batch, csv_path, project_root):\n    manifest = json.loads((batch / "manifest.json").read_text())\n    batch_id = manifest["batch_id"]\n    expected = {}\n    for filename, info in manifest["files"].items():\n        check(Path(filename).name == filename, "Manifest filename must be a basename")\n        data = (batch / filename).read_bytes()\n        check(hashlib.sha256(data).hexdigest() == info["sha256"], "Export file hash differs: " + filename)\n        lines = data.decode("utf-8").splitlines()\n        check(len(lines) == info["rows"], "Export row count differs: " + filename)\n        for row_number, line in enumerate(lines, 1):\n            payload = json.loads(line)\n            key = (payload["resourceType"], payload["id"])\n            check(key not in expected, "Duplicate exported resource ID")\n            expected[key] = (payload, filename, row_number)\n    with csv_path.open(newline="", encoding="utf-8-sig") as handle:\n        reader = csv.DictReader(handle)\n        check(reader.fieldnames is not None, "CSV has no header")\n        required = {"BATCH_ID", "RESOURCE_TYPE", "RESOURCE_ID", "SOURCE_FILENAME", "FILE_ROW_NUMBER", "PAYLOAD_JSON"}\n        check(required.issubset({name.upper() for name in reader.fieldnames}), "CSV is missing required columns")\n        rows = [{key.upper(): value for key, value in row.items()} for row in reader]\n    check(len(rows) == len(expected), "Loaded count differs from export")\n    seen = set()\n    for row in rows:\n        key = (row["RESOURCE_TYPE"], row["RESOURCE_ID"])\n        check(row["BATCH_ID"] == batch_id, "Wrong batch ID")\n        check(key in expected, "Unexpected loaded resource")\n        check(key not in seen, "Duplicate loaded resource")\n        seen.add(key)\n        payload, filename, row_number = expected[key]\n        check(json.loads(row["PAYLOAD_JSON"]) == payload, "Payload differs: " + str(key))\n        check(Path(row["SOURCE_FILENAME"]).name == filename, "Source filename differs")\n        check(Decimal(row["FILE_ROW_NUMBER"]) == row_number, "Source row number differs")\n        print("MATCH:", "/".join(key))\n    check(seen == set(expected), "Exported resources are missing")\n    # Independently verify source-file hashes when these files are available.\n    for item in manifest.get("lineage", []):\n        for field, hash_field in [("hl7_file", "hl7_sha256"), ("converted_file", "converted_sha256")]:\n            path = Path(item[field])\n            if not path.is_absolute():\n                path = project_root / path\n            check(path.is_file(), "Source file missing: " + str(path))\n            check(hashlib.sha256(path.read_bytes()).hexdigest() == item[hash_field],\n                  "Source hash differs: " + str(path))\n    print(f"PASS: all {len(expected)} payloads and source rows match the Firely export.")\n    print("PASS: available HL7 and converted source files match manifest hashes.")\n\n\nif __name__ == "__main__":\n    if len(sys.argv) != 3:\n        raise SystemExit("Usage: reconcile_bridge.py BATCH_DIRECTORY SNOWFLAKE_CSV")\n    try:\n        reconcile(Path(sys.argv[1]).expanduser(), Path(sys.argv[2]).expanduser(), Path.cwd())\n    except (ValueError, KeyError, TypeError, OSError) as error:\n        raise SystemExit("FAIL: " + str(error))\n'
