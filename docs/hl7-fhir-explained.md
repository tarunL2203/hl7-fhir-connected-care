# Learning recap: HL7, FHIR and the three project phases

Compiled from the explanation in this conversation; illustrative architecture is not a claim that every listed tool was deployed.

## Three phases
1. Clinical standardization: source HL7 messages → Python parsing → explicit mapping and validation → linked FHIR resources stored in Firely.
2. Cloud landing: authenticated export → NDJSON files and batch metadata → Amazon S3.
3. Analytics: S3 → Snowflake raw data → typed tables and governed views → dashboards and business questions.

## Vocabulary
- HL7 is the standards organization; HL7 v2 is a healthcare messaging standard.
- ADT messages communicate patient administration events such as admission, discharge and transfer.
- ORU messages communicate observation results. SIU messages communicate scheduling events. They are message types, not Python modules or preset patient facts.
- PID is a patient-identification segment; OBX contains observation/result information.
- hl7apy is a Python library from CRS4 for parsing, creating and validating HL7 v2 messages. It does not automatically perform all HL7-to-FHIR mappings.
- FHIR represents linked resources such as Patient, Observation and Appointment. Firely stores and exposes FHIR resources through APIs.

## What our conversion demonstrated
The earlier discussion identified synthetic admission and lab fixtures, Python converters using hl7apy, patient-linked glucose Observations, and a subsequently added scheduling path. The small reconciled portal batch contained 1 Patient, 3 Observations and 1 Appointment. Mapping details and test claims should be checked against the original source archives and dated evidence included here.

A large already-FHIR dataset supports analytics testing but does not prove it passed through HL7 conversion. A sample-specific converter is not evidence of arbitrary hospital-feed support.

## Real hospital pattern
Hospital EHRs such as Epic, Oracle Health or MEDITECH generate clinical events. Laboratory systems such as Epic Beaker generate results. Integration engines such as Mirth Connect or InterSystems Health Connect receive, route and transform messages. Site-specific rules resolve codes, units, patient identifiers and timestamps. Invalid or ambiguous records require investigation and replay. A FHIR repository can serve authorized applications and a separate analytics export.

S3 is object storage, not an HL7 converter. Batch COPY INTO loads staged files into Snowflake. Snowpipe can automate file ingestion using S3 events and SQS. Snowpipe Streaming is a separate direct-row approach that does not require staged S3 files. Cortex Analyst uses semantic definitions to generate SQL for business questions.

## Why FHIR emerged
HL7 v2 connected hospital systems effectively, but local variations made interfaces expensive to map and maintain. FHIR, introduced by Grahame Grieve in 2011, built on earlier HL7 experience to make standardized healthcare data more accessible through modern web approaches. Early momentum included SMART on FHIR and Argonaut participants such as Epic, Cerner and Boston Children's informatics team. HL7 v2 and FHIR coexist.

FHIR does not correct inaccurate source data automatically. Zero linked allergy records describes data coverage, not proof that the person has no allergies. Information completeness is not clinical clearance.

## Primary references used in the conversation
- https://www.crs4.it/en/technology-catalogue/hl7apy/
- https://github.com/crs4/hl7apy
- https://hl7.org/fhir/overview.html
- https://hl7.org/fhir/comparison-v2.html
- https://info.hl7.org/fhir-10th-birthday
- https://open.epic.com/Ancillary/Results
- https://docs.snowflake.com/en/user-guide/data-load-snowpipe-auto-s3
- https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst
