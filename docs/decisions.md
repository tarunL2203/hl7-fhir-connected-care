# Architecture decisions

The decisions that shape the platform, each with the context that forced it and the consequences accepted. Dates refer to the [project history](project-history.md).

### ADR-001 · Match patients by identifier and derive resource IDs from source keys (30 Sep – 1 Oct)

- **Context.** Names are not unique and change. Interfaces replay messages, so an ID generated on every run would duplicate records.
- **Decision.** Patients are matched only by identifier system + value. A duplicate identifier stops processing for manual review. Lab and appointment IDs are UUID5 hashes of the source keys (sender, facility, authority, MRN, order and result identifiers).
- **Consequences.** Replays are idempotent and every resource traces back to its message. Messages from unconfigured authorities are rejected rather than guessed. A production deployment would put a master patient index behind this rule.

### ADR-002 · Four outcomes, and a partial retrieval never proves absence (2 Oct)

- **Context.** "No result found" is ambiguous: the test may not have been done, or retrieval may have failed. The two need different owners.
- **Decision.** Each visit receives `information_complete`, `information_gap`, `unable_to_assess` or `requirements_not_configured`. A gap is reported only after every result page was retrieved successfully. Any failure becomes `unable_to_assess` and is routed to the integration team, not to records staff.
- **Consequences.** Records staff only chase genuine gaps. The label "Information availability, not clinical clearance" keeps the output out of clinical decision-making.

### ADR-003 · Rules are configuration, not code (2 Oct)

- **Context.** Visit requirements differ by visit type and change over time.
- **Decision.** Requirements live in [`policy.json`](../worklist/spec/v2/policy.json): code, window, inclusive and exclusive bounds, accepted statuses, unit requirement, routing and due times. In Snowflake they live in a requirements table.
- **Consequences.** A new visit type is a new profile. The same rule runs in Python and SQL, pinned by nine edge-case predicate tests.

### ADR-004 · A public OIDC client with PKCE, and tokens kept server-side (2–3 Oct)

- **Context.** The portal is a browser-facing app that cannot safely hold a client secret.
- **Decision.** Use the authorization-code flow with PKCE against Firely Auth, with no client secret. Tokens are verified (RS256, issuer, audience, expiry, nonce, scopes, reviewer identity) and held only in server memory. The browser holds a random session ID. Sessions last 15 minutes and no refresh tokens are requested.
- **Consequences.** A stolen cookie expires quickly and never exposes a token. Reviewers sign in again after 15 minutes.

### ADR-005 · Serve documents through a verifying gate, not signed links (2 Oct)

- **Context.** A link in a FHIR DocumentReference does not prove the requester may see the document.
- **Decision.** The portal retrieves documents server-side, only after an authorized DocumentReference read for the same patient and registry, status, type and size checks. It verifies SHA-256 before returning the bytes.
- **Consequences.** There are no shareable URLs and every access is checked. The portal carries the download traffic.

### ADR-006 · Immutable batches with manifests, confirmed by two reads (4 Oct)

- **Context.** A FHIR server offers no transactional snapshot for export.
- **Decision.** Each export reads the cohort twice through the reviewer's session and proceeds only if both reads match. Each batch is an immutable set of NDJSON files with a SHA-256 manifest.
- **Consequences.** Every load can be reconciled row by row against its source, and these reconciliations run in CI. This gives consistency for small cohorts, not a substitute for change data capture.

### ADR-007 · RAW `VARIANT` first, then typed tables with insert-only `MERGE` (5–6 Oct)

- **Context.** FHIR JSON is nested and varies by resource. Analytics needs typed columns without losing the source.
- **Decision.** Land each resource as a `VARIANT` with batch, file and row provenance. Build typed tables with an insert-only `MERGE` on batch + resource ID after a uniqueness check. Questionable rows are flagged `needs_review`, never dropped.
- **Consequences.** Loads are idempotent: repeat `COPY` files are skipped and `MERGE` reruns insert nothing. The typed layer can always be validated back to RAW. A changed resource under the same key is investigated rather than silently updated.

### ADR-008 · Keep the S3 integration's trust tight while it was blocked (4–8 Oct)

- **Context.** Snowflake's `AssumeRole` was denied even though the trust policy and external ID matched exactly.
- **Decision.** Do not widen trust, remove the external ID or make data public. Load through a Snowflake internal stage meanwhile, and find the governing policy: an AWS-managed resource control policy on free-plan accounts. It was fixed at the organization level on 8 Oct.
- **Consequences.** No control was weakened at any point. Batches from 5–7 Oct use the internal stage; Phase 1 loads directly from S3.

### ADR-009 · Synthetic data only (all phases)

- **Context.** The platform handles the kind of data HIPAA protects.
- **Decision.** Use only fictional patients and the official HL7 FHIR R4 examples. Account identifiers are replaced with placeholders throughout the repository and its history.
- **Consequences.** The repository can be public. Production use would need a HIPAA risk assessment, business associate agreements, audit logging and PHI governance in Snowflake ([HIPAA considerations](hipaa-considerations.md)).

---

<sub>**Reading order 6 of 12** · ← [Architecture](architecture.md) · [HL7 → FHIR mapping](hl7-to-fhir-mapping.md) → · [README](../README.md)</sub>
