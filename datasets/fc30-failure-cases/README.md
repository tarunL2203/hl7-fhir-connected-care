# Firely synthetic failure-case batch

Batch: `synthetic-failure-cases-20261006-v1`
Generated October 6, 2026. Entirely synthetic: no real patient inputs, names, or identifiers. This is a newly generated analytics fixture, not evidence of HL7 conversion or Firely-server processing. JSON is FHIR-shaped; two deliberately invalid Observation timestamps are included to test RAW ingestion and review handling. No full FHIR profile validation was performed. Do not send the entire dataset directly to Firely as valid clinical resources.

## What to use first
1. Extract this ZIP into a new folder.
   Expected: `canonical`, `delivery`, CSV files, manifest, and generator.
2. Review `expected-outcomes.csv` and `expected-review-issues.csv`.
   Expected: 30 patient scenarios, two invalid timestamps and four unresolved Observation references.
3. Prepare a separate Snowflake batch/table path using the existing SQL definitions before uploading.
   Expected: original two-patient demo and batch remain intact.
4. Load only the three NDJSON files in `canonical/` for the first analytics run.
   Expected: Patient 30, Observation 87, Appointment 30, total 147 unique resources.
5. Compare reports to the expected outcomes after the report and validation rules have been extended.
   Expected: 11 information_complete, 13 information_gap, 2 not_applicable, 2 requirements_not_configured, 2 unable_to_assess. Two of the information_gap cases have unresolved-reference review holds; they are provisional and must not be treated as final business conclusions.

Nothing has been loaded to AWS, Firely, or Snowflake by creating this package. Do not rerun CREATE TABLE against your existing demo tables, truncate existing data, or substitute the new batch ID in the old report and assume its rules cover these cases.

## Files
- `canonical/Patient.ndjson`, `canonical/Observation.ndjson`, `canonical/Appointment.ndjson`: one latest resource per resource ID, including deliberate quality failures.
- `delivery/`: same patients/appointments; Observations contain three exact duplicate deliveries and both versions of one corrected observation. Use this later to test RAW deduplication and version-aware projection in an isolated path. Do not load both folders together for the first run.
- `expected-outcomes.csv`: fixture oracle: patient ID, appointment ID, scenario, expected link/count/status, and release state. It is an independently specified expected-result file, not an actual Snowflake query result.
- `appointment-requirements.csv`: 28 configured appointments; two intentionally have no requirement. This replaces reliance on the old two-appointment hardcoded list. It is demo business-rule configuration, not a clinical guideline.
- `expected-review-issues.csv`: six deliberate quality issues; intended_fixture_patient_id is test-only provenance. Never use it to silently repair an Observation subject reference.
- `manifest.json`: exact counts, row counts, file sizes, and SHA-256 hashes for data files.
- `generate_dataset.py`: deterministic, dependency-free generator with local verification. Run `python3 generate_dataset.py` from this extracted folder to reproduce data and check counts/outcomes/hashes. It writes only fixture files in its own folder and makes no network calls.

## Scenario allocation
| Scenario | Patients | Expected report status |
| --- | ---: | --- |
| Qualifying glucose | 8 | information_complete |
| Missing birth date with qualifying glucose | 3 | information_complete; birth date flagged separately |
| No observations | 3 | information_gap |
| Observations older than seven days | 3 | information_gap |
| Preliminary observations only | 3 | information_gap |
| At/after appointment time | 2 | information_gap |
| Cancelled appointment | 2 | not_applicable |
| No configured requirement | 2 | requirements_not_configured |
| Invalid timestamp plus out-of-window observation | 2 | unable_to_assess |
| Unknown patient references | 2 | provisional information_gap + hold_for_reference_review |

All 30 patients have one Appointment. An appointment's expected requirement is valid mass-concentration glucose in the prior seven days. Window includes its start and excludes the appointment time. Accept final, amended, or corrected results; require LOINC 2345-7 and UCUM mg/dL. Different analytes and units are excluded rather than converted. Missing birth date does not block this specific availability rule. Cancelled visits are not applicable; unconfigured visits are not assessed. Invalid linked timestamps take precedence over a gap/complete label. Unresolved references trigger a separate batch-quality alert and a hold on affected fixture cases. A production process needs a defined reconciliation workflow before attributing an unresolved record to a patient.

## Additional experiments
- `fc30-p002`: one observation exactly at the seven-day window start (included).
- `fc30-p003`: an equivalent -04:00 timestamp must compare correctly with UTC.
- `fc30-p004`: one glucose result in mmol/L, with its appropriate distinct code; excluded from the mg/dL rule. Three other observations qualify. Do not compare its numeric value directly with mg/dL.
- `fc30-p005`: one hemoglobin observation; excluded from the glucose rule. Three other observations qualify.
- `fc30-o001-01`: version 1 final value 91, version 2 corrected value 101. Canonical data keeps version 2; delivery data retains both. Typed latest-state projection must select version 2 and retain provenance. The existing insert-only MERGE cannot implement updates if version 1 was already loaded.
- Three duplicate deliveries have the exact same payload, ID and version as earlier deliveries.

## Count and repeat contract
Canonical: 147 physical NDJSON rows = 147 unique resource IDs.
Delivery: 151 physical rows = 148 unique resource-version payloads = 147 unique resource IDs. There are three exact duplicates and one additional corrected version. Thus delivery RAW physical count depends on the chosen retention policy; 151, 148, and 147 represent different layers, not interchangeable targets.

For a repeat of the exact same batch, expect zero new logical resource-version records and unchanged latest-state resource counts. COPY load history alone is not a lasting business-key uniqueness guarantee. Implement batch + type + ID + version/payload identity where appropriate; detect conflicting payloads with the same ID/version. Numeric version ordering is valid only for this controlled fixture, not a general guarantee of FHIR version IDs.

## Verification performed
The generator independently recomputed linked counts, qualifying counts and report classifications from the canonical JSON and compared them with all 30 predefined expectations. It checked distinct IDs, exact duplicate counts, version counts, the four unresolved references, and every data-file hash. These local checks passed. Snowflake ingestion, SQL parity, repeat behavior, and complete FHIR validation have not yet been performed for this new batch.
