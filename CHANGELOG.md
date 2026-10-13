# Changelog

Notable changes to the Connected Care Data Platform. The build itself, from 30 September to 11 October 2026, is described in the [project history](docs/project-history.md), and every commit from that period is dated to when the work happened.

## [1.0.0] – 2026-10-13

First public release.

### Platform
- **Converters.** HL7 v2 → FHIR R4 for ADT^A01, ORU^R01 and SIU^S12, with strict validation and deterministic, replay-safe resource IDs.
- **Rules and worklist.** A pre-visit information-availability engine with four outcomes and configurable rules. The worklist routes genuine gaps to records staff and data faults to the integration team.
- **Reviewer portal.** OpenID Connect authorization code + PKCE sign-in, scoped FHIR access, and a document gate that verifies patient, registry and SHA-256 before release.
- **Analytics.** Authenticated batch export to S3 and Snowflake; RAW and typed layers, three reports, a Streamlit dashboard, and a Cortex Analyst semantic view over 933 official FHIR R4 examples.

### Engineering
- **CI on every push** (`make check`):
  - Black and pyflakes, plus 51 tests;
  - reconciliation of four Snowflake loads against their exports, and the 30-patient outcome check;
  - reproduction of the converter outputs and of the 30-patient dataset.
- **Shared FHIR client.** `worklist/fhir_client.py`, with an allow-listed, configurable endpoint (`FHIR_SECURED_URL`).
- **Testable converters.** Restructured into functions with unit tests; the source server is configurable through `FHIR_SOURCE_URL`.
- **Repository layout.** Code paths resolve from the repository rather than a fixed home directory. Converters live in `converters/`, and one-time scripts and working records in `archive/`.

### Fixed
- **Document-gate tests** now run in document mode; local mode's deferred downloads have their own test.
- **Linter findings** across the application code: a confusing error-routing idiom, implicit subprocess checks, missing exception chaining and unused imports.

### Documentation
- **For each audience:** a business overview with requirement traceability, an end-to-end walkthrough, an architecture description, nine decision records, the HL7 → FHIR mapping spec, the Snowflake design, and a background guide to HL7 v2 and FHIR.
