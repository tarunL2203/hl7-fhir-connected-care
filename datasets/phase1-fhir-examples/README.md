# HL7 FHIR exploration: Phase 1 starter package

Status: profiled and packaged locally; NOT uploaded to AWS or executed in Snowflake.

## What to do now
1. Unzip this package.
2. In S3 bucket `<S3_BUCKET>`, create folder `analytics-demo/hl7-r4-examples-20261008-v1/`.
3. Upload the 11 individual NDJSON files INSIDE `s3_upload/` directly to that folder. Do not upload the ZIP, reports, or an extra nested s3_upload folder.
4. Run `01_setup.sql` in your existing Snowflake worksheet. LIST must show 11 files.
5. Run `02_load_verify.sql` in order in that same session; stop on errors. Expected landing and final raw total: 933. First merge inserts 933; repeated identical batch inserts zero.
6. Share resource counts before moving to standardized views and semantic views.

This creates a separate schema `CHATGPT_LAB.FHIR_HL7_EXAMPLES`. It does not edit the existing October 7 demo tables or dashboard. Uses the existing warehouse and storage integration. SQL is prepared, not account-executed; account privileges and actual stage access remain to be verified.

## Expected selected records
| File | Records |
|---|---:|
| Patient.ndjson | 265 |
| Appointment.ndjson | 3 |
| Observation.ndjson | 531 |
| Condition.ndjson | 12 |
| Medication.ndjson | 24 |
| MedicationRequest.ndjson | 41 |
| MedicationStatement.ndjson | 7 |
| AllergyIntolerance.ndjson | 6 |
| Encounter.ndjson | 11 |
| DiagnosticReport.ndjson | 32 |
| DocumentReference.ndjson | 1 |

## Findings
- Full source: 14,044 parsed JSON objects, 139 resource types, no duplicate top-level resource-type/ID keys.
- Selected load: 933 records in 11 types. Original JSON content preserved; whitespace normalized. Medication is included for medicationReference lookups.
- Full archive reference audit: 3,343 resolved and 135 unresolved simple Type/id occurrences. Another 267 contained and 66 other/absolute/versioned occurrences are explicitly unassessed. These are occurrences, not distinct missing target IDs.
- Full-archive resolution is NOT selected-load resolution: some referenced supporting resources lie outside these 11 types. This is an exploration slice, not a reference-complete import package.
- All 3 Appointment resources point to Patient/example. Two are booked in December 2013; one is proposed without start/end.
- 71 observations link directly to Patient/example. 33 lack any effective[x] field; dated examples span 1999–2018. No dated example observation falls in 2013. Do not manufacture a coherent visit history by adjusting dates.
- JSON parsing success is not FHIR profile validation. A missing optional timestamp is an analytics limitation, not automatically a FHIR validity error.

## Files
- profile_hl7.py: repeatable profiler (Python standard library), accepts input ZIP and output directory.
- resource_inventory.csv: full archive inventory.
- reference_audit.csv: full archive reference occurrences and limited resolution classes.
- patient_link_coverage.csv: direct subject/patient and appointment-participant link counts; not a population completeness score.
- example_patient_observations.csv: fields to inspect before selecting measures.
- manifest.json: source archive hash and expected counts/hashes of selected files.
- METRIC_CATALOGUE.md: definitions, exclusions, semantic-view scope and initial AI evaluation questions.

## Source and intended use
Source: https://hl7.org/fhir/R4/examples-ndjson.zip (user-provided archive). Official illustrative FHIR R4 examples, not real patient data or a representative cohort. Retain HL7 attribution and consult https://hl7.org/fhir/R4/license.html before redistribution. No clinical recommendations or measured workflow savings are established.
