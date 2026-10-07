-- Current batch: one patient, two observations, one appointment.
-- SELECT-only verification. These statements do not reload or modify data.
USE WAREHOUSE FIRELY_DEMO_WH;
USE DATABASE CHATGPT_LAB;
USE SCHEMA FIRELY_RAW_5DD08717;

-- 1. Expected: Appointment 1/1, Observation 2/2, Patient 1/1.
SELECT resource_type, COUNT(*) AS records,
       COUNT(DISTINCT resource_id) AS distinct_ids
FROM FHIR_RESOURCE_HL7_APPT_BRIDGE
WHERE batch_id = 'hl7-appointment-bridge-20261007T162957465413Z'
GROUP BY resource_type ORDER BY resource_type;

-- 2. This fixture's explicit configured rule:
-- glucose LOINC 2345-7, UCUM mg/dL, final/amended/corrected,
-- numeric result in [appointment start minus seven days, appointment start).
-- Expected: one booked appointment with 2 qualifying results,
-- information_complete. This is information availability, not clinical clearance.
WITH a AS (
 SELECT batch_id, resource_id AS appointment_id,
   CASE WHEN REGEXP_LIKE(payload:participant[0]:actor:reference::VARCHAR,
        '(http://localhost:8080/)?Patient/[A-Za-z0-9.-]{1,64}')
        THEN SPLIT_PART(payload:participant[0]:actor:reference::VARCHAR, '/', -1)
   END AS patient_id,
   payload:status::VARCHAR AS appointment_status,
   payload:serviceType[0]:coding[0]:system::VARCHAR AS service_system,
   payload:serviceType[0]:coding[0]:code::VARCHAR AS service_code,
   TRY_TO_TIMESTAMP_TZ(payload:start::VARCHAR, 'AUTO') AS start_time,
   TRY_TO_TIMESTAMP_TZ(payload:end::VARCHAR, 'AUTO') AS end_time
 FROM FHIR_RESOURCE_HL7_APPT_BRIDGE
 WHERE resource_type = 'Appointment'
   AND batch_id = 'hl7-appointment-bridge-20261007T162957465413Z'
), o AS (
 SELECT batch_id, resource_id AS observation_id, payload,
   CASE WHEN REGEXP_LIKE(payload:subject:reference::VARCHAR,
        '(http://localhost:8080/)?Patient/[A-Za-z0-9.-]{1,64}')
        THEN SPLIT_PART(payload:subject:reference::VARCHAR, '/', -1)
   END AS patient_id,
   TRY_TO_TIMESTAMP_TZ(payload:effectiveDateTime::VARCHAR, 'AUTO') AS measured_at
 FROM FHIR_RESOURCE_HL7_APPT_BRIDGE
 WHERE resource_type = 'Observation'
   AND batch_id = 'hl7-appointment-bridge-20261007T162957465413Z'
), counts AS (
 SELECT a.*, p.resource_id AS resolved_patient_id,
   COUNT_IF(o.observation_id IS NOT NULL AND o.measured_at IS NULL) AS invalid_time_count,
   COUNT_IF(o.payload:code:coding[0]:system::VARCHAR = 'http://loinc.org'
     AND o.payload:code:coding[0]:code::VARCHAR = '2345-7'
     AND o.payload:valueQuantity:system::VARCHAR = 'http://unitsofmeasure.org'
     AND o.payload:valueQuantity:code::VARCHAR = 'mg/dL'
     AND TRY_TO_DECIMAL(o.payload:valueQuantity:value::VARCHAR, 18, 6) IS NOT NULL
     AND o.payload:status::VARCHAR IN ('final', 'amended', 'corrected')
     AND o.measured_at >= DATEADD('day', -7, a.start_time)
     AND o.measured_at < a.start_time) AS qualifying_glucose_count
 FROM a
 LEFT JOIN FHIR_RESOURCE_HL7_APPT_BRIDGE p
   ON p.batch_id = a.batch_id AND p.resource_type = 'Patient'
  AND p.resource_id = a.patient_id
 LEFT JOIN o ON o.batch_id = a.batch_id AND o.patient_id = a.patient_id
 GROUP BY a.batch_id, a.appointment_id, a.patient_id, a.appointment_status,
          a.service_system, a.service_code, a.start_time, a.end_time, p.resource_id
)
SELECT patient_id, appointment_id, appointment_status, start_time,
       qualifying_glucose_count,
       CASE
         WHEN appointment_status = 'cancelled' THEN 'not_applicable'
         WHEN service_system IS NULL OR service_code IS NULL
           OR service_system <> 'https://example.org/synthetic-visit-types'
           OR service_code <> 'demo-glucose-review'
           THEN 'requirements_not_configured'
         WHEN resolved_patient_id IS NULL OR start_time IS NULL OR end_time IS NULL
           OR end_time <= start_time OR invalid_time_count > 0 THEN 'unable_to_assess'
         WHEN qualifying_glucose_count > 0 THEN 'information_complete'
         ELSE 'information_gap'
       END AS information_availability
FROM counts;

-- 3. Full payload export for independent local reconciliation: expected 4 rows.
-- Download as hl7-appointment-bridge-raw.csv into Downloads.
SELECT batch_id, resource_type, resource_id, source_filename, file_row_number,
       TO_JSON(payload) AS payload_json
FROM FHIR_RESOURCE_HL7_APPT_BRIDGE
WHERE batch_id = 'hl7-appointment-bridge-20261007T162957465413Z'
ORDER BY resource_type, resource_id;

-- 4. Separate failure-case fixture summary.
-- Expected: complete 11, gap 13, not applicable 2,
-- requirements not configured 2, unable to assess 2.
SELECT information_availability, COUNT(*) AS appointments
FROM APPOINTMENT_FC30_REPORT
GROUP BY information_availability ORDER BY information_availability;
