# Background: HL7 v2, FHIR and where this platform fits

A short guide to the standards this project uses, for readers new to healthcare data.

## HL7 v2: the messaging standard hospitals run on

Most hospital systems still exchange events as **HL7 version 2** messages. A message is a set of segments, one per line. Fields are separated by `|` and components by `^`. This project uses three message types:

| Message | Event | Key segments |
|---|---|---|
| ADT^A01 | A patient is admitted or registered | `MSH` header, `EVN` event, `PID` patient identity, `PV1` visit |
| ORU^R01 | A result is reported | `PID`, `OBR` order, `OBX` result (test code, value, unit, status) |
| SIU^S12 | A new appointment is booked | `SCH` schedule, `PID`, `RGS` resource group, `AIS` service |

For example, this `OBX` segment from [`samples/lab-002.hl7`](../samples/lab-002.hl7) reports a final glucose result of 95 mg/dL:

```
OBX|1|NM|2345-7^Glucose serum or plasma^LN||95|mg/dL^mg/dL^UCUM|||||F
```

HL7 v2 is compact and dependable, but every site configures it differently. That is why integration teams spend so much effort on mapping, and why this project's converters accept only explicitly supported shapes.

## FHIR: the modern API standard

**FHIR** (Fast Healthcare Interoperability Resources), release R4, represents health data as linked **resources** exchanged over a REST API:
- **Resources.** Patient, Observation (a lab result), Appointment and DocumentReference are the four this platform reads.
- **References** link them: an Observation's `subject` is `Patient/demo-patient-002`.
- **Search** returns a `Bundle` of results with `next` links for paging. The platform follows every page before concluding anything is missing.
- **SMART on FHIR** adds OAuth 2.0 and OpenID Connect authorization. Scopes such as `user/Observation.rs` limit an app to reading and searching one resource type.
- **NDJSON**, one resource per line, is the standard bulk-export format, and the batch format used here for Snowflake.

In the United States, the ONC Cures Act Final Rule requires certified EHRs to offer standardized FHIR R4 APIs, so FHIR is now the common interface for apps and analytics.

## Terminologies

- **LOINC** codes identify tests and observations; `2345-7` is glucose in serum or plasma.
- **UCUM** codes express units, for example `mg/dL`.
- **Observation status** distinguishes `final`, `amended` and `corrected` results from `preliminary` ones. Only the first three count toward a visit's requirement here.

## How the pieces fit in a hospital, and in this project

| Real-world role | Typical system | In this project |
|---|---|---|
| Source of clinical events | EHR (for example Epic, Oracle Health, MEDITECH) and lab systems | Synthetic HL7 v2 messages in [`samples/`](../samples/) |
| Routing and transformation | Interface engine (Mirth Connect, Rhapsody, InterSystems) | [`converters/`](../converters/): strict, validated HL7 → FHIR mapping |
| FHIR API and storage | FHIR server | Firely Server, with storage on Amazon RDS for SQL Server |
| Identity and access | Authorization server, SMART on FHIR | Firely Auth: OIDC with PKCE and scoped tokens |
| Operational review | Chart preparation, pre-visit planning | The reviewer portal, the visit rule and the worklist |
| Analytics | Data warehouse fed by bulk export | Snowflake: RAW and typed layers, reports, dashboard, Cortex Analyst |

## Things FHIR does not do on its own

FHIR standardizes structure, not truth:
- A wrong patient link or a missing unit is still wrong after conversion. This is why the platform validates on the way in and flags `needs_review` downstream.
- An empty search result can mean "not done" or "not retrievable". Treating those differently is the core of this project.
- Zero linked allergy records in a dataset is not evidence that a patient has no allergies.

## References

- HL7 FHIR R4 [overview](https://hl7.org/fhir/R4/overview.html) and [comparison with v2](https://hl7.org/fhir/R4/comparison-v2.html)
- [SMART App Launch](https://hl7.org/fhir/smart-app-launch/) and [Bulk Data Access](https://hl7.org/fhir/uv/bulkdata/)
- [LOINC](https://loinc.org) and [UCUM](https://ucum.org)
- [hl7apy](https://github.com/crs4/hl7apy), the HL7 v2 parser used by the converters
- Snowflake [semi-structured data](https://docs.snowflake.com/en/user-guide/semistructured-intro) and [Cortex Analyst](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst)
