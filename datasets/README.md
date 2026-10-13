# Datasets

| Folder | Contents | Source |
|---|---|---|
| [`fc30-failure-cases/`](fc30-failure-cases/) | 30 synthetic patients, 87 observations and 30 appointments covering ten scenarios (complete, missing data, out-of-window, preliminary, cancelled, unconfigured, invalid timestamp, unknown patient), with expected outcomes and the generator script | Generated 6 Oct 2026 by `generate_dataset.py` |
| [`phase1-fhir-examples/`](phase1-fhir-examples/) | 933-record, 11-type slice of the official FHIR R4 examples, with the profiler, inventory, reference audit, metric catalogue and the Snowflake SQL that loaded it directly from S3 | [HL7 FHIR R4 examples](https://hl7.org/fhir/R4/downloads.html), [FHIR licence](https://hl7.org/fhir/R4/license.html) |
| [`migration-snapshot-2026-10-02/`](migration-snapshot-2026-10-02/) | Patient, Observation and Appointment resources captured before Firely moved to Amazon RDS | Project Firely server, 2 Oct 2026 |

The exported batches that were loaded into Snowflake live with their manifests in [`analytics/batches/`](../analytics/batches/). `make reproduce` regenerates the 30-patient dataset and fails if any committed file changes.
