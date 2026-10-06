SELECT CURRENT_ACCOUNT(), CURRENT_USER(), CURRENT_ROLE();

SHOW WAREHOUSES LIKE 'FIRELY_DEMO_WH';

USE WAREHOUSE FIRELY_DEMO_WH;

SELECT resource_type, COUNT(*) AS records,
       COUNT(DISTINCT resource_id) AS distinct_ids
FROM CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_RESOURCE_INTERNAL
WHERE batch_id = 'synthetic-20261004T225801Z-5dd08717'
GROUP BY resource_type
ORDER BY resource_type;

-- 1. Check column names and types in the existing RAW table.
-- This reads metadata; it does not change the table.
DESC TABLE CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_RESOURCE_INTERNAL;

-- 2. Inspect the seven synthetic FHIR resources.
-- We need their actual field shapes, patient references,
-- units and timestamps before building typed tables.
SELECT
    resource_type,
    resource_id,
    batch_id,
    source_filename,
    file_row_number,
    loaded_at,
    payload
FROM CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_RESOURCE_INTERNAL
WHERE batch_id = 'synthetic-20261004T225801Z-5dd08717'
ORDER BY resource_type, resource_id;

-- 3. Check source uniqueness before planning a repeatable MERGE.
-- Expected: zero rows.
-- Any returned row means we must inspect duplicates before loading.
SELECT
    batch_id,
    resource_type,
    resource_id,
    COUNT(*) AS row_count
FROM CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_RESOURCE_INTERNAL
WHERE batch_id = 'synthetic-20261004T225801Z-5dd08717'
GROUP BY batch_id, resource_type, resource_id
HAVING COUNT(*) > 1;

-- 4. Inventory existing tables to avoid name collisions.
-- This does not create or replace anything.
SHOW TABLES IN SCHEMA CHATGPT_LAB.FIRELY_RAW_5DD08717;

-- Reuse the existing warehouse and schema.
USE WAREHOUSE FIRELY_DEMO_WH;
USE DATABASE CHATGPT_LAB;
USE SCHEMA FIRELY_RAW_5DD08717;
-- Use the existing role that created the project objects.
-- This does not grant or change any permissions.
USE ROLE ACCOUNTADMIN;
-- New analytical table: one row per batch + Patient resource ID.
-- RAW remains the source, and the full original JSON is retained.
-- Plain CREATE deliberately stops if this table already exists.


-- Confirm the active role and restore the project context.
USE WAREHOUSE FIRELY_DEMO_WH;
USE DATABASE CHATGPT_LAB;
USE SCHEMA FIRELY_RAW_5DD08717;

SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_SCHEMA();


CREATE TABLE PATIENT_TYPED (
    batch_id          VARCHAR NOT NULL,
    patient_id        VARCHAR NOT NULL,
    given_name        VARCHAR,
    family_name       VARCHAR,
    identifiers       VARIANT,
    birth_date_raw    VARCHAR,
    birth_date        DATE,
    birth_date_status VARCHAR,
    source_filename   VARCHAR NOT NULL,
    file_row_number   NUMBER NOT NULL,
    loaded_at         TIMESTAMP_LTZ NOT NULL,
    source_payload    VARIANT NOT NULL

);

-- Insert-only MERGE for this saved, immutable export batch.
-- Matching batch + patient IDs are left unchanged on reruns.
-- Name fields use the first name/given entry in this bounded sample.
-- All names and identifiers remain available in source_payload.
MERGE INTO PATIENT_TYPED AS target
USING (
    SELECT
        batch_id,
        resource_id AS patient_id,
        payload:name[0].given[0]::VARCHAR AS given_name,
        payload:name[0].family::VARCHAR AS family_name,
        payload:identifier AS identifiers,
        payload:birthDate::VARCHAR AS birth_date_raw,

        -- Convert only a complete YYYY-MM-DD birth date.
        -- Missing or unsupported values remain visible through status.
        CASE
            WHEN REGEXP_LIKE(
                payload:birthDate::VARCHAR,
                '[0-9]{4}-[0-9]{2}-[0-9]{2}'
            )
            THEN TRY_TO_DATE(
                payload:birthDate::VARCHAR, 'YYYY-MM-DD'
            )
        END AS birth_date,

        CASE
            WHEN payload:birthDate::VARCHAR IS NULL
                THEN 'missing'
            WHEN REGEXP_LIKE(
                payload:birthDate::VARCHAR,
                '[0-9]{4}-[0-9]{2}-[0-9]{2}'
            )
            AND TRY_TO_DATE(
                payload:birthDate::VARCHAR, 'YYYY-MM-DD'
            ) IS NOT NULL
                THEN 'valid'
            ELSE 'invalid_or_unsupported'
        END AS birth_date_status,

        source_filename,
        file_row_number,
        loaded_at,
        payload AS source_payload
    FROM FHIR_RESOURCE_INTERNAL
    WHERE batch_id = 'synthetic-20261004T225801Z-5dd08717'
      AND resource_type = 'Patient'
) AS source
ON  target.batch_id = source.batch_id
AND target.patient_id = source.patient_id

WHEN NOT MATCHED THEN INSERT (
    batch_id, patient_id, given_name, family_name, identifiers,
    birth_date_raw, birth_date, birth_date_status,
    source_filename, file_row_number, loaded_at, source_payload
)
VALUES (
    source.batch_id, source.patient_id,
    source.given_name, source.family_name, source.identifiers,
    source.birth_date_raw, source.birth_date, source.birth_date_status,
    source.source_filename, source.file_row_number,
    source.loaded_at, source.source_payload
);



-- Confirm successful extraction and explicit missing-date handling.
SELECT
    patient_id,
    given_name,
    family_name,
    birth_date,
    birth_date_status
FROM PATIENT_TYPED
WHERE batch_id = 'synthetic-20261004T225801Z-5dd08717'
ORDER BY patient_id;

-- A repeated load must preserve exactly two unique patient rows.
SELECT
    COUNT(*) AS records,
    COUNT(DISTINCT patient_id) AS distinct_patients
FROM PATIENT_TYPED
WHERE batch_id = 'synthetic-20261004T225801Z-5dd08717';


-- Reuse existing project objects.
USE WAREHOUSE FIRELY_DEMO_WH;
USE DATABASE CHATGPT_LAB;
USE SCHEMA FIRELY_RAW_5DD08717;

-- Temporary transformation view: lasts only for this session.
-- Supports the single-code, numeric observations in this saved batch.
CREATE TEMPORARY VIEW OBS_LOAD_20261006 AS
WITH extracted AS (
    SELECT
        batch_id,
        resource_id AS observation_id,
        payload:subject.reference::VARCHAR AS patient_reference_raw,

        -- Accept only relative Patient references or this known server.
        CASE WHEN REGEXP_LIKE(
            payload:subject.reference::VARCHAR,
            '(http://localhost:8081/)?Patient/[A-Za-z0-9.-]{1,64}'
        )
        THEN SPLIT_PART(
            payload:subject.reference::VARCHAR, '/', -1
        ) END AS patient_id,

        payload:status::VARCHAR AS observation_status,
        payload:code.coding[0].system::VARCHAR AS code_system,
        payload:code.coding[0].code::VARCHAR AS observation_code,
        TRY_TO_DECIMAL(
            payload:valueQuantity.value::VARCHAR, 18, 6
        ) AS numeric_value,
        payload:valueQuantity.unit::VARCHAR AS unit,
        payload:valueQuantity.system::VARCHAR AS unit_system,
        payload:valueQuantity.code::VARCHAR AS unit_code,
        payload:effectiveDateTime::VARCHAR AS effective_time_raw,

        -- Require an explicit timezone; retain the original string too.
        CASE WHEN REGEXP_LIKE(
            payload:effectiveDateTime::VARCHAR,
            '.*(Z|[+-][0-9]{2}:[0-9]{2})'
        )
        THEN TRY_TO_TIMESTAMP_TZ(
            payload:effectiveDateTime::VARCHAR
        ) END AS effective_time,

        source_filename,
        file_row_number,
        loaded_at,
        payload AS source_payload
    FROM FHIR_RESOURCE_INTERNAL
    WHERE batch_id = 'synthetic-20261004T225801Z-5dd08717'
      AND resource_type = 'Observation'
)
SELECT
    extracted.*,
    -- Preserve questionable rows and flag them instead of dropping them.
    IFF(
        patient_id IS NOT NULL
        AND effective_time IS NOT NULL
        AND numeric_value IS NOT NULL
        AND NULLIF(TRIM(unit), '') IS NOT NULL
        AND observation_status IS NOT NULL
        AND code_system IS NOT NULL
        AND observation_code IS NOT NULL
        AND ARRAY_SIZE(source_payload:code.coding) = 1
        AND source_payload:id::VARCHAR = observation_id
        AND source_payload:resourceType::VARCHAR = 'Observation',
        'valid', 'needs_review'
    ) AS quality_status
FROM extracted;

-- Create an empty typed table using the transformation's column types.
CREATE TABLE OBSERVATION_TYPED AS
SELECT * FROM OBS_LOAD_20261006 WHERE 1 = 0;

-- Insert new batch/resource keys; leave existing snapshot rows unchanged.
MERGE INTO OBSERVATION_TYPED AS t
USING OBS_LOAD_20261006 AS s
ON t.batch_id = s.batch_id
AND t.observation_id = s.observation_id
WHEN NOT MATCHED THEN INSERT ALL BY NAME;

-- This batch has exactly one patient participant per appointment.
-- Original participant arrays remain preserved in source_payload.
CREATE TEMPORARY VIEW APPT_LOAD_20261006 AS
WITH extracted AS (
    SELECT
        batch_id,
        resource_id AS appointment_id,
        payload:participant[0].actor.reference::VARCHAR
            AS patient_reference_raw,

        CASE WHEN REGEXP_LIKE(
            payload:participant[0].actor.reference::VARCHAR,
            '(http://localhost:8081/)?Patient/[A-Za-z0-9.-]{1,64}'
        )
        THEN SPLIT_PART(
            payload:participant[0].actor.reference::VARCHAR, '/', -1
        ) END AS patient_id,

        payload:status::VARCHAR AS appointment_status,
        payload:start::VARCHAR AS start_time_raw,
        payload:end::VARCHAR AS end_time_raw,

        -- Store timezone-aware values for correct window comparisons.
        CASE WHEN REGEXP_LIKE(
            payload:start::VARCHAR,
            '.*(Z|[+-][0-9]{2}:[0-9]{2})'
        )
        THEN TRY_TO_TIMESTAMP_TZ(payload:start::VARCHAR)
        END AS start_time,

        CASE WHEN REGEXP_LIKE(
            payload:end::VARCHAR,
            '.*(Z|[+-][0-9]{2}:[0-9]{2})'
        )
        THEN TRY_TO_TIMESTAMP_TZ(payload:end::VARCHAR)
        END AS end_time,

        source_filename,
        file_row_number,
        loaded_at,
        payload AS source_payload
    FROM FHIR_RESOURCE_INTERNAL
    WHERE batch_id = 'synthetic-20261004T225801Z-5dd08717'
      AND resource_type = 'Appointment'
)
SELECT
    extracted.*,
    IFF(
        patient_id IS NOT NULL
        AND start_time IS NOT NULL
        AND end_time IS NOT NULL
        AND end_time > start_time
        AND appointment_status IS NOT NULL
        AND ARRAY_SIZE(source_payload:participant) = 1
        AND source_payload:id::VARCHAR = appointment_id
        AND source_payload:resourceType::VARCHAR = 'Appointment',
        'valid', 'needs_review'
    ) AS quality_status
FROM extracted;

CREATE TABLE APPOINTMENT_TYPED AS
SELECT * FROM APPT_LOAD_20261006 WHERE 1 = 0;

MERGE INTO APPOINTMENT_TYPED AS t
USING APPT_LOAD_20261006 AS s
ON t.batch_id = s.batch_id
AND t.appointment_id = s.appointment_id
WHEN NOT MATCHED THEN INSERT ALL BY NAME;


-- Rerun only the MERGEs, not the CREATE statements.
MERGE INTO OBSERVATION_TYPED AS t
USING OBS_LOAD_20261006 AS s
ON t.batch_id = s.batch_id
AND t.observation_id = s.observation_id
WHEN NOT MATCHED THEN INSERT ALL BY NAME;

MERGE INTO APPOINTMENT_TYPED AS t
USING APPT_LOAD_20261006 AS s
ON t.batch_id = s.batch_id
AND t.appointment_id = s.appointment_id
WHEN NOT MATCHED THEN INSERT ALL BY NAME;

-- Combine all three typed tables into one validation result.
WITH typed AS (
    SELECT
        batch_id, 'Patient' AS resource_type,
        patient_id AS resource_id, patient_id,
        IFF(birth_date_status IN ('valid', 'missing'),
            'valid', 'needs_review') AS quality_status,
        source_payload
    FROM PATIENT_TYPED

    UNION ALL

    SELECT
        batch_id, 'Observation', observation_id, patient_id,
        quality_status, source_payload
    FROM OBSERVATION_TYPED

    UNION ALL

    SELECT
        batch_id, 'Appointment', appointment_id, patient_id,
        quality_status, source_payload
    FROM APPOINTMENT_TYPED
)
SELECT
    t.resource_type,
    COUNT(*) AS typed_rows,
    COUNT(DISTINCT t.resource_id) AS distinct_ids,
    SUM(IFF(t.quality_status = 'valid', 0, 1)) AS review_rows,
    SUM(IFF(p.patient_id IS NULL, 1, 0)) AS broken_patient_links,
    SUM(IFF(
        r.resource_id IS NOT NULL
        AND t.source_payload = r.payload,
        0, 1
    )) AS payload_mismatches
FROM typed AS t
LEFT JOIN PATIENT_TYPED AS p
    ON t.batch_id = p.batch_id
   AND t.patient_id = p.patient_id
LEFT JOIN FHIR_RESOURCE_INTERNAL AS r
    ON t.batch_id = r.batch_id
   AND t.resource_type = r.resource_type
   AND t.resource_id = r.resource_id
WHERE t.batch_id = 'synthetic-20261004T225801Z-5dd08717'
GROUP BY t.resource_type
ORDER BY t.resource_type;

-- Count observations and appointments separately to avoid inflated counts.
WITH observations AS (
    SELECT batch_id, patient_id, COUNT(*) AS observation_count
    FROM OBSERVATION_TYPED
    GROUP BY batch_id, patient_id
),
appointments AS (
    SELECT batch_id, patient_id, COUNT(*) AS appointment_count
    FROM APPOINTMENT_TYPED
    GROUP BY batch_id, patient_id
)
SELECT
    p.patient_id,
    p.given_name || ' ' || p.family_name AS patient_name,
    p.birth_date_status,
    COALESCE(o.observation_count, 0) AS observation_count,
    COALESCE(a.appointment_count, 0) AS appointment_count,
    IFF(
        COALESCE(o.observation_count, 0) > 0
        AND COALESCE(a.appointment_count, 0) > 0,
        'patient_observation_appointment_present',
        'resource_type_gap'
    ) AS record_presence
FROM PATIENT_TYPED AS p
LEFT JOIN observations AS o
    ON p.batch_id = o.batch_id AND p.patient_id = o.patient_id
LEFT JOIN appointments AS a
    ON p.batch_id = a.batch_id AND p.patient_id = a.patient_id
WHERE p.batch_id = 'synthetic-20261004T225801Z-5dd08717'
ORDER BY p.patient_id;

-- Select the configured glucose code and qualifying result statuses.
-- Preserve original timestamps alongside their UTC representation.
SELECT
    p.patient_id,
    p.given_name || ' ' || p.family_name AS patient_name,
    o.observation_id,
    o.numeric_value AS glucose_value,
    o.unit,
    o.observation_status,
    o.effective_time_raw,
    TO_CHAR(
        CONVERT_TIMEZONE('UTC', o.effective_time),
        'YYYY-MM-DD HH24:MI:SS'
    ) AS measurement_time_utc
FROM OBSERVATION_TYPED AS o
JOIN PATIENT_TYPED AS p
    ON o.batch_id = p.batch_id AND o.patient_id = p.patient_id
WHERE o.batch_id = 'synthetic-20261004T225801Z-5dd08717'
  AND o.code_system = 'http://loinc.org'
  AND o.observation_code = '2345-7'
  AND o.observation_status IN ('final', 'amended', 'corrected')
  AND o.quality_status = 'valid'
ORDER BY p.patient_id, o.effective_time, o.observation_id;


-- Apply the demo requirement only to the two configured appointments.
-- This evaluates saved-batch information availability.
-- It does not determine clinical clearance or read fresh FHIR data.
WITH configured_visits AS (
    SELECT column1 AS appointment_id
    FROM VALUES ('demo-appointment-002'), ('fixture-v2-a02')
),
assessment AS (
    SELECT
        a.batch_id,
        a.appointment_id,
        a.patient_id,
        p.given_name || ' ' || p.family_name AS patient_name,
        a.appointment_status,
        a.quality_status AS appointment_quality,
        a.start_time,
        DATEADD(day, -7, a.start_time) AS window_start,
        c.appointment_id IS NOT NULL AS requirement_configured,
        p.patient_id IS NOT NULL AS patient_found,

        -- Retain visibility of questionable linked observations.
        SUM(IFF(o.quality_status = 'needs_review', 1, 0))
            AS review_observations,

        -- Include the window start; exclude the appointment instant.
        SUM(IFF(
            o.quality_status = 'valid'
            AND o.code_system = 'http://loinc.org'
            AND o.observation_code = '2345-7'
            AND o.observation_status IN ('final', 'amended', 'corrected')
            AND o.effective_time >= DATEADD(day, -7, a.start_time)
            AND o.effective_time < a.start_time,
            1, 0
        )) AS qualifying_glucose_count

    FROM APPOINTMENT_TYPED AS a
    LEFT JOIN PATIENT_TYPED AS p
        ON a.batch_id = p.batch_id AND a.patient_id = p.patient_id
    LEFT JOIN OBSERVATION_TYPED AS o
        ON a.batch_id = o.batch_id AND a.patient_id = o.patient_id
    LEFT JOIN configured_visits AS c
        ON a.appointment_id = c.appointment_id
    WHERE a.batch_id = 'synthetic-20261004T225801Z-5dd08717'
    GROUP BY
        a.batch_id, a.appointment_id, a.patient_id,
        p.given_name, p.family_name, a.appointment_status,
        a.quality_status, a.start_time, c.appointment_id, p.patient_id
)
SELECT
    appointment_id,
    patient_name,
    TO_CHAR(
        CONVERT_TIMEZONE('UTC', window_start),
        'YYYY-MM-DD HH24:MI:SS'
    ) AS window_start_utc,
    TO_CHAR(
        CONVERT_TIMEZONE('UTC', start_time),
        'YYYY-MM-DD HH24:MI:SS'
    ) AS appointment_time_utc,
    qualifying_glucose_count,
    CASE
        WHEN NOT requirement_configured
            OR appointment_status <> 'booked'
            THEN 'requirements_not_configured'
        WHEN appointment_quality <> 'valid'
            OR NOT patient_found
            OR review_observations > 0
            THEN 'unable_to_assess'
        WHEN qualifying_glucose_count > 0
            THEN 'information_complete'
        ELSE 'information_gap'
    END AS information_availability
FROM assessment
ORDER BY appointment_id;


-- Test inclusive seven-day start, exclusive appointment time,
-- accepted result statuses, timezone equivalence and missing time.
WITH cases AS (
    SELECT
        column1 AS test_name,
        column2 AS measurement_time_raw,
        column3 AS result_status,
        column4 AS expected_qualifies
    FROM VALUES
        ('Exactly at window start',
         '2026-09-29T13:00:00Z', 'final', TRUE),
        ('One second before window',
         '2026-09-29T12:59:59Z', 'final', FALSE),
        ('One second before appointment',
         '2026-10-06T12:59:59Z', 'final', TRUE),
        ('Exactly at appointment',
         '2026-10-06T13:00:00Z', 'final', FALSE),
        ('Preliminary result',
         '2026-10-01T13:00:00Z', 'preliminary', FALSE),
        ('Amended result',
         '2026-10-01T13:00:00Z', 'amended', TRUE),
        ('Corrected result',
         '2026-10-01T13:00:00Z', 'corrected', TRUE),
        ('Equivalent timezone',
         '2026-10-01T09:00:00-04:00', 'final', TRUE),
        ('Missing measurement time',
         NULL, 'final', FALSE)
),
evaluated AS (
    SELECT
        *,
        IFF(
            result_status IN ('final', 'amended', 'corrected')
            AND TRY_TO_TIMESTAMP_TZ(measurement_time_raw)
                >= DATEADD(
                    day, -7,
                    TO_TIMESTAMP_TZ('2026-10-06T13:00:00Z')
                )
            AND TRY_TO_TIMESTAMP_TZ(measurement_time_raw)
                < TO_TIMESTAMP_TZ('2026-10-06T13:00:00Z'),
            TRUE, FALSE
        ) AS actual_qualifies
    FROM cases
)
SELECT
    test_name,
    expected_qualifies,
    actual_qualifies,
    IFF(expected_qualifies = actual_qualifies, 'PASS', 'FAIL')
        AS test_result
FROM evaluated
ORDER BY test_name;

