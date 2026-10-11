# HIPAA considerations and security evidence

Prepared 10 October 2026. This is a retrospective mapping of documented project safeguards, not a HIPAA certification or a new security audit. The project describes its demonstration inputs as synthetic fixtures and official FHIR examples; this review does not certify every collected file as free of PHI or secrets. No evidence establishes a production deployment authorized to process real PHI.

## Historically documented safeguards

| Consideration | Documented project behavior | Evidence and limits |
|---|---|---|
| Authentication | OIDC authorization-code flow with PKCE; signature, issuer, audience, time, nonce, subject, scopes and reviewer checks | CURRENT-PROGRESS-2026-10-05.md, section 4. Demo identity verification does not establish enterprise identity governance. |
| Session protection | Server-memory tokens; random session IDs; Secure/HttpOnly/SameSite cookies; absolute expiry at the earlier of access-token expiry or 15 minutes; no refresh tokens | Source inspection corroborates the expiry calculation. This is not a verified inactivity timeout. Logout removes the viewer session; the provider sign-in session can remain active, and global token revocation is not established. |
| Access control | Scoped Patient, Observation, Appointment and DocumentReference reads; anonymous requests denied | REPEATABLE-VERIFICATION-MILESTONE-2026-10-03.md: anonymous 401 and authenticated tests. Resource-type read/search scopes are not proof of patient-compartment isolation, tenant separation, or general care-team authorization. The inspected code requires the named read scopes to be present; it does not reject every possible extra scope. |
| Document confidentiality | Server-side gate checks patient association, registry, status, expected URL, type and size; wrong-patient/unregistered requests denied | Progress section 3 and October 3 milestone: HTTP 403 denial checks and authorized PDF/PNG retrieval. The later local-secure-copy configuration explicitly defers documents; do not carry this test result forward to that mode without rechecking. |
| Transport protection | Database Encrypt=True and TrustServerCertificate=False; trusted Auth discovery; HTTPS reviewer tests | Progress section 4; milestone preflight. The documented viewer/Auth endpoints use HTTPS, but local FHIR uses HTTP on localhost:8081; the FHIR reader attaches its bearer token to these requests. Do not describe this topology as encrypted end to end. |
| Cloud storage protection | Private S3 landing, AES256-encrypted writes, public-access block and bucket-owner enforcement checked | Progress section 7. This documents the historical batch; it does not independently verify every current object or account setting. |
| Network restrictions | RDS access restricted through device-specific /32 security-group rules; TLS not weakened to fix connectivity | Progress section 4. The report records two allowed /32 rules, including a preserved earlier rule. This is not proof that only the current device can connect. RDS is publicly reachable; private-subnet isolation is not demonstrated. |
| Integrity and traceability | Downloaded SHA-256 checks; source filenames, batch IDs and load context; reconciliation and rerun controls | Progress sections 3 and 7; SQL scripts, manifests within archives, and result CSVs. Integrity checks do not by themselves provide a complete access audit. |
| Sensitive evidence handling | The October 3 verification report states that its saved evidence omitted cookies, tokens and document bodies | October 3 milestone. This is a statement about that evidence set, not a complete secret scan of the collection. |
| Key exposure response | A diagnostic output exposed signing material; notes report key rotation, old-key removal from JWKS and refreshed caches | Progress section 4. Old private checkpoints must not be restored or published. This is documented remediation, not evidence of a complete incident-response program. |

The saved milestone reports 15/15 live reviewer checks, 6/6 infrastructure checks and 34/34 offline checks (21 auth, 4 startup guardrails and 9 worklist). The 15-check reviewer run already includes six anonymous/service checks; these counts must not be summed as unique security controls. These are historical reported results; no live security rerun was performed during consolidation.

## What is not established by these files

Before any real-PHI deployment, the responsible organization would need to establish and document the applicable requirements and evidence, including:

- Covered-entity/business-associate roles and applicable BAAs with cloud and downstream service providers.
- A documented security risk analysis and treatment plan covering Firely, RDS, S3, Snowflake, the viewer, exports and AI processing.
- Production access provisioning, review and revocation; appropriate minimum-necessary access and disclosure controls.
- A verified encryption/key-management inventory, including database, warehouse, backups, endpoints and exports.
- Durable access/audit logging, monitoring, retention and review responsibilities. Worklist history and load provenance are not substitutes for a full access audit.
- Tested backup restoration, disaster recovery, contingency procedures, retention and secure disposal.
- Incident response and breach assessment/notification procedures; workforce training and physical safeguards.
- Approved handling of PHI in Cortex prompts, query results, screenshots and support workflows. Do not assume a service or AI feature is covered merely because the platform is available.
- Data provenance and a formal de-identification method if real data is to be de-identified. Removing names alone is not proof of HIPAA de-identification.

These are evidence gaps, not claims that each control is absent.

## Technical qualifications added after evidence review

This follow-up inspected the uploaded `firely-local-integration-source.zip` files `viewer_auth.py`, `authenticated_viewer_server.py` and `auth_fhir.py`, and the local-copy setup configuration. It corroborates selected implementation details, not the currently deployed runtime. Historical reports remain the source for cloud configuration and live test outcomes.

- **Deployment boundary:** Firely services ran in local Docker with an AWS RDS backend in the documented architecture. Calling this an AWS-hosted Firely application would overstate the hosting evidence. The later local-secure-copy mode is a separate configuration; do not merge modes into one tested topology.
- **Encryption boundary:** AES256 S3 writes describe server-side object encryption, not client-side encryption, customer-managed KMS keys or encryption of every database/backup. No KMS rotation claim is supported.
- **Integrity boundary:** Comparing SHA-256 values detects a mismatch against a trusted expected value. It is not a digital signature, immutable audit trail, malware scan or proof against a party able to replace both object and manifest.
- **Authorization boundary:** The historical export is bounded to an explicit cohort, but that alone does not constrain every permission of the underlying account. Historical ACCOUNTADMIN use does not demonstrate least-privilege Snowflake operation. Snowflake row-access policies, masking policies, MFA enforcement and service-account separation were not established by this review.
- **Authentication detail:** The inspected code checks ID-token nonce and authorized party, access-token scopes/client identity, and matching subjects; the same claim checks are not applied identically to both token types. It checks `at_hash` when supplied. PKCE is not MFA. The 15-minute cap is an absolute session bound, not evidence of inactivity locking or immediate revocation following an account change.
- **Later workflow evidence:** October 3 auth/document results predate the October 7 local-copy/export changes. The source retains the authenticated handler, but an earlier passing report is not a fresh regression run for later routes.
- **Export consistency:** Two matching authorized reads provide reconciliation evidence, not a transactionally consistent snapshot during concurrent updates. Local downloaded exports and temporary files also need their own access, retention and disposal controls for real PHI.
- **FHIR scope:** Supported ADT/ORU/SIU fixtures, resource links and analytical rules do not establish universal HL7 conversion, full FHIR profile conformance, terminology validation, patient identity resolution across organizations, or clinical correctness.
- **Operational gaps:** No evidence reviewed establishes complete vulnerability/patch management, endpoint/disk protection, dependency scanning, penetration testing, or a tested production recovery process. These are unverified areas, not automatically absent controls.
- **HIPAA scope:** Login consent is OAuth permission consent, not necessarily a HIPAA authorization. Minimum-necessary rules depend on use/disclosure and applicable exceptions; provider treatment disclosures/requests are an example exception. The Privacy Rule also involves permitted uses/disclosures and individual rights, which this technical demonstration does not establish.

## Presentation-ready wording

**Documented demo safeguards:** Historical evidence records OIDC/PKCE reviewer authentication, resource-type read scopes, bounded viewer sessions, document-access checks in the earlier reviewer mode, and private encrypted S3 landing. Selected tests covered anonymous denial, document denial and viewer-session replay after logout. Local FHIR traffic used HTTP; patient-level authorization, production audit operations and HIPAA compliance have not been established.

## Authoritative references

The HIPAA Security Rule addresses the confidentiality, integrity and availability of ePHI through administrative, physical and technical safeguards. The relevant organization's obligations extend beyond application features. HHS also explains that using cloud services for ePHI requires appropriate agreements and safeguards. These summaries do not assert that a proposed rule is already effective.

- HHS, Summary of the HIPAA Security Rule: https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/index.html
- HHS, Guidance on HIPAA and Cloud Computing: https://www.hhs.gov/hipaa/for-professionals/special-topics/health-information-technology/cloud-computing/index.html
- HHS, The Security Rule: https://www.hhs.gov/hipaa/for-professionals/security/index.html

Reviewed 10 October 2026. Project evidence is in 06_Project_Notes_and_Runbooks; dates and batch scopes should be retained when quoting it.

Additional HHS references reviewed for the qualifications:
- Minimum necessary: https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/minimum-necessary-requirement/index.html
- Risk analysis: https://www.hhs.gov/hipaa/for-professionals/security/guidance/final-guidance-risk-analysis/index.html
