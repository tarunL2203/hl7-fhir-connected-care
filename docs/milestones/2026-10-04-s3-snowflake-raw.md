> UPDATE October 5: User-approved internal-stage alternative PASSED using newly requested FIRELY_DEMO_WH. See SNOWFLAKE-INTERNAL-RAW-MILESTONE-2026-10-05.md before following historical resume steps. Exact 7 records loaded and reconciled; repeat added zero rows. Original AWS S3 integration remains blocked. Do not recreate completed objects.

# AWS S3 to Snowflake RAW ingestion — October 4, 2026

Status: BLOCKED — the reviewer demonstration passed, but the RAW ingestion milestone has not passed. The scoped integration is enabled and RAW objects exist. Live stage LIST failed with Snowflake error 3167: AWS denied sts:AssumeRole. COPY has not been executed.

Working window began 2026-10-04 22:50:49 UTC (6:50 PM America/New_York). Five-hour deadline: 2026-10-05 03:50:49 UTC (11:50 PM America/New_York, October 4).

## Completed live

- Existing AWS/local preflight 6/6 and anonymous smoke 6/6 passed.
- Normal Demo Reviewer OIDC/PKCE login and consent produced a verified session. Exported 2 Patient, 3 Observation and 2 Appointment resources; exact cohort demo-patient-002 and fixture-v2-p02.
- Pagination exercised with _count=1. Independent second authorized extraction matched. Source worklist hash unchanged.
- Batch synthetic-20261004T225801Z-5dd08717 contains three NDJSON files and manifest. No PDF/image bodies or unrelated patients exported. Optional readiness snapshot omitted to prioritize core load.
- Uploaded to private existing bucket <S3_BUCKET>, prefix analytics-demo/synthetic-20261004T225801Z-5dd08717/. All four objects encrypted AES256 and download/SHA-256 verified.
- Snowflake account <SNOWFLAKE_ACCOUNT>, user <SNOWFLAKE_USER>. Existing ACCOUNTADMIN role available. Existing CHATGPT_LAB database and CHATGPT_WH X-Small warehouse; auto-suspend 60 seconds. UI displayed $395 of $400 trial credits and 96 days remaining.
- Created storage integration FIRELY_S3_READ_5DD08717 initially disabled, then enabled it after explicit user confirmation. DESCRIBE verified it is enabled and limited to this batch prefix.
- Created CHATGPT_LAB.FIRELY_RAW_5DD08717 with FHIR_JSON file format, FHIR_STAGE external stage and FHIR_RESOURCE RAW table. Actual query-history evidence confirms these creations succeeded.
- Two live stage LIST attempts failed with error 3167 (AWS sts:AssumeRole denied). No COPY was executed; table row count was not verified.
- Created IAM role arn:aws:iam::<AWS_ACCOUNT_ID>:role/firely-snowflake-read-5dd08717 trusted only by the Snowflake identity returned by DESCRIBE, with exact external-ID condition. Inline ReadOnlySyntheticBatch policy grants GetBucketLocation, prefix-restricted ListBucket, GetObject and GetObjectVersion only. Read-back verified.

## Pending

Resolve the exact AWS AssumeRole denial through read-only organization/account checks, then verify LIST, execute COPY, save query IDs/results, reconcile full payloads/counts/IDs/links, repeat without FORCE and verify no duplicates. No warehouse was created or resized. Final warehouse state/usage remains to be recorded.

Live role trust matches the integration principal and external-ID condition; no role permissions boundary was present. Policy simulation reported AllowedByOrganizations=false, but this is a diagnostic clue, not proof of the governing policy. The project session cannot list effective organization policies. Organization <AWS_ORG_ID> reports management account <AWS_MGMT_ACCOUNT_ID>; the project account is <AWS_ACCOUNT_ID>. The user reported “Service AWS Organizations unavailable” when opening the console. The next read-only step is to identify the signed-in console account and establish access to the management account or its administrator. No organization policy has been changed.

The user subsequently reported adding credits. No updated balance or usage has been independently verified; credits do not resolve the AWS authorization failure.

## Evidence and checkpoint

Before-edit checkpoint: checkpoints/before-snowflake-raw-20261004T225156Z/.

Actual source files/manifest: analytics/batches/synthetic-20261004T225801Z-5dd08717/.

Evidence: analytics/evidence/ (extract, S3 hashes, source preservation, bucket privacy, Snowflake grants, IAM role verification). SQL: analytics/sql/synthetic-20261004T225801Z-5dd08717/. Execution instructions: analytics/README.md.

Eight offline exporter/reconciliation guardrail tests passed, including rejection of missing, duplicate and altered records. These are distinct from the real source/S3 results. IAM policy simulation returned explicit denies, including for an upload that subsequently succeeded live; simulation is not treated as proof of actual Snowflake access.

## Named failures resolved or avoided

- AWS rejected a deny-only initial role trust as MalformedPolicyDocument; no role created by that attempt.
- Automatic approval review rejected a proposed temporary trust to AccountFullAccessRole. It was not applied. Safer flow used: create disabled Snowflake integration first, obtain exact Snowflake principal, then create only the authorized Snowflake trust. This succeeded.

## Session two

Typed Patient/Observation/Appointment analytical tables, followed by three SQL outputs: cohort record completeness, glucose observation timeline, and appointment-linked data availability. No clinical-clearance claim. These remain outside this RAW milestone.

## Comprehensive history

See PROJECT-HISTORY-AND-HANDOFF-2026-10-04.md for the project chronology, engineering decisions, resource IDs, reviewer test evidence, checkpoints and remaining work.
