# Results

Downloaded Snowflake query results, verification runs and reconciliation inputs, grouped by the date they were produced. All rows are synthetic. Account identifiers and network addresses are replaced with placeholders.

| Folder | What it shows |
|---|---|
| [`2026-10-02-worklist-assessment/`](2026-10-02-worklist-assessment/) | Baseline reads, offline assessment cases, the missing-result scenario, document-link tests, and the exported worklist history (created → in review → resolved) |
| [`2026-10-03-reviewer-verification/`](2026-10-03-reviewer-verification/) | Live reviewer milestone (15/15) and the repeatable preflight, start, smoke and reviewer runs, with sign-in and consent screenshots |
| [`2026-10-04-connection-checks/`](2026-10-04-connection-checks/) | Preflight and smoke runs on 4–5 Oct after AWS session renewal and a Firely restart |
| [`2026-10-04-s3-landing/`](2026-10-04-s3-landing/) | Two-read export summary, S3 upload with SHA-256 download check, source preservation, offline reconciler tests |
| [`2026-10-04-snowflake-external-stage/`](2026-10-04-snowflake-external-stage/) | IAM role and trust read-back, policy simulation, Snowflake grants, and the failed external-stage `LIST` (error 3167) |
| [`2026-10-05-internal-stage/`](2026-10-05-internal-stage/) | First and repeat COPY, both RAW downloads (identical), reconciliation (7/7 rows, 0 duplicates), warehouse state |
| [`2026-10-06-raw-layer/`](2026-10-06-raw-layer/) | RAW table inventory, column definitions, payload rows, typed Patient output |
| [`2026-10-06-typed-analytics/`](2026-10-06-typed-analytics/) | Typed-layer validation, the three reports, 9 rule checks, MERGE query history |
| [`2026-10-07-30-patient-batch/`](2026-10-07-30-patient-batch/) | Stage listing, availability for every appointment, the 6 records flagged for review, the summary and the dashboard export |
| [`2026-10-07-hl7-bridge/`](2026-10-07-hl7-bridge/) | RAW downloads for both bridge batches, the SIU appointment's availability result, the repeat load and the terminal transcript |
| [`2026-10-07-local-portal/`](2026-10-07-local-portal/) | Authenticated local-portal verification: two reads agree, snapshot match after reference normalization |
| [`2026-10-07-portal-refresh/`](2026-10-07-portal-refresh/) | RAW download and the repeat COPY (all files `LOAD_SKIPPED`) for the portal-refresh batch |
| [`2026-10-08-fhir-r4-examples/`](2026-10-08-fhir-r4-examples/) | Phase 1 patient-reference resolution by resource type (609 of 641 resolved) |

## Reproduce the reconciliation

The RAW downloads above can be checked against the exported batches without any cloud account. From the repository root, with `requirements.txt` installed:

```sh
# 5 Oct internal-stage load: 7 rows
python analytics/reconcile_csv.py analytics/batches/synthetic-20261004T225801Z-5dd08717 \
  results/2026-10-05-internal-stage/internal-raw-first-20261005.csv --evidence /tmp/reconciliation.json

# 7 Oct HL7 bridge, appointment bridge and portal-refresh loads: 3, 4 and 5 rows
R=analytics/batches/hl7-portal-refresh-20261007T183326824850Z/reconcile_bridge.py
python $R analytics/batches/hl7-bridge-20261007T160123921786Z results/2026-10-07-hl7-bridge/raw-download-hl7-bridge.csv
python $R analytics/batches/hl7-appointment-bridge-20261007T162957465413Z results/2026-10-07-hl7-bridge/raw-download-appointment-bridge.csv
python $R analytics/batches/hl7-portal-refresh-20261007T183326824850Z results/2026-10-07-portal-refresh/raw-download.csv

# 30-patient batch: expected vs actual outcomes
python analytics/compare_fc30_outcomes.py
```

Each check confirms every resource ID, the full JSON payload, the source file and row number, and the SHA-256 of every exported file, and ends with `PASS`. For example:

```
MATCH: Appointment/siu-appointment-17d6d563-4f77-5aac-b49b-2367195f7423
MATCH: Observation/demo-glucose-002
MATCH: Observation/lab-760b9ffe-19ca-5dbb-b2ef-8bb12d2cf2d4
MATCH: Patient/demo-patient-002
PASS: all 4 payloads and source rows match the Firely export.
PASS: available HL7 and converted source files match manifest hashes.
```
