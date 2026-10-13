# Current demonstration: what is verified

## Milestone reached
The user completed full-payload and source-row reconciliation for a four-resource batch on October 7, 2026. This establishes agreement between the exported local Firely resources and the loaded Snowflake rows.

| Resource | Count | Source |
|---|---:|---|
| Patient/demo-patient-002 | 1 | Selected PID fields from synthetic ADT admission |
| Observations | 2 | Synthetic final numeric ORU lab messages |
| Appointment | 1 | Newly generated synthetic SIU S12 booking |

Latest batch: `hl7-appointment-bridge-20261007T162957465413Z`
Appointment ID: `siu-appointment-17d6d563-4f77-5aac-b49b-2367195f7423`
Appointment: October 6, 2026, 13:00–13:30 UTC.
Labs: 95 and 102 mg/dL on October 1 at 13:00 and 14:00 UTC.

## What actually happened
1. The original converters generated a patient and two observations from the existing synthetic HL7 messages. The local Python environment needed hl7apy installed.
2. Local Firely returned HTTP 200 after startup. The stored patient lacked the gender supplied by the admission message. The user saved a backup and added the missing gender using a version-aware update. Other existing patient fields remained in the submitted resource.
3. Both stored labs used absolute references on http://localhost:8080. The comparison normalized only that exact local base URL and confirmed the converted fields matched. The export retained the server payloads unchanged.
4. The first patient/lab export contained three resources. Snowflake counts were 1 patient and 2 observations with matching distinct-ID counts. The attached repeat-load result says File was loaded before for both files. All three payloads and source rows passed local reconciliation.
5. The appointment script created a separate deterministic Appointment from a new synthetic SIU S12 sample. The user's live result reported HTTP 201 and matching read-back. It verified all four resources against the converted fields and checked two matching server reads before exporting.
6. The user confirmed the four-resource load counts and supplied a final terminal result showing all four loaded payloads and their file-row positions matched the export.

## A short demonstration
1. Open `bridge-verification.sql` in the existing Snowflake account. Run its context commands and Query 1.
   Expected: Appointment 1/1, Observation 2/2, Patient 1/1.
2. Run Query 2 for the configured seven-day glucose information rule.
   Expected: one booked appointment, qualifying_glucose_count 2 and information_complete.
   Evidence status: this query was supplied to the user. Its actual report output was not attached or explicitly confirmed separately at packaging time. Save the result CSV before describing it as inspected report evidence.
3. Show the final reconciliation transcript under evidence.
   Verified result: four MATCH lines and PASS. This is user-reported live terminal output, not a fresh run performed while assembling this package.
4. Run Query 4 to show the separate synthetic failure-case analytics summary.
   Verified attached summary: complete 11, gap 13, not applicable 2, requirements not configured 2, unable to assess 2.

## Evidence kept on the user's Mac
Project: `~/firely-learning`
Current export: `analytics/batches/hl7-appointment-bridge-20261007T162957465413Z/`
Local files: Patient.ndjson, Observation.ndjson, Appointment.ndjson, manifest.json.
Downloaded Snowflake comparison file: `~/Downloads/hl7-appointment-bridge-raw.csv`.
Patient backup: `checkpoints/hl7-bridge-20261007T155946059633Z/patient-before-update.json`.
The scheduling source and converted output are in samples/appointment-bridge-001.hl7 and samples/appointment-bridge-001.fhir.json.

These current live NDJSON/manifest/RAW CSV files have not been uploaded into this review package. Preserve them locally or add them when handing the package to a reviewer who needs independent replay. The generated SIU source included here is reproduced by the same delivered converter, not a downloaded copy of the user's Mac file.

## Repeatable commands
The source hash verification below is an additional packaged helper check. The user's already completed reconciliation compared export hashes, loaded payloads and file-row provenance.

From the project folder:
```
document-tools-venv/bin/python /PATH/TO/reconcile_bridge.py analytics/batches/hl7-appointment-bridge-20261007T162957465413Z ~/Downloads/hl7-appointment-bridge-raw.csv
```
Expected: four MATCH lines and PASS messages for payloads/provenance and available source-file hashes. The helper stops if a source file changed after export.

The appointment script's --self-test mode runs offline and never contacts Firely. A normal run checks the existing patient/labs, creates the new appointment only when its deterministic ID is absent, leaves a matching existing appointment unchanged and writes a new export batch. It is a single-user demo and does not establish concurrent creation guarantees.

## Separate 30-patient experiment
The fixture contains 30 patients, 87 observations and 30 appointments. It includes 3 missing birth dates, 2 invalid observation timestamps and 4 unresolved observation references. The user confirmed the counts and quality checks. The actual attached appointment summary matches 11/13/2/2/2.

These records test analytics behavior. They do not demonstrate HL7 mapping for 30 patients. The four unresolved references require review, and patient-level availability remains a preview while those links remain unresolved.

## Interpretation and next phase
This is a bounded synthetic demonstration. Admission mapping creates a Patient from selected PID fields, not an Encounter or a complete admission record. The lab converter supports one final numeric result for the configured patient. The scheduling converter supports one SIU S12 booking fixture and is not a general scheduling feed converter. No full HL7 or FHIR profile-validation milestone is established here.

The local bridge uses the Firely endpoint at localhost:8080 and is separate from the earlier authenticated reviewer application. Two matching reads provide a consistency check, not a transactionally locked snapshot. The manual internal-stage upload does not establish automated ingestion. Information availability does not represent clinical clearance.

Scaling options: automate delivery with the existing private AWS S3 route when account authorization permits, extend mapping to additional patients and scheduling events, and add monitored incremental ingestion. Keep the existing bucket private. No new bucket or billing change is needed for the completed local bridge.
