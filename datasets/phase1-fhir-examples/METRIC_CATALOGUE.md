# Phase 1 metric contracts

Dataset: official HL7 R4 examples. No population representativeness or clinical-readiness claim. Batch: hl7-r4-examples-20261008-v1. Raw record grain: source dataset + batch + resource type + ID. No cross-dataset patient matching. This catalogue specifies subsequent SQL/semantic-view development; those objects were not yet deployed when it was written. By 13 October the link-check view (`HL7_PATIENT_LINK_CHECK`), the coverage view (`HL7_PATIENT_COVERAGE`) and the `PATIENT_RECORD_COVERAGE` semantic view were built; the other semantic views listed here remain planned.

| Metric | Grain and definition | Exclusions / interpretation | Planned semantic view |
|---|---|---|---|
| Resource count | Count unique raw identities within source/batch/type | Bundled resources are not recursively counted as separate raw rows | FHIR_PIPELINE_QUALITY |
| Patient record count | Count distinct Patient IDs within source/batch | Example Patient resources may include non-human and incomplete examples; not a human-population statistic | PATIENT_RECORD_COVERAGE |
| Patient coverage by category | Distinct present Patient IDs with >=1 direct, resolved subject/patient link of specified type / distinct present Patient IDs in same source/batch | Separate each category; unresolved/absolute/contained links not silently treated as resolved; annotate eligibility | PATIENT_RECORD_COVERAGE |
| Unresolved relative-reference rate | Unresolved simple Type/id reference occurrences / all evaluated simple Type/id occurrences | Full archive lookup; not limited selected load. Contained, absolute, versioned, other references separately reported as unassessed. Repeated references count as occurrences | FHIR_PIPELINE_QUALITY |
| Observation effective-time missing rate | Observations without any effective[x] field / observations | Missing field does not mean invalid FHIR; timestamp parsing and usable time are separate checks | FHIR_PIPELINE_QUALITY |
| Numeric measurement coverage | Observations with usable numeric valueQuantity or numeric component valueQuantity / eligible measurement observations | Code + code system + unit determine comparability; components are child rows | PATIENT_RECORD_COVERAGE |
| Scheduled appointment count | Appointment rows with usable start/end and patient participant | Report proposed appointments separately; deduplicate patient participants per appointment | APPOINTMENT_INFORMATION |
| Rule evaluation coverage | Eligible scheduled appointments with explicit configured rule / eligible scheduled appointments | A missing rule is not an information failure | APPOINTMENT_INFORMATION |
| Information availability rate | Rule-evaluated eligible appointments with >=1 qualifying observation / rule-evaluated eligible appointments | Same patient, approved code/system/status/unit and effective time in [start − window, start); no inferred rule from visit description | APPOINTMENT_INFORMATION |
| At-visit knowability | Result issued time <= appointment start when available | effective time alone cannot prove the result was available at the visit. Missing issued time gives unknown; source ingestion time is not historic availability | APPOINTMENT_INFORMATION |
| Medication order count | Count MedicationRequest by subject and status | Does not establish use, adherence, or current medication list | PATIENT_RECORD_COVERAGE |
| Medication statement count | Count MedicationStatement by subject/status/effective period | Separate from prescriptions; never merge different patient identities | PATIENT_RECORD_COVERAGE |
| Batch reconciliation | Expected manifest records minus landing/target records, per type | Must be zero; compare payloads for repeated immutable batch | FHIR_PIPELINE_QUALITY |

## Semantic design
Aggregate repeating resource tables independently before joining patient-level or appointment-level facts. Use separate observation-component and coding tables. Keep snapshot metrics restricted to one batch or an explicitly defined latest-resource selection. Never sum snapshots as a population.

## Cortex Analyst evaluation questions
1. How many records were loaded by resource type?
2. How many distinct Patient resource IDs exist in this batch?
3. Which records have unresolved simple references in the full-archive audit?
4. How many observations for Patient/example lack an effective field?
5. Which appointments have no fixed start time?
6. How many observations reference Patient/example?
7. Which patient IDs have recorded allergy examples?
8. Which patient IDs have medication statements?
9. Did a repeat load insert additional records?
10. Which units and coding systems occur in observations?
11. Which observations contain component measurements?
12. Are there configured information rules for every eligible appointment?
13. Which observations were measured after an appointment? (Does not imply an error.)
14. Was this result available at visit time? (Unknown unless appropriate availability evidence exists.)
15. How many repeat tests did this platform prevent? (Unsupported by the dataset.)

## Cortex Code task prompt for the next implementation
Inspect CHATGPT_LAB.FHIR_HL7_EXAMPLES.RESOURCE_RAW using read-only queries first. Implement standardized views for patients, appointment participants, observations, observation components, conditions, allergies, and medication orders/statements in a separate schema. Preserve original codes, units and payloads. Report absolute/contained/unresolved references explicitly. Generate reviewed SQL and expected-result checks before executing writes. Use the metric definitions in this file; do not infer clinical requirements or combine different patient IDs. Start with ordinary views; select dynamic tables only after the transformations and refresh need are established.
