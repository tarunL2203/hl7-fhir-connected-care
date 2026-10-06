-- Synthetic two-patient demonstration using a saved export batch.
-- Information availability, not clinical clearance.
USE ROLE ACCOUNTADMIN;
USE WAREHOUSE FIRELY_DEMO_WH;
USE DATABASE CHATGPT_LAB;
USE SCHEMA FIRELY_RAW_5DD08717;


-- ============================================================
-- CONTEXT — run this block first
-- Synthetic saved-batch demonstration.
-- Information availability, not clinical clearance.
-- ============================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE FIRELY_DEMO_WH;
USE DATABASE CHATGPT_LAB;
USE SCHEMA FIRELY_RAW_5DD08717;


-- ============================================================
-- REPORT 1: Cohort resource completeness
-- EXPECTED: 2 rows.
-- Ravi: 2 observations, 1 appointment, birth date valid.
-- Person02: 1 observation, 1 appointment, birth date missing.
-- Both: patient_observation_appointment_present.
-- SAVE RESULT AS: 01-cohort-completeness.csv
-- ============================================================

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
    ON p.batch_id = o.batch_id
   AND p.patient_id = o.patient_id
LEFT JOIN appointments AS a
    ON p.batch_id = a.batch_id
   AND p.patient_id = a.patient_id
WHERE p.batch_id = 'synthetic-20261004T225801Z-5dd08717'
ORDER BY p.patient_id;


-- ============================================================
-- REPORT 2: Glucose timeline
-- EXPECTED: 3 rows, all final, units mg/dL.
-- Ravi:     95 at 2026-10-01 13:00:00 UTC.
-- Ravi:    102 at 2026-10-01 14:00:00 UTC.
-- Person02: 95 at 2026-10-05 12:00:00 UTC.
-- SAVE RESULT AS: 02-glucose-timeline.csv
-- ============================================================

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
    ON o.batch_id = p.batch_id
   AND o.patient_id = p.patient_id
WHERE o.batch_id = 'synthetic-20261004T225801Z-5dd08717'
  AND o.code_system = 'http://loinc.org'
  AND o.observation_code = '2345-7'
  AND o.observation_status IN ('final', 'amended', 'corrected')
  AND o.quality_status = 'valid'
ORDER BY p.patient_id, o.effective_time, o.observation_id;


-- ============================================================
-- REPORT 3: Appointment information availability
-- EXPECTED: 2 rows.
-- demo-appointment-002: 2 qualifying glucose results.
-- fixture-v2-a02:       1 qualifying glucose result.
-- Both: information_complete.
-- Window: includes seven-day start; excludes appointment time.
-- SAVE RESULT AS: 03-appointment-availability.csv
-- ============================================================

WITH configured_visits AS (
    SELECT column1 AS appointment_id
    FROM VALUES
        ('demo-appointment-002'),
        ('fixture-v2-a02')
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

        SUM(IFF(o.quality_status = 'needs_review', 1, 0))
            AS review_observations,

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
        ON a.batch_id = p.batch_id
       AND a.patient_id = p.patient_id
    LEFT JOIN OBSERVATION_TYPED AS o
        ON a.batch_id = o.batch_id
       AND a.patient_id = o.patient_id
    LEFT JOIN configured_visits AS c
        ON a.appointment_id = c.appointment_id
    WHERE a.batch_id = 'synthetic-20261004T225801Z-5dd08717'
    GROUP BY
        a.batch_id,
        a.appointment_id,
        a.patient_id,
        p.given_name,
        p.family_name,
        a.appointment_status,
        a.quality_status,
        a.start_time,
        c.appointment_id,
        p.patient_id
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