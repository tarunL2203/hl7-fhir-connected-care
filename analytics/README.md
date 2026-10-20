# Analytics: export → S3 → Snowflake

The pipeline that takes FHIR resources out of the secured Firely server and into Snowflake, and the tools that prove each load matches its source. For the design (layers, idempotency, validation, security, roadmap), see [Snowflake design](../docs/snowflake-design.md); for one batch followed end to end, see the [walkthrough](../docs/walkthrough.md).

## Modules

| Module | Step | What it does |
|---|---|---|
| [`export_cohort.py`](export_cohort.py) | Export | Reads a bounded synthetic cohort through the reviewer's verified OIDC/PKCE session, follows every page, requires a second identical read, and writes NDJSON plus a SHA-256 manifest |
| [`land_s3.py`](land_s3.py) | Land | Checks the bucket's public-access block and ownership controls, uploads with AES-256 and no-overwrite conditional writes, then downloads every object and compares its SHA-256 (bucket from `S3_BUCKET`) |
| [`prepare_snowflake.py`](prepare_snowflake.py) | Load | Generates collision-safe SQL and a batch-scoped IAM read policy for one batch; generated SQL is never counted as a result |
| [`reconcile_csv.py`](reconcile_csv.py) | Prove | Compares the RAW rows downloaded from Snowflake with the exported batch: every ID, full payload, source file, row number and hash |
| [`compare_fc30_outcomes.py`](compare_fc30_outcomes.py) | Prove | Compares the 30-patient batch's Snowflake outcomes with the generator's expected outcomes |
| [`test_export.py`](test_export.py), [`test_reconcile.py`](test_reconcile.py) | Tests | Offline guardrail and negative tests for the export and the reconciler |

The portal's own export route, used for the 7 October batches, is [`worklist/portal_batch_export.py`](../worklist/portal_batch_export.py).

## Folders

| Folder | Contents |
|---|---|
| [`batches/`](batches/) | Every batch that was loaded into Snowflake, with its manifest. The [portal-refresh batch](batches/hl7-portal-refresh-20261007T183326824850Z/) also holds its numbered SQL scripts and `reconcile_bridge.py`, the reconciler for the HL7-derived batches |
| [`snowflake/`](snowflake/) | The Snowflake SQL: typed layer, reports, the 30-patient and bridge loads, and the Cortex Analyst demo questions |
| [`sql/`](sql/synthetic-20261004T225801Z-5dd08717/) | SQL and IAM policy generated for the first batch: access, external-stage load, reconciliation, repeat load and the internal-stage route used while S3 was blocked |
| [`dashboard/`](dashboard/) | The Streamlit-in-Snowflake dashboard, which runs on the warehouse with no external credentials |

## How a batch moves

1. **Export** two matching authenticated reads into an immutable batch with a manifest.
2. **Land** it in a private S3 prefix, or upload it to a Snowflake internal stage.
3. **Load** named files only with `COPY INTO`, keeping each payload as `VARIANT` with its file and row (`ON_ERROR = ABORT_STATEMENT`, `FORCE = FALSE`). Manifests are never loaded.
4. **Prove** it: download the RAW rows, reconcile them against the batch, then run the identical `COPY` again and confirm every file is `LOAD_SKIPPED`.

Snowflake reads S3 through a storage integration that trusts one Snowflake principal with an external ID. Its IAM role can only list and read batch prefixes: it cannot write, delete or read the document fixtures. The committed policy covers the first batch's prefix; the Phase 1 prefix was read through the same integration on 8 October, and that change is not recorded here. The integration was blocked from 4 to 7 October by an AWS-managed policy and fixed on 8 October; the [project history](../docs/project-history.md#8-s3--snowflake-fixed-and-phase-1-examples-8-oct) has the details.

## Checks

Everything here runs offline, with no cloud account:

```sh
cd analytics && python -B -m unittest test_export test_reconcile   # guardrail and negative tests
make reconcile PYTHON=python                                        # from the repository root: all four loads + the 30-patient outcomes
```

The commands for each individual load are in [results](../results/README.md#reproduce-the-reconciliation). Running the export and landing steps for real needs the full stack, an AWS profile and a Snowflake account.

---

<sub>[← README](../README.md) · [Project tour](../docs/tour.md)</sub>
