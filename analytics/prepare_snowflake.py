"""Prepare non-secret, collision-safe SQL and a batch-scoped read policy.

This generates files only. Executed SQL results are required for milestone success.
"""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def identifier(value):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("unsupported_identifier")
    return value.upper()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("batch")
    p.add_argument("--database", required=True)
    p.add_argument("--warehouse", required=True)
    p.add_argument("--role-arn", required=True)
    args = p.parse_args()
    directory = Path(args.batch).resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    batch = manifest["batch_id"]
    if not re.fullmatch(r"synthetic-[0-9TZ]+-[a-f0-9]{8}", batch):
        raise ValueError("invalid_batch")
    if not re.fullmatch(r"arn:aws:iam::[0-9]{12}:role/[A-Za-z0-9_+=,.@/-]+", args.role_arn):
        raise ValueError("invalid_role_arn")
    db, warehouse = identifier(args.database), identifier(args.warehouse)
    suffix = batch.split("-")[-1].upper()
    schema, integration = "FIRELY_RAW_" + suffix, "FIRELY_S3_READ_" + suffix
    stage, table = f"{db}.{schema}.FHIR_STAGE", f"{db}.{schema}.FHIR_RESOURCE"
    prefix = "analytics-demo/" + batch + "/"
    bucket = "<S3_BUCKET>"
    output = ROOT / "analytics/sql" / batch
    output.mkdir(parents=True, exist_ok=True)
    policy = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["s3:GetBucketLocation"], "Resource": f"arn:aws:s3:::{bucket}"},
        {"Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": f"arn:aws:s3:::{bucket}",
         "Condition": {"StringLike": {"s3:prefix": [prefix, prefix + "*"]}}},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:GetObjectVersion"],
         "Resource": f"arn:aws:s3:::{bucket}/{prefix}*"}]}
    (output / "iam-read-policy.json").write_text(json.dumps(policy, indent=2) + "\n")
    (output / "01-access.sql").write_text(f"""-- READ-ONLY inventory first. Confirm role privileges, credits and an existing warehouse.
SELECT CURRENT_ACCOUNT(), CURRENT_ORGANIZATION_NAME(), CURRENT_USER(), CURRENT_ROLE();
SHOW WAREHOUSES;
SHOW DATABASES;
SET inventory_role = CURRENT_ROLE();
SHOW GRANTS TO ROLE IDENTIFIER($inventory_role);
-- Name collision checks: stop if either name already belongs to unrelated work.
SHOW SCHEMAS LIKE '{schema}' IN DATABASE {db};
SHOW INTEGRATIONS LIKE '{integration}';
-- Create disabled first to obtain Snowflake's exact identity before IAM trust.
CREATE STORAGE INTEGRATION {integration}
 TYPE = EXTERNAL_STAGE STORAGE_PROVIDER = 'S3' ENABLED = FALSE
 STORAGE_AWS_ROLE_ARN = '{args.role_arn}'
 STORAGE_ALLOWED_LOCATIONS = ('s3://{bucket}/{prefix}');
DESCRIBE INTEGRATION {integration};
-- Create the dedicated IAM role with only the returned STORAGE_AWS_IAM_USER_ARN
-- and STORAGE_AWS_EXTERNAL_ID, attach iam-read-policy.json, then verify the role.
-- After required browser confirmation, activate before proceeding to 02-load.sql:
-- ALTER STORAGE INTEGRATION {integration} SET ENABLED = TRUE;
""")
    copy = f"""COPY INTO {table}
 (payload, resource_type, resource_id, batch_id, source_filename, file_row_number, loaded_at)
 FROM (SELECT t.$1, t.$1:resourceType::VARCHAR, t.$1:id::VARCHAR,
              '{batch}', METADATA$FILENAME, METADATA$FILE_ROW_NUMBER,
              METADATA$START_SCAN_TIME FROM @{stage} t)
 FILES = ('patient.ndjson', 'observation.ndjson', 'appointment.ndjson')
 ON_ERROR = ABORT_STATEMENT FORCE = FALSE PURGE = FALSE;
"""
    (output / "02-load.sql").write_text(f"""-- Use only the verified existing warehouse; never creates or resizes it.
USE WAREHOUSE {warehouse};
ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 120;
ALTER SESSION SET QUERY_TAG = 'firely-synthetic-raw-{suffix}';
CREATE SCHEMA {db}.{schema} COMMENT = 'Synthetic two-patient learning demo only';
CREATE FILE FORMAT {db}.{schema}.FHIR_JSON TYPE = JSON COMPRESSION = NONE
 STRIP_OUTER_ARRAY = FALSE ALLOW_DUPLICATE = FALSE;
CREATE STAGE {stage} URL = 's3://{bucket}/{prefix}'
 STORAGE_INTEGRATION = {integration} FILE_FORMAT = {db}.{schema}.FHIR_JSON;
CREATE TABLE {table} (
 payload VARIANT NOT NULL, resource_type VARCHAR NOT NULL, resource_id VARCHAR NOT NULL,
 batch_id VARCHAR NOT NULL, source_filename VARCHAR NOT NULL,
 file_row_number NUMBER NOT NULL, loaded_at TIMESTAMP_LTZ NOT NULL
);
LIST @{stage};
-- Save LIST rows and query ID; actual S3 files must be present.
{copy}
-- Capture the COPY query ID and result immediately.
SELECT LAST_QUERY_ID() AS copy_query_id;
""")
    expected = json.dumps(manifest["ids"], separators=(",", ":")).replace("'", "''")
    verification = f"""-- Counts and IDs: save actual results and query IDs.
SELECT resource_type, COUNT(*) AS resource_count, ARRAY_AGG(resource_id) WITHIN GROUP (ORDER BY resource_id) AS ids
 FROM {table} WHERE batch_id = '{batch}' GROUP BY resource_type ORDER BY resource_type;
-- Must return zero rows: missing, extra or duplicate resource IDs.
WITH expected AS (
 SELECT f.key::VARCHAR AS resource_type, i.value::VARCHAR AS resource_id
 FROM TABLE(FLATTEN(INPUT => PARSE_JSON('{expected}'))) f,
 LATERAL FLATTEN(INPUT => f.value) i
), actual AS (
 SELECT resource_type, resource_id, COUNT(*) AS n FROM {table}
 WHERE batch_id = '{batch}' GROUP BY resource_type, resource_id
)
SELECT COALESCE(e.resource_type,a.resource_type) AS resource_type,
 COALESCE(e.resource_id,a.resource_id) AS resource_id, a.n
 FROM expected e FULL OUTER JOIN actual a USING(resource_type, resource_id)
 WHERE e.resource_id IS NULL OR a.resource_id IS NULL OR a.n <> 1;
-- Must return zero: duplicate batch/type/id grain.
SELECT batch_id, resource_type, resource_id, COUNT(*) FROM {table}
 WHERE batch_id = '{batch}' GROUP BY batch_id, resource_type, resource_id HAVING COUNT(*) > 1;
-- Raw links for reconciliation; non-patient actors are explicit manifest exceptions.
SELECT resource_id, payload:subject:reference::VARCHAR AS patient_reference
 FROM {table} WHERE batch_id = '{batch}' AND resource_type = 'Observation';
SELECT resource_id, p.value:actor:reference::VARCHAR AS patient_reference
 FROM {table}, LATERAL FLATTEN(INPUT => payload:participant) p
 WHERE batch_id = '{batch}' AND resource_type = 'Appointment';
"""
    (output / "03-reconcile.sql").write_text(verification)
    (output / "04-repeat.sql").write_text("-- Repeat identical COPY without FORCE; save result and query ID.\n" + copy +
        "SELECT LAST_QUERY_ID() AS repeat_copy_query_id;\n" + verification +
        "-- Suspend only if this session resumed the warehouse and it has no other users/work.\n" +
        f"-- ALTER WAREHOUSE {warehouse} SUSPEND;\n")
    (output / "objects.json").write_text(json.dumps({"batch_id": batch, "database": db, "warehouse": warehouse,
        "schema": schema, "integration": integration, "stage": stage, "table": table,
        "bucket": bucket, "prefix": prefix, "role_arn": args.role_arn, "executed": False}, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
