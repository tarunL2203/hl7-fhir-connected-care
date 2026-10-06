"""Deterministic synthetic fixture generator; no network or real patient inputs."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
from collections import Counter
import json,csv,copy,hashlib
ROOT=Path(__file__).resolve().parent
BATCH='synthetic-failure-cases-20261006-v1'
UTC=timezone.utc
START=datetime(2026,10,20,13,tzinfo=UTC)
SCENARIOS=[('complete',8,4),('missing_birth_date',3,4),('no_observations',3,0),('outside_window',3,4),('preliminary_only',3,3),('at_appointment',2,3),('cancelled_appointment',2,2),('unconfigured_requirement',2,2),('invalid_timestamp',2,2),('broken_patient_reference',2,2)]
def stamp(d):return d.isoformat(timespec='seconds').replace('+00:00','Z')
def meta(version=1):return {'versionId':str(version),'lastUpdated':f'2026-10-06T{15+version:02d}:00:00Z','tag':[{'system':'https://example.org/fixture-label','code':'synthetic'}]}
def write_ndjson(path,items):path.write_text(''.join(json.dumps(x,separators=(',',':'),sort_keys=True)+'\n' for x in items))
def write_csv(path,items):
 with path.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(items[0]));w.writeheader();w.writerows(items)
def generate():
 patients=[];observations=[];appointments=[];expected=[];config=[];issues=[];idx=0
 for scenario,n,nobs in SCENARIOS:
  for _ in range(n):
   idx+=1;pid=f'fc30-p{idx:03d}';aid=f'fc30-a{idx:03d}';start=START+timedelta(days=(idx-1)%3)
   p={'resourceType':'Patient','id':pid,'meta':meta(),'identifier':[{'system':'https://example.org/synthetic-patient-id','value':pid}],'active':True,'name':[{'use':'official','family':'Synthetic','given':[f'Person{idx:02d}']}],'gender':'unknown'}
   if scenario!='missing_birth_date':p['birthDate']=f'{1970+idx:04d}-06-15'
   patients.append(p)
   a={'resourceType':'Appointment','id':aid,'meta':meta(),'status':'cancelled' if scenario=='cancelled_appointment' else 'booked','start':stamp(start),'end':stamp(start+timedelta(minutes=30)),'serviceType':[{'coding':[{'system':'https://example.org/synthetic-visit-types','code':'demo-glucose-review'}]}],'participant':[{'actor':{'reference':f'Patient/{pid}'},'status':'accepted'}]}
   appointments.append(a)
   if scenario!='unconfigured_requirement':config.append({'batch_id':BATCH,'appointment_id':aid,'requirement_code':'demo-glucose-mgdl-7d','window_days':7,'accepted_unit_code':'mg/dL','enabled':'true'})
   for j in range(nobs):
    when=start-timedelta(days=1+j,hours=j)
    if scenario=='outside_window':when=start-timedelta(days=8+j)
    if scenario=='at_appointment':when=start+timedelta(minutes=j)
    if scenario=='invalid_timestamp':when=start-timedelta(days=8)
    ref=f'Patient/{pid}' if scenario!='broken_patient_reference' else f'Patient/fc30-unknown-{idx:03d}'
    o={'resourceType':'Observation','id':f'fc30-o{idx:03d}-{j+1:02d}','meta':meta(),'status':'preliminary' if scenario=='preliminary_only' else 'final','category':[{'coding':[{'system':'http://terminology.hl7.org/CodeSystem/observation-category','code':'laboratory'}]}],'code':{'coding':[{'system':'http://loinc.org','code':'2345-7','display':'Glucose [Mass/volume] in Serum or Plasma'}]},'subject':{'reference':ref},'effectiveDateTime':stamp(when),'valueQuantity':{'value':90+idx+j*3,'unit':'mg/dL','system':'http://unitsofmeasure.org','code':'mg/dL'}}
    if scenario=='invalid_timestamp' and j==0:
     o['effectiveDateTime']='2026-13-40T25:61:00Z';issues.append({'resource_type':'Observation','resource_id':o['id'],'issue':'invalid_timestamp','intended_fixture_patient_id':pid,'handling':'retain source payload; unable_to_assess'})
    if scenario=='broken_patient_reference':issues.append({'resource_type':'Observation','resource_id':o['id'],'issue':'unknown_patient_reference','intended_fixture_patient_id':pid,'handling':'retain unresolved reference; do not silently relink'})
    if idx==2 and j==0:o['effectiveDateTime']=stamp(start-timedelta(days=7))
    if idx==3 and j==0:o['effectiveDateTime']=(when.astimezone(timezone(timedelta(hours=-4)))).isoformat(timespec='seconds')
    if idx==4 and j==0:
     o['code']['coding']=[{'system':'http://loinc.org','code':'14749-6','display':'Glucose [Moles/volume] in Serum or Plasma'}]
     o['valueQuantity']={'value':5.5,'unit':'mmol/L','system':'http://unitsofmeasure.org','code':'mmol/L'}
    if idx==5 and j==0:
     o['code']['coding']=[{'system':'http://loinc.org','code':'718-7','display':'Hemoglobin [Mass/volume] in Blood'}]
     o['valueQuantity']={'value':13.4,'unit':'g/dL','system':'http://unitsofmeasure.org','code':'g/dL'}
    observations.append(o)
   q=nobs if scenario in ('complete','missing_birth_date','cancelled_appointment','unconfigured_requirement') else 0
   if idx in (4,5):q-=1
   status='information_complete' if scenario in ('complete','missing_birth_date') else 'information_gap'
   if scenario=='cancelled_appointment':status='not_applicable'
   if scenario=='unconfigured_requirement':status='requirements_not_configured'
   if scenario=='invalid_timestamp':status='unable_to_assess'
   expected.append({'batch_id':BATCH,'patient_id':pid,'appointment_id':aid,'scenario':scenario,'birth_date_status':'missing' if scenario=='missing_birth_date' else 'valid','expected_linked_observation_count':0 if scenario=='broken_patient_reference' else nobs,'expected_qualifying_glucose_count':q,'expected_information_availability':status,'expected_review_issue':'unknown_patient_reference' if scenario=='broken_patient_reference' else ('invalid_timestamp' if scenario=='invalid_timestamp' else ''),'expected_release_state':'hold_for_reference_review' if scenario=='broken_patient_reference' else 'normal','appointment_time_utc':stamp(start)})
 delivery=copy.deepcopy(observations)
 # Exact delivery duplicates (same resource, version and payload).
 for i in [1,8,20]:delivery.append(copy.deepcopy(observations[i]))
 corrected=copy.deepcopy(observations[0]);corrected['meta']=meta(2);corrected['status']='corrected';corrected['valueQuantity']['value']=101
 delivery.append(corrected)
 canonical=copy.deepcopy(observations);canonical[0]=corrected
 for folder,obs in [('canonical',canonical),('delivery',delivery)]:
  d=ROOT/folder;d.mkdir(exist_ok=True)
  for name,items in [('Patient',patients),('Observation',obs),('Appointment',appointments)]:write_ndjson(d/f'{name}.ndjson',items)
 write_csv(ROOT/'expected-outcomes.csv',expected);write_csv(ROOT/'appointment-requirements.csv',config);write_csv(ROOT/'expected-review-issues.csv',issues)
 summary={'batch_id':BATCH,'synthetic_only':True,'counts':{'canonical':{'Patient':30,'Observation':87,'Appointment':30,'total':147},'delivery':{'Patient':30,'Observation':91,'Appointment':30,'total':151},'distinct_resource_versions':148,'exact_duplicate_deliveries':3,'additional_corrected_version':1},'expected_status_counts':dict(Counter(x['expected_information_availability'] for x in expected)),'expected_review_issue_counts':dict(Counter(x['issue'] for x in issues)),'version_policy':'Fixture versions are numeric; choose highest version per resource for canonical projection; retain both source versions. Do not generalize numeric version ordering to arbitrary FHIR servers.','files':[]}
 for p in sorted(ROOT.rglob('*')):
  if p.is_file() and p.suffix in ('.ndjson','.csv'):summary['files'].append({'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,'data_rows':sum(1 for _ in p.open())-(1 if p.suffix=='.csv' else 0)})
 (ROOT/'manifest.json').write_text(json.dumps(summary,indent=2)+'\n')
 verify()
 print(json.dumps({'counts':summary['counts'],'statuses':summary['expected_status_counts'],'review_issues':summary['expected_review_issue_counts']},indent=2))
def verify():
 expected=list(csv.DictReader((ROOT/'expected-outcomes.csv').open()))
 data={t:[json.loads(s) for s in (ROOT/'canonical'/f'{t}.ndjson').read_text().splitlines()] for t in ['Patient','Observation','Appointment']}
 assert [len(data[t]) for t in data]==[30,87,30]
 pids={p['id'] for p in data['Patient']};assert len(pids)==30
 configs={r['appointment_id'] for r in csv.DictReader((ROOT/'appointment-requirements.csv').open())}
 actual=[]
 for e in expected:
  a=next(x for x in data['Appointment'] if x['id']==e['appointment_id']);start=datetime.fromisoformat(a['start'].replace('Z','+00:00'))
  linked=[o for o in data['Observation'] if o['subject']['reference']==f"Patient/{e['patient_id']}"]
  q=0;bad=False
  for o in linked:
   try:tm=datetime.fromisoformat(o['effectiveDateTime'].replace('Z','+00:00'))
   except ValueError:bad=True;continue
   coding=o['code']['coding'][0];qty=o['valueQuantity']
   if coding['system']=='http://loinc.org' and coding['code']=='2345-7' and qty['system']=='http://unitsofmeasure.org' and qty['code']=='mg/dL' and o['status'] in ['final','amended','corrected'] and start-timedelta(days=7)<=tm<start:q+=1
  status='not_applicable' if a['status']=='cancelled' else ('requirements_not_configured' if a['id'] not in configs else ('unable_to_assess' if bad else ('information_complete' if q else 'information_gap')))
  assert len(linked)==int(e['expected_linked_observation_count']),(e['patient_id'],'link count')
  assert q==int(e['expected_qualifying_glucose_count']),(e['patient_id'],'qualifying count')
  assert status==e['expected_information_availability'],(e['patient_id'],'status')
  actual.append(status)
 assert Counter(actual)=={'information_complete':11,'information_gap':13,'not_applicable':2,'requirements_not_configured':2,'unable_to_assess':2}
 obsdelivery=[json.loads(s) for s in (ROOT/'delivery/Observation.ndjson').read_text().splitlines()]
 assert len(obsdelivery)==91 and len({json.dumps(o,sort_keys=True) for o in obsdelivery})==88
 assert len({o['id'] for o in obsdelivery})==87
 assert sum(o['subject']['reference'].split('/')[-1] not in pids for o in data['Observation'])==4
 for item in json.loads((ROOT/'manifest.json').read_text())['files']:assert hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()==item['sha256']
if __name__=='__main__':generate()
