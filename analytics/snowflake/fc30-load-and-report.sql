USE ROLE ACCOUNTADMIN;
USE WAREHOUSE FIRELY_DEMO_WH;
USE DATABASE CHATGPT_LAB;
USE SCHEMA FIRELY_RAW_5DD08717;

-- New internal stage for uploading the synthetic files.
CREATE STAGE IF NOT EXISTS FHIR_FC30_INTERNAL_STAGE
    FILE_FORMAT = (TYPE = JSON);

-- New empty RAW table with the confirmed column structure.
CREATE TABLE IF NOT EXISTS FHIR_RESOURCE_FC30
    LIKE FHIR_RESOURCE_INTERNAL;


    LIST @CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_FC30_INTERNAL_STAGE;


    -- Load only the three canonical files into the new RAW table.
COPY INTO CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_RESOURCE_FC30 (
    payload,
    resource_type,
    resource_id,
    batch_id,
    source_filename,
    file_row_number,
    loaded_at
)
FROM (
    SELECT
        t.$1,
        t.$1:resourceType::VARCHAR,
        t.$1:id::VARCHAR,
        'synthetic-failure-cases-20261006-v1',
        METADATA$FILENAME,
        METADATA$FILE_ROW_NUMBER,
        METADATA$START_SCAN_TIME
    FROM @CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_FC30_INTERNAL_STAGE AS t
)
FILES = ('Patient.ndjson', 'Observation.ndjson', 'Appointment.ndjson')
FILE_FORMAT = (TYPE = JSON)
ON_ERROR = 'ABORT_STATEMENT'
FORCE = FALSE;


SELECT
    resource_type,
    COUNT(*) AS records,
    COUNT(DISTINCT resource_id) AS distinct_ids
FROM CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_RESOURCE_FC30
WHERE batch_id = 'synthetic-failure-cases-20261006-v1'
GROUP BY resource_type
ORDER BY resource_type;

-- Create a separate typed table for our 30-patient batch.
CREATE TABLE IF NOT EXISTS
CHATGPT_LAB.FIRELY_RAW_5DD08717.PATIENT_FC30_TYPED AS
SELECT
    batch_id,
    resource_id AS patient_id,
    payload:name[0]:given[0]::VARCHAR AS given_name,
    payload:name[0]:family::VARCHAR AS family_name,
    payload:birthDate::VARCHAR AS birth_date_raw,
    TRY_TO_DATE(
        payload:birthDate::VARCHAR, 'YYYY-MM-DD'
    ) AS birth_date,
    CASE
        WHEN NULLIF(TRIM(payload:birthDate::VARCHAR), '') IS NULL
            THEN 'missing'
        WHEN TRY_TO_DATE(
            payload:birthDate::VARCHAR, 'YYYY-MM-DD'
        ) IS NULL
            THEN 'invalid'
        ELSE 'valid'
    END AS birth_date_status,
    source_filename,
    file_row_number,
    loaded_at,
    payload AS source_payload
FROM CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_RESOURCE_FC30
WHERE resource_type = 'Patient'
  AND batch_id = 'synthetic-failure-cases-20261006-v1';

  SELECT
    birth_date_status,
    COUNT(*) AS patient_count
FROM CHATGPT_LAB.FIRELY_RAW_5DD08717.PATIENT_FC30_TYPED
GROUP BY birth_date_status
ORDER BY birth_date_status;

USE WAREHOUSE FIRELY_DEMO_WH;
USE DATABASE CHATGPT_LAB;
USE SCHEMA FIRELY_RAW_5DD08717;

-- Turn observation JSON into queryable columns.
-- Keep the original JSON and provenance for investigation.
CREATE TABLE IF NOT EXISTS OBSERVATION_FC30_TYPED AS
SELECT
    batch_id,
    resource_id AS observation_id,
    payload:subject:reference::VARCHAR AS patient_reference_raw,
    CASE
        WHEN REGEXP_LIKE(
            payload:subject:reference::VARCHAR,
            'Patient/[A-Za-z0-9.-]{1,64}'
        )
        THEN SPLIT_PART(
            payload:subject:reference::VARCHAR, '/', 2
        )
    END AS patient_id,
    payload:status::VARCHAR AS observation_status,
    payload:code:coding[0]:system::VARCHAR AS code_system,
    payload:code:coding[0]:code::VARCHAR AS observation_code,
    TRY_TO_DECIMAL(
        payload:valueQuantity:value::VARCHAR, 18, 6
    ) AS value_numeric,
    payload:valueQuantity:system::VARCHAR AS unit_system,
    payload:valueQuantity:code::VARCHAR AS unit_code,
    payload:effectiveDateTime::VARCHAR AS effective_time_raw,
    CASE
        WHEN REGEXP_LIKE(
            payload:effectiveDateTime::VARCHAR,
            '.*(Z|[+-][0-9]{2}:[0-9]{2})'
        )
        THEN TRY_TO_TIMESTAMP_TZ(
            payload:effectiveDateTime::VARCHAR, 'AUTO'
        )
    END AS effective_time,
    source_filename,
    file_row_number,
    loaded_at,
    payload AS source_payload
FROM FHIR_RESOURCE_FC30
WHERE resource_type = 'Observation'
  AND batch_id = 'synthetic-failure-cases-20261006-v1';

-- Turn appointment JSON into queryable columns.
-- This fixture has exactly one patient participant per appointment.
CREATE TABLE IF NOT EXISTS APPOINTMENT_FC30_TYPED AS
SELECT
    batch_id,
    resource_id AS appointment_id,
    payload:participant[0]:actor:reference::VARCHAR
        AS patient_reference_raw,
    CASE
        WHEN REGEXP_LIKE(
            payload:participant[0]:actor:reference::VARCHAR,
            'Patient/[A-Za-z0-9.-]{1,64}'
        )
        THEN SPLIT_PART(
            payload:participant[0]:actor:reference::VARCHAR,
            '/', 2
        )
    END AS patient_id,
    payload:status::VARCHAR AS appointment_status,
    payload:start::VARCHAR AS start_time_raw,
    TRY_TO_TIMESTAMP_TZ(
        payload:start::VARCHAR, 'AUTO'
    ) AS start_time,
    payload:end::VARCHAR AS end_time_raw,
    TRY_TO_TIMESTAMP_TZ(
        payload:end::VARCHAR, 'AUTO'
    ) AS end_time,
    source_filename,
    file_row_number,
    loaded_at,
    payload AS source_payload
FROM FHIR_RESOURCE_FC30
WHERE resource_type = 'Appointment'
  AND batch_id = 'synthetic-failure-cases-20261006-v1';

-- Check the resulting table sizes.
SELECT 'Observation' AS resource_type, COUNT(*) AS records
FROM OBSERVATION_FC30_TYPED
UNION ALL
SELECT 'Appointment', COUNT(*)
FROM APPOINTMENT_FC30_TYPED;

-- Check timestamps and whether referenced patients exist.
SELECT
    COUNT(*) AS observations_checked,
    COUNT_IF(o.effective_time IS NULL)
        AS invalid_or_missing_timestamps,
    COUNT_IF(p.patient_id IS NULL)
        AS unresolved_patient_references
FROM OBSERVATION_FC30_TYPED o
LEFT JOIN PATIENT_FC30_TYPED p
    ON p.batch_id = o.batch_id
   AND p.patient_id = o.patient_id;

   -- Load the requirement configuration from our fixture.
-- Appointments 25 and 26 intentionally have no configured requirement.
CREATE TABLE IF NOT EXISTS APPOINTMENT_FC30_REQUIREMENTS AS
SELECT
    'synthetic-failure-cases-20261006-v1'::VARCHAR AS batch_id,
    'fc30-a' || LPAD(column1::VARCHAR, 3, '0')
        AS appointment_id,
    7 AS window_days,
    'mg/dL'::VARCHAR AS accepted_unit_code
FROM VALUES
    (1),(2),(3),(4),(5),(6),(7),(8),
    (9),(10),(11),(12),(13),(14),(15),(16),
    (17),(18),(19),(20),(21),(22),(23),(24),
    (27),(28),(29),(30);

-- Calculate availability from actual observations and configuration.
CREATE OR REPLACE VIEW APPOINTMENT_FC30_REPORT AS
WITH counts AS (
    SELECT
        a.batch_id,
        a.appointment_id,
        a.patient_id,
        a.appointment_status,
        a.start_time,
        a.end_time,
        r.appointment_id AS configured_appointment_id,

        COUNT_IF(
            o.observation_id IS NOT NULL
            AND o.effective_time IS NULL
        ) AS invalid_time_count,

        COUNT_IF(
            o.code_system = 'http://loinc.org'
            AND o.observation_code = '2345-7'
            AND o.unit_system = 'http://unitsofmeasure.org'
            AND o.unit_code = r.accepted_unit_code
            AND o.value_numeric IS NOT NULL
            AND o.observation_status IN (
                'final', 'amended', 'corrected'
            )
            AND o.effective_time >=
                DATEADD('day', -r.window_days, a.start_time)
            AND o.effective_time < a.start_time
        ) AS qualifying_glucose_count

    FROM APPOINTMENT_FC30_TYPED a
    LEFT JOIN APPOINTMENT_FC30_REQUIREMENTS r
        ON r.batch_id = a.batch_id
       AND r.appointment_id = a.appointment_id
    LEFT JOIN OBSERVATION_FC30_TYPED o
        ON o.batch_id = a.batch_id
       AND o.patient_id = a.patient_id
    GROUP BY
        a.batch_id,
        a.appointment_id,
        a.patient_id,
        a.appointment_status,
        a.start_time,
        a.end_time,
        r.appointment_id
)
SELECT
    *,
    CASE
        WHEN appointment_status = 'cancelled'
            THEN 'not_applicable'
        WHEN configured_appointment_id IS NULL
            THEN 'requirements_not_configured'
        WHEN start_time IS NULL
          OR end_time IS NULL
          OR end_time <= start_time
          OR invalid_time_count > 0
            THEN 'unable_to_assess'
        WHEN qualifying_glucose_count > 0
            THEN 'information_complete'
        ELSE 'information_gap'
    END AS information_availability
FROM counts;

-- Summarize the report.
SELECT
    information_availability,
    COUNT(*) AS appointments
FROM APPOINTMENT_FC30_REPORT
GROUP BY information_availability
ORDER BY information_availability;


SELECT
    patient_id,
    appointment_id,
    appointment_status,
    start_time,
    qualifying_glucose_count,
    information_availability
FROM APPOINTMENT_FC30_REPORT
ORDER BY patient_id;

SELECT
    o.observation_id,
    o.patient_reference_raw,
    o.effective_time_raw,
    CASE
        WHEN p.patient_id IS NULL
             AND o.effective_time IS NULL
            THEN 'unresolved_patient_and_invalid_time'
        WHEN p.patient_id IS NULL
            THEN 'unresolved_patient_reference'
        ELSE 'invalid_or_missing_timestamp'
    END AS review_reason
FROM OBSERVATION_FC30_TYPED o
LEFT JOIN PATIENT_FC30_TYPED p
    ON p.batch_id = o.batch_id
   AND p.patient_id = o.patient_id
WHERE p.patient_id IS NULL
   OR o.effective_time IS NULL
ORDER BY o.observation_id;

