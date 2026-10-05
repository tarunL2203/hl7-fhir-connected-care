> Current milestone: internal-stage alternative PASSED October 5. See ../SNOWFLAKE-INTERNAL-RAW-MILESTONE-2026-10-05.md. Warehouse FIRELY_DEMO_WH; stage FHIR_INTERNAL_STAGE; table FHIR_RESOURCE_INTERNAL in CHATGPT_LAB.FIRELY_RAW_5DD08717. Original S3 flow below remains blocked.

# Synthetic Firely → private S3 → Snowflake RAW

Only the two synthetic patients established by the reviewer milestone are in scope.
No source record, worklist row or existing document is changed. No document body is exported.

## Execution order

1. Run `document-tools-venv/bin/python -B worklist/demo_check.py preflight` and `smoke`.
2. Save a checkpoint. Stop only the normal foreground viewer before using the export runner on the same port.
3. Run `document-tools-venv/bin/python -B analytics/export_cohort.py`. Complete normal reviewer login at https://localhost:8082/auth/login. The existing AuthService verifies OIDC/PKCE. The runner uses that verified session in memory, performs bounded authenticated FHIR reads, follows pagination and compares a second read. It leaves the normal viewer running after export; Ctrl+C stops it.
4. Run `document-tools-venv/bin/python -B analytics/land_s3.py analytics/batches/<batch_id>`. It checks privacy, uses encrypted conditional uploads (no overwrite), and downloads every object to compare SHA-256. The existing AWS profile is `firely-learning`; renewal is `aws login --profile firely-learning`.
5. Inventory the existing Snowflake account, privileges, database and warehouse. Prepare SQL using `analytics/prepare_snowflake.py <batch_dir> --database <existing_database> --warehouse <existing_warehouse> --role-arn <dedicated_role_arn>`.
6. In `sql/<batch_id>/01-access.sql`, verify name availability and create the integration **disabled**. DESCRIBE returns Snowflake's exact IAM identity/external ID. Create the dedicated AWS role with that principal and condition only, attach `iam-read-policy.json`, and read back the settings. Do not use a temporary broad trust. Enable the integration after any required browser confirmation.
7. Run the creation statements in `02-load.sql`, then LIST the stage and save its result/query ID. Run COPY and immediately save `SELECT LAST_QUERY_ID() AS COPY_QUERY_ID, * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));` as CSV. Creation statements intentionally fail on collisions; do not rerun them or replace unrelated objects.
8. Execute `03-reconcile.sql`. Download RAW columns (`payload, resource_type, resource_id, batch_id, source_filename, file_row_number, loaded_at`) for this batch as CSV. Run `analytics/reconcile_csv.py <batch_dir> <csv> --evidence <evidence_json>` with the existing Python environment. This independently compares every payload, ID, count and file row with the local source export.
9. Execute the identical COPY from `04-repeat.sql` without FORCE. Save its result/query ID and rerun reconciliation/duplicate checks. Do not recreate or truncate the table between loads.
10. Record warehouse state/usage. Do not suspend other users' active work. Restore the ordinary viewer with `worklist/demo_check.py start` after stopping the export runner.

The storage role can read/list only the batch prefix. It cannot upload, unload, delete or read existing document fixtures. SQL explicitly loads only three named resource files; `manifest.json` is excluded. All COPY failures abort the statement.

## Evidence boundaries

- `batches/`: real authenticated exports and manifest.
- `evidence/`: live AWS checks and actual Snowflake results when available.
- `test_export.py`: offline guardrail tests only, not cloud-load proof.
- SQL generation and S3 upload alone do not complete the milestone.
- Source consistency is two matching authorized reads, not a transactionally locked source snapshot.

Reference: https://docs.snowflake.com/en/user-guide/data-load-s3-config-storage-integration and https://docs.snowflake.com/en/sql-reference/sql/copy-into-table.
