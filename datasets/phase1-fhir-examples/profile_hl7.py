"""Profile official HL7 R4 example NDJSON; no source edits or clinical inference.
Usage: python profile_hl7.py examples-ndjson.zip output_directory
"""
import collections,csv,hashlib,json,re,sys,zipfile
from pathlib import Path
src=Path(sys.argv[1]); out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
rows=[]
with zipfile.ZipFile(src) as z:
 for n in z.namelist():
  if n.endswith('/'):continue
  for i,l in enumerate(z.read(n).decode('utf-8-sig').splitlines(),1):
   if l.strip():rows.append((n,i,json.loads(l)))
idx=collections.Counter((r.get('resourceType'),r.get('id')) for _,_,r in rows)
def csvout(name,headers,data):
 with (out/name).open('w',newline='') as f:
  w=csv.writer(f);w.writerow(headers);w.writerows(data)
def references(obj,path=''):
 if isinstance(obj,dict):
  for k,v in obj.items():
   p=path+'.'+k if path else k
   if k=='reference' and isinstance(v,str):yield p,v
   else:yield from references(v,p)
 elif isinstance(obj,list):
  for i,v in enumerate(obj):yield from references(v,f'{path}[{i}]')
counts=collections.Counter(r['resourceType'] for _,_,r in rows)
csvout('resource_inventory.csv',['resource_type','records'],sorted(counts.items()))
links=[]
for n,i,r in rows:
 for path,ref in references(r):
  if ref.startswith('#'):status='contained_reference_not_evaluated'
  elif re.fullmatch(r'[A-Za-z]+/[^/]+',ref):status='resolved_in_archive' if tuple(ref.split('/')) in idx else 'unresolved_in_archive'
  else:status='absolute_versioned_or_other_not_evaluated'
  links.append((r['resourceType'],r.get('id'),path,ref,status))
csvout('reference_audit.csv',['resource_type','resource_id','field_path','reference','resolution'],links)
clinical=['Patient','Appointment','Observation','Condition','Medication','MedicationRequest','MedicationStatement','AllergyIntolerance','Encounter','DiagnosticReport','DocumentReference']
selected=[r for _,_,r in rows if r['resourceType'] in clinical]
(out/'s3_upload').mkdir(exist_ok=True)
manifest=[]
for t in clinical:
 rr=[r for r in selected if r['resourceType']==t]
 b=''.join(json.dumps(r,separators=(',',':'),ensure_ascii=False)+'\n' for r in rr).encode()
 (out/'s3_upload'/f'{t}.ndjson').write_bytes(b)
 manifest.append({'file':t+'.ndjson','records':len(rr),'sha256':hashlib.sha256(b).hexdigest()})
(out/'manifest.json').write_text(json.dumps({'source_url':'https://hl7.org/fhir/R4/examples-ndjson.zip','source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'source_dataset':'hl7_r4_official_examples','batch_id':'hl7-r4-examples-20261008-v1','files':manifest},indent=2))
coverage=collections.defaultdict(collections.Counter)
for r in selected:
 ref=(r.get('subject') or r.get('patient') or {}).get('reference')
 if ref:coverage[ref][r['resourceType']]+=1
 for p in r.get('participant',[]) if r['resourceType']=='Appointment' else []:
  ref=p.get('actor',{}).get('reference','')
  if ref.startswith('Patient/'):coverage[ref]['Appointment']+=1
csvout('patient_link_coverage.csv',['patient_reference']+clinical,[(p,*[v[t] for t in clinical]) for p,v in sorted(coverage.items())])
obs=[r for r in selected if r['resourceType']=='Observation' and r.get('subject',{}).get('reference')=='Patient/example']
csvout('example_patient_observations.csv',['id','status','code_json','effective_json','value_fields','has_components','issued'],[(r['id'],r.get('status'),json.dumps(r.get('code',{})),json.dumps({k:v for k,v in r.items() if k.startswith('effective')}),'|'.join(k for k in r if k.startswith('value')),bool(r.get('component')),r.get('issued','')) for r in obs])
summary={'all_records':len(rows),'resource_types':len(counts),'duplicate_type_id_keys':sum(v>1 for v in idx.values()),'selected_records':len(selected),'selected_types':len(clinical),'reference_occurrences':dict(collections.Counter(x[-1] for x in links)),'example_observations':len(obs),'example_observations_without_effective':sum(not any(k.startswith('effective') for k in r) for r in obs),'example_observation_years':dict(collections.Counter(str(r.get('effectiveDateTime',r.get('effectivePeriod',{}).get('start','missing')))[:4] for r in obs))}
(out/'profile_summary.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))
