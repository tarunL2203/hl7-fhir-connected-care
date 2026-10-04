-- READ-ONLY inventory first. Confirm role privileges, credits and an existing warehouse.
SELECT CURRENT_ACCOUNT(), CURRENT_ORGANIZATION_NAME(), CURRENT_USER(), CURRENT_ROLE();
SHOW WAREHOUSES;
SHOW DATABASES;
SET inventory_role = CURRENT_ROLE();
SHOW GRANTS TO ROLE IDENTIFIER($inventory_role);
-- Name collision checks: stop if either name already belongs to unrelated work.
SHOW SCHEMAS LIKE 'FIRELY_RAW_5DD08717' IN DATABASE CHATGPT_LAB;
SHOW INTEGRATIONS LIKE 'FIRELY_S3_READ_5DD08717';
-- Create disabled first to obtain Snowflake's exact identity before IAM trust.
CREATE STORAGE INTEGRATION FIRELY_S3_READ_5DD08717
 TYPE = EXTERNAL_STAGE STORAGE_PROVIDER = 'S3' ENABLED = FALSE
 STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::<AWS_ACCOUNT_ID>:role/firely-snowflake-read-5dd08717'
 STORAGE_ALLOWED_LOCATIONS = ('s3://<S3_BUCKET>/analytics-demo/synthetic-20261004T225801Z-5dd08717/');
DESCRIBE INTEGRATION FIRELY_S3_READ_5DD08717;
-- Create the dedicated IAM role with only the returned STORAGE_AWS_IAM_USER_ARN
-- and STORAGE_AWS_EXTERNAL_ID, attach iam-read-policy.json, then verify the role.
-- After required browser confirmation, activate before proceeding to 02-load.sql:
-- ALTER STORAGE INTEGRATION FIRELY_S3_READ_5DD08717 SET ENABLED = TRUE;
