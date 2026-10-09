/* CONNECTED CARE DATA PLATFORM — READ-ONLY DEMO

Paste this instruction into Snowflake Cortex Code:

Use only the existing project views and this exact dataset and batch:
 SOURCE_DATASET = 'hl7_r4_official_examples'
 BATCH_ID = 'hl7-r4-examples-20261008-v1'
Use CHATGPT_LAB.FHIR_ANALYTICS.HL7_PATIENT_COVERAGE for patient metrics,
CHATGPT_LAB.FHIR_STANDARDIZED.HL7_PATIENT_LINK_CHECK for link outcomes,
and CHATGPT_LAB.FHIR_HL7_EXAMPLES.RESOURCE_RAW for resource inventory.
Inspect the available columns, then run only read-only SELECT queries.
Do not change tables, permissions, warehouses or semantic definitions.
Show the executed SQL, exact filters, denominator, result table and a concise
interpretation. Preserve explicitly requested patient IDs. If an ID does not
exist, say so; do not substitute another patient. Do not call missing linked
records an absent clinical condition. Distinguish source resources, resolved
records and distinct patients. Resource types and patient coverage overlap.
Run questions 1–4 first. Run 5–6 for a deeper technical demonstration.
Export result tables and capture the SQL and chart/table for each question.

Question 1: Across the 265-patient example batch, how many patients have at
least one linked record in each of the nine coverage categories? Show count,
percentage of all patients and linked-record count. Use a horizontal bar chart.

Question 2: How many patients have observations with no linked allergy record,
and how many have medication orders with no linked allergy record? Show the
cohort denominator and exact patient IDs in a separate detail table. Describe
these as information-coverage cohorts, not clinical risk or missing allergies.

Question 3: For the exact PATIENT_ID 'example', show every coverage metric.
Then contrast the exact PATIENT_ID '23'. Explain the difference without
substituting either patient or inferring clinical facts from a zero.

Question 4: How many clinical resources resolve to a Patient in this batch?
Break the remainder into missing literal references, other reference formats
and unresolved Patient/id references. Show counts by resource type and overall.
Explain that this is a bounded reference rule, not a blanket data-error label.

Question 5: Which ten patients have the broadest linked information coverage?
Rank by number of covered categories, then total linked records. Show each
metric. Explain why record volume differs from breadth of patient coverage.

Question 6: How many patients have no linked clinical records across the eight
clinical categories? Report appointment coverage separately. Do not imply the
sample archive is a representative clinical population.

LOCAL SOURCE BENCHMARKS (not live Snowflake execution results):
933 selected resources / 265 patients / 11 types.
Patients by metric: Observations 15, Diagnostic reports 15, Encounters 5,
Conditions 3, Allergy records 2, Medication orders 1, Medication statements 1,
Documents 1, Appointments 1.
Observation cohort: 15 patients; 14 have zero linked allergy records.
Medication-order cohort: 1 patient; 1 has zero linked allergy records.
Patient 'example': observations 71, allergies 4, conditions 4, appointments 3,
encounters 3, diagnostic reports 4, medication orders 0, statements 0,
documents 0. Patient '23': observations 1, all other metrics 0.
641 clinical resources: 609 resolved, 15 unresolved in batch, 10 other
reference formats, 7 with no literal reference.
20 patients have >=1 linked clinical resource; 245 have none under this rule.
These benchmarks come from examples-ndjson.zip and the supplied transformation
logic. If Snowflake differs, preserve its actual results and investigate the
batch, transformations or source differences before updating the presentation.
*/

-- 0. Confirm selected-batch inventory. Avoid combining batches.
SELECT RESOURCE_TYPE, COUNT(*) AS RESOURCE_COUNT
FROM CHATGPT_LAB.FHIR_HL7_EXAMPLES.RESOURCE_RAW
WHERE SOURCE_DATASET = 'hl7_r4_official_examples'
  AND BATCH_ID = 'hl7-r4-examples-20261008-v1'
GROUP BY RESOURCE_TYPE
ORDER BY RESOURCE_COUNT DESC, RESOURCE_TYPE;

-- 1. Coverage across nine resource categories.
WITH cohort AS (
 SELECT * FROM CHATGPT_LAB.FHIR_ANALYTICS.HL7_PATIENT_COVERAGE
 WHERE SOURCE_DATASET = 'hl7_r4_official_examples'
   AND BATCH_ID = 'hl7-r4-examples-20261008-v1'
), long_metrics AS (
 SELECT PATIENT_ID, METRIC, RECORD_COUNT
 FROM cohort
 UNPIVOT(RECORD_COUNT FOR METRIC IN (
  OBSERVATION_COUNT, ALLERGY_RECORD_COUNT, CONDITION_COUNT,
  MEDICATION_ORDER_COUNT, MEDICATION_STATEMENT_COUNT,
  ENCOUNTER_COUNT, DIAGNOSTIC_REPORT_COUNT,
  DOCUMENT_REFERENCE_COUNT, APPOINTMENT_COUNT
 ))
)
SELECT METRIC,
 COUNT(*) AS TOTAL_PATIENTS,
 SUM(IFF(RECORD_COUNT > 0, 1, 0)) AS PATIENTS_WITH_RECORDS,
 ROUND(100.0 * SUM(IFF(RECORD_COUNT > 0, 1, 0)) / NULLIF(COUNT(*), 0), 2)
   AS PCT_OF_PATIENTS,
 SUM(RECORD_COUNT) AS LINKED_RECORDS
FROM long_metrics
GROUP BY METRIC
ORDER BY PATIENTS_WITH_RECORDS DESC, METRIC;

-- 2a. Coverage cohorts: preserve denominator and avoid clinical inference.
WITH c AS (
 SELECT * FROM CHATGPT_LAB.FHIR_ANALYTICS.HL7_PATIENT_COVERAGE
 WHERE SOURCE_DATASET = 'hl7_r4_official_examples'
   AND BATCH_ID = 'hl7-r4-examples-20261008-v1'
)
SELECT 'Observations with no linked allergy record' AS COHORT,
 SUM(IFF(OBSERVATION_COUNT > 0, 1, 0)) AS COHORT_PATIENTS,
 SUM(IFF(OBSERVATION_COUNT > 0 AND ALLERGY_RECORD_COUNT = 0, 1, 0))
   AS PATIENTS_WITHOUT_LINKED_ALLERGY_RECORD
FROM c
UNION ALL
SELECT 'Medication orders with no linked allergy record',
 SUM(IFF(MEDICATION_ORDER_COUNT > 0, 1, 0)),
 SUM(IFF(MEDICATION_ORDER_COUNT > 0 AND ALLERGY_RECORD_COUNT = 0, 1, 0))
FROM c;

-- 2b. Exact patient details behind the cohorts.
SELECT PATIENT_ID, OBSERVATION_COUNT, MEDICATION_ORDER_COUNT, ALLERGY_RECORD_COUNT
FROM CHATGPT_LAB.FHIR_ANALYTICS.HL7_PATIENT_COVERAGE
WHERE SOURCE_DATASET = 'hl7_r4_official_examples'
  AND BATCH_ID = 'hl7-r4-examples-20261008-v1'
  AND ALLERGY_RECORD_COUNT = 0
  AND (OBSERVATION_COUNT > 0 OR MEDICATION_ORDER_COUNT > 0)
ORDER BY PATIENT_ID;

-- 3. Exact-ID check. No sample substitution is allowed.
SELECT PATIENT_ID, OBSERVATION_COUNT, ALLERGY_RECORD_COUNT,
 CONDITION_COUNT, MEDICATION_ORDER_COUNT, MEDICATION_STATEMENT_COUNT,
 ENCOUNTER_COUNT, DIAGNOSTIC_REPORT_COUNT, DOCUMENT_REFERENCE_COUNT,
 APPOINTMENT_COUNT
FROM CHATGPT_LAB.FHIR_ANALYTICS.HL7_PATIENT_COVERAGE
WHERE SOURCE_DATASET = 'hl7_r4_official_examples'
  AND BATCH_ID = 'hl7-r4-examples-20261008-v1'
  AND PATIENT_ID IN ('example', '23')
ORDER BY PATIENT_ID;

-- 4. Reference resolution by resource type. No unsupported formats discarded.
SELECT RESOURCE_TYPE, LINK_STATUS, COUNT(*) AS RECORD_COUNT
FROM CHATGPT_LAB.FHIR_STANDARDIZED.HL7_PATIENT_LINK_CHECK
WHERE SOURCE_DATASET = 'hl7_r4_official_examples'
  AND BATCH_ID = 'hl7-r4-examples-20261008-v1'
GROUP BY RESOURCE_TYPE, LINK_STATUS
ORDER BY RESOURCE_TYPE, LINK_STATUS;

-- 5. Breadth and volume are distinct metrics. Categories overlap across patients.
WITH c AS (
 SELECT *,
 IFF(OBSERVATION_COUNT > 0, 1, 0) + IFF(ALLERGY_RECORD_COUNT > 0, 1, 0)
 + IFF(CONDITION_COUNT > 0, 1, 0) + IFF(MEDICATION_ORDER_COUNT > 0, 1, 0)
 + IFF(MEDICATION_STATEMENT_COUNT > 0, 1, 0) + IFF(ENCOUNTER_COUNT > 0, 1, 0)
 + IFF(DIAGNOSTIC_REPORT_COUNT > 0, 1, 0) + IFF(DOCUMENT_REFERENCE_COUNT > 0, 1, 0)
 + IFF(APPOINTMENT_COUNT > 0, 1, 0) AS COVERED_CATEGORIES,
 OBSERVATION_COUNT + ALLERGY_RECORD_COUNT + CONDITION_COUNT
 + MEDICATION_ORDER_COUNT + MEDICATION_STATEMENT_COUNT + ENCOUNTER_COUNT
 + DIAGNOSTIC_REPORT_COUNT + DOCUMENT_REFERENCE_COUNT + APPOINTMENT_COUNT
 AS TOTAL_LINKED_RECORDS
 FROM CHATGPT_LAB.FHIR_ANALYTICS.HL7_PATIENT_COVERAGE
 WHERE SOURCE_DATASET = 'hl7_r4_official_examples'
   AND BATCH_ID = 'hl7-r4-examples-20261008-v1'
)
SELECT PATIENT_ID, COVERED_CATEGORIES, TOTAL_LINKED_RECORDS,
 OBSERVATION_COUNT, ALLERGY_RECORD_COUNT, CONDITION_COUNT,
 MEDICATION_ORDER_COUNT, MEDICATION_STATEMENT_COUNT, ENCOUNTER_COUNT,
 DIAGNOSTIC_REPORT_COUNT, DOCUMENT_REFERENCE_COUNT, APPOINTMENT_COUNT
FROM c
ORDER BY COVERED_CATEGORIES DESC, TOTAL_LINKED_RECORDS DESC, PATIENT_ID
LIMIT 10;

-- 6. Patient-level coverage with a stable denominator.
SELECT COUNT(*) AS TOTAL_PATIENTS,
 SUM(IFF(OBSERVATION_COUNT + ALLERGY_RECORD_COUNT + CONDITION_COUNT
  + MEDICATION_ORDER_COUNT + MEDICATION_STATEMENT_COUNT + ENCOUNTER_COUNT
  + DIAGNOSTIC_REPORT_COUNT + DOCUMENT_REFERENCE_COUNT > 0, 1, 0))
  AS PATIENTS_WITH_LINKED_CLINICAL_RECORDS,
 SUM(IFF(OBSERVATION_COUNT + ALLERGY_RECORD_COUNT + CONDITION_COUNT
  + MEDICATION_ORDER_COUNT + MEDICATION_STATEMENT_COUNT + ENCOUNTER_COUNT
  + DIAGNOSTIC_REPORT_COUNT + DOCUMENT_REFERENCE_COUNT = 0, 1, 0))
  AS PATIENTS_WITHOUT_LINKED_CLINICAL_RECORDS,
 SUM(IFF(APPOINTMENT_COUNT > 0, 1, 0)) AS PATIENTS_WITH_APPOINTMENTS
FROM CHATGPT_LAB.FHIR_ANALYTICS.HL7_PATIENT_COVERAGE
WHERE SOURCE_DATASET = 'hl7_r4_official_examples'
  AND BATCH_ID = 'hl7-r4-examples-20261008-v1';
