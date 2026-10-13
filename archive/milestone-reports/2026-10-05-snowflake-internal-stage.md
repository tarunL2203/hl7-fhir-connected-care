# Snowflake internal-stage RAW milestone — October 5, 2026

Status: PASSED for the explicitly approved LOCAL EXPORT → SNOWFLAKE INTERNAL STAGE alternative. The original AWS S3 → Snowflake integration remains BLOCKED and is not claimed complete.

## Authorization and scope

After the AWS Organizations console requested a paid-plan upgrade, the user declined upgrading and explicitly approved uploading the existing seven synthetic records to a Snowflake internal stage. The user then explicitly requested a NEW warehouse. Created FIRELY_DEMO_WH (X-Small, auto-suspend 60 seconds, auto-resume true, initially suspended). Existing CHATGPT_WH was not resized or reconfigured. No AWS settings or privileges changed. Trial status is not a proven root cause of the earlier AssumeRole denial.

## Actual source and destination

Source: analytics/batches/synthetic-20261004T225801Z-5dd08717/ from the October 4 verified reviewer-authenticated FHIR extraction. All three local SHA-256 hashes matched the manifest before upload. No new extraction or source mutation occurred.

Uploaded exactly patient.ndjson, observation.ndjson and appointment.ndjson through the authenticated Snowflake browser. Manifest and document bodies were not uploaded.

Account: <SNOWFLAKE_ACCOUNT>, user <SNOWFLAKE_USER>; setup used the existing ACCOUNTADMIN role. No grants added.
Stage: CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_INTERNAL_STAGE.
Table: CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_RESOURCE_INTERNAL.
Warehouse: FIRELY_DEMO_WH, verified in the actual final count query.
The prior FHIR_STAGE external stage, FHIR_RESOURCE table and FIRELY_S3_READ_5DD08717 integration were preserved.

## Live results

- Browser upload reported three files uploaded; actual LIST returned the exact three filenames.
- First COPY: 01c784f7-0108-b568-0010-b2a6000b53a2. Three files LOADED, 7 parsed/loaded records, zero errors.
- Counts: Patient 2, Observation 3, Appointment 2.
- Actual downloaded RAW CSV independently reconciled against the local manifest and source files: exact IDs, complete JSON payloads, filenames, file row numbers and nonempty load timestamps passed; zero duplicate resource identities.
- All five Observation/Appointment patient references resolve to the two exported patients.
- Identical COPY repeated with FORCE=FALSE and PURGE=FALSE: 01c784f8-0108-bfed-0010-b2a6000cf27a. All files LOAD_SKIPPED, zero loaded rows, message 'File was loaded before.' The result contains errors_seen=1 per skipped file; this is the returned already-loaded message, not a new failed data load.
- Second actual RAW CSV reconciled successfully. Before/after CSV rows are identical, including load timestamps; counts remain 2/3/2 and duplicates zero.
- Final warehouse SHOW confirmed SUSPENDED. An explicit suspend attempt returned Invalid state after the warehouse had auto-suspended; the subsequent SHOW established final state. Prior configuration export confirms auto_suspend=60, auto_resume=true, X-Small, zero running/queued queries at inspection.

These results are live Snowflake operations plus local reconciliation of downloaded live results, not simulated connector responses. No additional offline tests were needed because no application implementation changed. Exact credits consumed were not measured; do not claim zero cost.

## Evidence

All under analytics/evidence/:
- internal-upload-20261005.png
- internal-stage-list-20261005.png
- internal-copy-first-20261005.csv
- internal-raw-first-20261005.csv
- internal-reconciliation-first-20261005.json
- internal-copy-repeat-20261005.csv
- internal-raw-repeat-20261005.csv
- internal-reconciliation-repeat-20261005.json
- internal-link-and-repeat-check-20261005.json
- internal-final-counts-20261005.csv and .png
- internal-warehouse-20261005.csv
- internal-warehouse-final-20261005.png
- new-warehouse-created-20261005.png

Before-change checkpoint: checkpoints/before-internal-stage-20261005T043620Z/.
SQL: analytics/sql/synthetic-20261004T225801Z-5dd08717/internal-stage/.

## Repeat and demonstration

Do not rerun 00-setup.sql: all objects already exist. Open the existing Snowflake account, select an authorized existing role, and execute USE WAREHOUSE FIRELY_DEMO_WH. Queries resume the dedicated warehouse and consume credits; it auto-suspends after 60 seconds idle. 01-copy.sql repeats the same three-file COPY without FORCE. 02-reconcile.sql checks counts, IDs, duplicates and links against the internal table. Use analytics/reconcile_csv.py with actual seven-column RAW CSV exports to verify complete payloads.

Short demo: show internal stage filenames, show table counts 2/3/2, show the repeat COPY evidence with LOAD_SKIPPED, then show matching reconciliation JSON. Keep the original S3 integration labeled blocked. The viewer remains https://localhost:8082/ with the existing normal authentication; it was restored and smoke-tested earlier this session, not signed in again during this analytics load.

Startup: from project root, document-tools-venv/bin/python -B worklist/demo_check.py start after checking the existing listener. Shutdown: Ctrl+C only the owned viewer process; docker stop firely-learning-aws firely-learning-auth firely-learning-mailpit only when shutdown is requested. Never delete volumes. Snowflake warehouse auto-suspends; do not stop RDS merely because local work ends.

## Remaining work

This alternative milestone is complete. Original direct S3 integration remains unresolved. Planned next milestone: typed Patient/Observation/Appointment analytical tables and three outputs (cohort completeness, glucose timeline, appointment-linked information availability), with no clinical-clearance claims. No production deployment, broader patient cohort, streaming or paid AWS upgrade was performed.
