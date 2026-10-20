# Project history

How the Connected Care Data Platform was built, from the first HL7 converter on 30 September 2026 to the packaged demonstration and its public releases on 13 and 14 October 2026. Each phase links to the dated milestone report or evidence that records it. All times are US Eastern unless stated.

The Git history of this repository mirrors the same timeline. It was reconstructed from the project's dated local checkpoints and file timestamps, so each commit shows the files as they existed at that moment. A few documents lost their original timestamps during packaging; those are placed in the commit for the work they belong to.

## Timeline at a glance

| Date | Phase | Outcome |
|---|---|---|
| 30 Sep | HL7 → FHIR Patient | ADT^A01 admissions converted to FHIR Patient with deterministic IDs |
| 1 Oct | HL7 → FHIR Observation | ORU^R01 glucose results converted with LOINC/UCUM coding and stable lab IDs |
| 2 Oct | Cloud database, worklist, documents, login | Firely moved to Amazon RDS for SQL Server; information-availability rules, worklist and document gate built; OIDC + PKCE login added |
| 3 Oct | Reviewer milestone | 15/15 live checks, 6/6 infrastructure checks, 34/34 offline tests; repeatable verification tooling |
| 4 Oct | Export and S3 landing | Authenticated two-patient export landed in private S3; direct S3 → Snowflake blocked at `sts:AssumeRole` |
| 5 Oct | Snowflake RAW | Internal-stage load of 7 records, fully reconciled; repeat load added 0 rows |
| 6 Oct | Typed analytics | Typed tables, three reports, 9/9 rule tests; 30-patient failure-case dataset generated |
| 7 Oct | HL7 bridge and local portal | SIU^S12 → Appointment bridge; 30-patient and bridge batches loaded; local secure portal with authenticated batch export |
| 8 Oct | S3 route fixed, Phase 1 | AssumeRole denial traced to an AWS-managed policy and fixed; 933 official FHIR R4 examples loaded directly from S3 and explored with Cortex Analyst |
| 10–14 Oct | Packaging | HIPAA considerations, requirements document, presentations, this repository (v1.0.0 and v1.1.0) |

## 1. HL7 v2 → FHIR conversion (30 Sep – 1 Oct)

- **Admissions.** [`convert_admission.py`](../converters/convert_admission.py) accepts only the configured `ADT^A01^ADT_A01` message and the `DEMO` identifier authority. It searches Firely by the training MRN identifier, rejects multiple matches, reuses an existing Patient ID and otherwise derives a deterministic UUID5 ID.
- **Lab results.** [`convert_lab.py`](../converters/convert_lab.py) accepts one final numeric OBX in an `ORU^R01` message, maps it to LOINC 2345-7 (glucose) with UCUM units, rejects non-finite values and requires a timezone. Three revisions on 1 October made it read the source path from the command line, name its output after the source message, and derive a stable Observation ID from sender, facility, assigning authority, MRN, order authority, order ID and result number. Replaying the same message therefore produces the same resource ID.
- **Design decisions.** Identity is matched by identifier system and value, never by name. Supported message shapes are listed explicitly, and anything else is rejected rather than guessed.

## 2. Cloud database, worklist, documents and login (2 Oct)

- **Amazon RDS.** Before moving Firely's storage to Amazon RDS for SQL Server (us-east-2), the existing Patient, Observation and Appointment resources were snapshotted ([`datasets/migration-snapshot-2026-10-02`](../datasets/migration-snapshot-2026-10-02/)). Connections keep `Encrypt=True` and `TrustServerCertificate=False`, and the RDS CA bundle is added to the Firely image's trust store ([`infra/tls/Dockerfile`](../infra/tls/Dockerfile)). Database ingress is limited to verified single-address (/32) rules.
- **Information-availability rules.** [`worklist/evaluator_v2.py`](../worklist/evaluator_v2.py) applies policy `demo-previsit-v2`: a booked visit needs a numeric glucose result (LOINC 2345-7) with units, measured within the 7 days before the appointment. The window start is inclusive and the appointment time exclusive. Accepted statuses are final, amended and corrected. Outcomes deliberately separate `information_complete`, `information_gap` (retrieval succeeded, nothing qualifies), `unable_to_assess` (retrieval or identity incomplete) and `requirements_not_configured`. The UI label is "Information availability, not clinical clearance". There are 13/13 offline assessment cases ([results](../results/2026-10-02-worklist-assessment/)).
- **Worklist.** [`worklist_store.py`](../worklist/worklist_store.py) keeps administrative follow-up in SQLite, separate from clinical FHIR data. The deduplication key is appointment + requirement + issue type. States are open, in_review and resolved. Resolving an item requires an actor, a reason and a fresh successful reassessment, and an issue that reappears reopens the same item with its history intact.
- **Documents.** Synthetic PDF and PNG files sit in a private S3 bucket and are linked to a patient through FHIR DocumentReference. The viewer never hands out an S3 URL. Its server-side gate checks the authorized DocumentReference read, the patient association, the registry entry, the status, the expected object URL, the content type and the size, then verifies SHA-256 after download. Wrong-patient and unregistered documents are denied.
- **Reviewer login.** The OpenID Connect authorization-code flow with PKCE runs against Firely Auth ([`viewer_auth.py`](../worklist/viewer_auth.py), [`authenticated_viewer_server.py`](../worklist/authenticated_viewer_server.py), sanitized client configuration in [`infra/firely-auth`](../infra/firely-auth/)):
  - Public client with no secret.
  - `state` bound to the browser, single-use and expiring.
  - RS256 signature, issuer, audience, time, subject, nonce, client, scope and reviewer identity checked on every token.
  - Tokens held only in server memory; Secure/HttpOnly/SameSite cookies carry random session IDs.
  - 15-minute sessions and no refresh tokens.
  - Scopes `openid profile fhirUser` plus `user/{Patient,Observation,Appointment,DocumentReference}.rs`.

## 3. Reviewer milestone and repeatable verification (3 Oct)

- **Two login failures, kept separate.** Firely Auth rejected admin accounts requesting the `openid` scope. Separately, the provider was running in the ASP.NET `Development` environment, which redirected sign-in to an absent UI on port 3000. It was rerun in `Production` mode using the same volumes, and the old container was kept stopped for rollback.
- **First live run** ([report](../archive/milestone-reports/2026-10-03-reviewer-milestone.md)). Sign-in, records, documents, assessments, resolution history and logout all worked against the running services. Two negative checks, old-cookie replay and the authenticated wrong-document denial, were covered only by simulated tests at that point.
- **Repeatable tooling, and 15/15 live.** [`demo_check.py`](../worklist/demo_check.py) adds `preflight`, `start`, `smoke` and `reviewer` modes. Its real sign-in run that afternoon passed 15/15 live checks, alongside 6/6 infrastructure checks and 34/34 offline tests ([report](../archive/milestone-reports/2026-10-03-repeatable-verification.md)):
  - Anonymous requests get 401.
  - Wrong-patient and unregistered documents get 403.
  - Logout with a bad CSRF token or wrong origin gets 403 and keeps the session; a valid logout gets 200.
  - The old session cookie, replayed after logout, is rejected.
  - The worklist database was unchanged.
  - The rest are health, readiness and data checks.
- **Security incident.** A broad diagnostic search printed private RSA signing material. The key was rotated to a new 3072-bit RS256 key and the old key was removed from the published JWKS. Configuration files, keys and checkpoints from that period are excluded from this repository.

## 4. Authenticated export and S3 landing (4 Oct)

- **Recovery first.** The AWS CLI session had expired, and both Firely evaluation containers had reached their 12-hour uptime limit (HTTP 402). After a renewal and restart, 6/6 smoke checks passed ([connection check](../archive/milestone-reports/2026-10-04-connection-check.md)).
- **Export.** [`export_cohort.py`](../analytics/export_cohort.py) reuses the verified reviewer session to read exactly 2 Patient, 3 Observation and 2 Appointment resources, following pagination with `_count=1`, and requires a second identical read. The batch's [`manifest.json`](../analytics/batches/synthetic-20261004T225801Z-5dd08717/manifest.json) records counts, IDs, sizes and SHA-256 hashes.
- **Landing.** [`land_s3.py`](../analytics/land_s3.py) uploads with conditional, no-overwrite, AES-256 writes, then downloads every object and compares its SHA-256. ETags are not treated as hashes.
- **Snowflake access.** The storage integration was created disabled first, to learn Snowflake's exact IAM principal. Only then was a role created that trusts that one principal with its external ID, with read/list rights on the single batch prefix. A broader temporary trust was proposed and rejected, and never applied.
- **Result:** the Snowflake stage `LIST` failed with error 3167, `sts:AssumeRole` denied ([report](../archive/milestone-reports/2026-10-04-s3-snowflake-raw.md), [diagnostics](../results/2026-10-04-snowflake-external-stage/)).

## 5. Snowflake RAW through an internal stage (5 Oct)

- **Setup.** With the external route blocked, the three exported files were uploaded to a Snowflake internal stage and loaded into the RAW table `FHIR_RESOURCE_INTERNAL`, using a dedicated X-Small warehouse (`FIRELY_DEMO_WH`, auto-suspend 60 s).
- **First COPY:** 7 rows loaded, 0 errors. **Repeat COPY:** every file `LOAD_SKIPPED`, 0 rows added.
- **Reconciliation.** The RAW rows were downloaded twice and checked independently with [`reconcile_csv.py`](../analytics/reconcile_csv.py): IDs, complete payloads, filenames and file row numbers match, the two downloads are identical, all 5 patient links resolve, and there are 0 duplicates ([report](../archive/milestone-reports/2026-10-05-snowflake-internal-stage.md), [results](../results/2026-10-05-internal-stage/)).

## 6. Typed analytics (6 Oct)

- **Typed tables.** `PATIENT_TYPED`, `OBSERVATION_TYPED` and `APPOINTMENT_TYPED` are loaded with an insert-only `MERGE` on batch ID + resource ID. The first loads inserted 2/3/2 rows. The Observation and Appointment reruns inserted 0 (query history); the Patient rerun was checked in the session but not exported. The tables keep full source JSON, batch identity, file row numbers and timezone-aware timestamps. Questionable shapes are flagged `needs_review`, never dropped.
- **Three reports** ([`firely-demo-reports.sql`](../analytics/snowflake/firely-demo-reports.sql)): cohort resource presence, glucose timeline and appointment-linked information availability. Both demo appointments were `information_complete`.
- **Rule tests.** 9/9 time-window and status predicate tests pass ([results](../results/2026-10-06-typed-analytics/), [report](../archive/milestone-reports/2026-10-06-typed-analytics.md)).
- **Failure-case dataset.** A 30-patient synthetic batch was generated with deliberately invalid timestamps and missing data, to exercise RAW ingestion and review handling ([`datasets/fc30-failure-cases`](../datasets/fc30-failure-cases/)).

## 7. HL7 scheduling bridge and local secure portal (7 Oct)

- **30-patient batch:** loaded with 30 Patient, 87 Observation and 30 Appointment resources. Appointment information availability: 11 complete, 13 gaps, 2 not applicable, 2 not configured, 2 unable to assess. **All 30 outcomes match the generator's expected outcomes, and all 6 deliberately broken observations were flagged for review** ([results](../results/2026-10-07-30-patient-batch/), [`compare_fc30_outcomes.py`](../analytics/compare_fc30_outcomes.py)).
- **SIU^S12 → Appointment.** [`appointment_bridge.py`](../converters/appointment_bridge.py) converts a scheduling message to a FHIR Appointment, writes it to Firely and reads it back. The RAW rows downloaded from Snowflake reconcile 4/4 against the Firely export (3/3 for the earlier lab-only bridge), and the repeat load of the lab-only bridge was skipped. The downloads are included, so the reconciliation can be rerun ([results](../results/2026-10-07-hl7-bridge/), [walkthrough](../archive/demo-notes/2026-10-07-appointment-bridge.md)).
- **Local secure portal.**
  - The reviewer portal was pointed at a protected local Firely snapshot, with document downloads deferred in this mode.
  - A synthetic lab update ([`samples/lab-portal-update-004.hl7`](../samples/lab-portal-update-004.hl7)) was converted and refreshed through the portal.
  - A new authenticated export route ([`portal_batch_export.py`](../worklist/portal_batch_export.py)) only exports when two reads agree and the snapshot and converted-source fields match. Patient references must match exactly after normalizing the two local Firely base URLs.
  - The resulting 1 Patient / 3 Observation / 1 Appointment batch was loaded and reconciles 5/5; a repeat COPY skipped all files ([results](../results/2026-10-07-portal-refresh/)).
  - The one-time patch scripts that made these changes are kept in [`archive/one-time-scripts`](../archive/one-time-scripts/).
- **Dashboard.** A Streamlit-in-Snowflake app ([`firely_streamlit_app.py`](../analytics/dashboard/firely_streamlit_app.py)) charts appointment information status.

## 8. S3 → Snowflake fixed, and Phase 1 examples (8 Oct)

- **Root cause.**
  - The AWS account was created in AWS's free-plan "Projects" experience, which applies a managed, non-editable resource control policy (`DenyAnyoneOutsideMyOrgAndAWS`) that denies `sts:*` and `s3:*` to principals outside the organization.
  - Snowflake's IAM principal is outside it, so `AssumeRole` is denied whatever the role's trust policy says. The trust principal and external ID had been verified to match Snowflake exactly, and the denial persisted after the account was upgraded to a paid plan on 7 October.
  - The block was lifted at the AWS organization level on 8 October. Reference: [SCPs and RCPs for AWS projects](https://docs.aws.amazon.com/accounts/latest/reference/scps-and-rcps-for-projects.html).
- **Phase 1 examples, loaded directly from S3.** The official HL7 FHIR R4 example archive was profiled: 14,044 JSON objects across 139 resource types, with a full reference audit. A 933-record slice across 11 types (265 Patients) was landed in S3 and loaded through the storage integration's external stage. The files were read from their own prefix through the same storage integration; the change that allowed that prefix is not recorded in this repository. A fail-closed block rejects the batch unless the count, IDs and payloads all check out ([`datasets/phase1-fhir-examples`](../datasets/phase1-fhir-examples/), [metric catalogue](../datasets/phase1-fhir-examples/METRIC_CATALOGUE.md)).
- **Reference integrity.** The Snowflake link check matches the offline benchmark exactly: 609 of 641 clinical resources (95.0%) resolve to a Patient in the batch, with 15 unresolved, 10 in other reference formats and 7 with no reference ([results](../results/2026-10-08-fhir-r4-examples/patient-link-check.csv)).
- **Cortex Analyst.** Coverage views and a `PATIENT_RECORD_COVERAGE` semantic view let Cortex Analyst answer questions such as "how many linked observation and allergy records does this patient have?". A zero is reported as "no linked records in this batch", never as clinical absence ([demo SQL](../analytics/snowflake/Snowflake-Coverage-Demo.sql)).

## 9. Packaging (10–14 Oct)

- **Documents.** HIPAA considerations ([`hipaa-considerations.md`](hipaa-considerations.md)), the requirements and delivery plan ([`BRD-FRD-and-Progress.docx`](BRD-FRD-and-Progress.docx)), an HL7/FHIR primer ([`hl7-fhir-learning-notes.md`](../archive/hl7-fhir-learning-notes.md), since replaced by the [background guide](background-hl7-fhir.md)) and the presentations in [`presentations/`](presentations/).
- **Fixes from the repository review.**
  - Worklist code now finds its configuration relative to the repository instead of a fixed home-directory path.
  - The document-gate tests, written on 2 October, now run in document mode, with a new test proving that local mode defers downloads. Before this they failed against the 7 October local-mode configuration.
  - Every offline check now passes: 8 analytics tests, 26 authentication, document-gate and startup tests, and 9 workflow tests.
- **Release v1.0.0 (13 Oct).**
  - Extracted a shared FHIR client.
  - Restructured the converters into testable functions with 8 unit tests.
  - Added CI that runs Black, pyflakes, 51 tests, the load reconciliations and the reproducibility checks on every push to main and every pull request.
  - Wrote the architecture description, decision records and walkthrough.
  - Moved one-time scripts and working records to `archive/`. See the [changelog](../CHANGELOG.md).
- **Cortex sessions (13 Oct).** The Cortex Analyst questions and the Cortex Code explanation, trust checks and lineage trace were run over the coverage model.
- **Release v1.1.0 (14 Oct).** Pages on [Cortex Analyst](cortex-analyst.md) and [Cortex Code](cortex-code.md), including the session in which Cortex Code answered for the wrong patient, and a README with a clickable contents table.

## Lessons learned

- **Separate "absent" from "not retrieved".** An information gap is only reported after a complete, successful retrieval. Anything else is `unable_to_assess`.
- **Prove each claim with live evidence.** A generated SQL file or a passing unit test was never counted as a cloud result; every milestone above links to downloaded query results and reconciliation output.
- **Prefer reversible, scoped access.** Single /32 ingress, a disabled-first storage integration, a prefix-scoped read role and no long-lived keys. A broader trust policy was rejected rather than used as a shortcut.
- **Diagnose before buying a fix.** A paid-plan upgrade alone did not change the AssumeRole denial. Finding the governing organization-level policy did.
- **Keep secrets out of tool output.** The signing-key exposure on 3 October led to an immediate rotation and to this repository's redaction rules.

---

<sub>**Reading order 12 of 12** · ← [HIPAA considerations](hipaa-considerations.md) · [README](../README.md)</sub>
