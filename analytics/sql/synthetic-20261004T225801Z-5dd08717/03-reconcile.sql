-- Counts and IDs: save actual results and query IDs.
SELECT resource_type, COUNT(*) AS resource_count, ARRAY_AGG(resource_id) WITHIN GROUP (ORDER BY resource_id) AS ids
 FROM CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_RESOURCE WHERE batch_id = 'synthetic-20261004T225801Z-5dd08717' GROUP BY resource_type ORDER BY resource_type;
-- Must return zero rows: missing, extra or duplicate resource IDs.
WITH expected AS (
 SELECT f.key::VARCHAR AS resource_type, i.value::VARCHAR AS resource_id
 FROM TABLE(FLATTEN(INPUT => PARSE_JSON('{"Patient":["demo-patient-002","fixture-v2-p02"],"Observation":["demo-glucose-002","fixture-v2-p02-glucose-001","lab-760b9ffe-19ca-5dbb-b2ef-8bb12d2cf2d4"],"Appointment":["demo-appointment-002","fixture-v2-a02"]}'))) f,
 LATERAL FLATTEN(INPUT => f.value) i
), actual AS (
 SELECT resource_type, resource_id, COUNT(*) AS n FROM CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_RESOURCE
 WHERE batch_id = 'synthetic-20261004T225801Z-5dd08717' GROUP BY resource_type, resource_id
)
SELECT COALESCE(e.resource_type,a.resource_type) AS resource_type,
 COALESCE(e.resource_id,a.resource_id) AS resource_id, a.n
 FROM expected e FULL OUTER JOIN actual a USING(resource_type, resource_id)
 WHERE e.resource_id IS NULL OR a.resource_id IS NULL OR a.n <> 1;
-- Must return zero: duplicate batch/type/id grain.
SELECT batch_id, resource_type, resource_id, COUNT(*) FROM CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_RESOURCE
 WHERE batch_id = 'synthetic-20261004T225801Z-5dd08717' GROUP BY batch_id, resource_type, resource_id HAVING COUNT(*) > 1;
-- Raw links for reconciliation; non-patient actors are explicit manifest exceptions.
SELECT resource_id, payload:subject:reference::VARCHAR AS patient_reference
 FROM CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_RESOURCE WHERE batch_id = 'synthetic-20261004T225801Z-5dd08717' AND resource_type = 'Observation';
SELECT resource_id, p.value:actor:reference::VARCHAR AS patient_reference
 FROM CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_RESOURCE, LATERAL FLATTEN(INPUT => payload:participant) p
 WHERE batch_id = 'synthetic-20261004T225801Z-5dd08717' AND resource_type = 'Appointment';
