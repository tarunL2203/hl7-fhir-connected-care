# Authenticated reviewer milestone — October 3, 2026

Status: CORE AUTHENTICATED REVIEWER DEMONSTRATION PASSED AND SAVED. Reviewer login, records, documents, assessments, resolution history and logout were exercised against running services. After explicit user confirmation, consent was renewed with Prompt me again next time and the signed-in viewer was restored. Exact old-cookie replay and authenticated wrong-document rejection remain simulated-test coverage, not live claims.

## Changes and evidence

### Database access restored

- RDS firely-learning-db is available and publicly accessible in us-east-2. Its endpoint matches the existing Firely connection: <RDS_ENDPOINT>:1433.
- Security group <SECURITY_GROUP_ID> retains its original TCP 1433 rule for <PUBLIC_IP>/32.
- Added rule <SG_RULE_ID> initially allowed <PUBLIC_IP>/32. On resumption, an automatic-family IP check reported <PUBLIC_IP>; IPv4-forced checks showed different egress. The same added rule was updated, not duplicated, and now allows only <PUBLIC_IP>/32. That address was verified immediately before applying it and repeated consistently in three subsequent IPv4-forced checks.
- Native IPv4 TCP connection to SQL Server succeeded after the final update. Earlier timeouts and the prior recommendation to switch networks are superseded by this result.
- Existing firely-learning-aws started successfully. GET http://localhost:8081/$readiness returned HTTP 200, including after the later key-cache refresh.
- Encrypt=True, TrustServerCertificate=False, SQL database auto-update=false, SMART authentication and HTTPS provider validation were preserved. No database records were changed.

Use curl -4 --silent --show-error https://checkip.amazonaws.com when rechecking this network's IPv4 egress. IPv6/default-family requests can report a different translated IPv4. Reverify the address before any future authorized /32 update; do not broaden CIDRs.

### Provider login UI corrected

Historical provider logs show access_denied with the specific reason: Admin users are not allowed to request the 'openid' scope. The viewer's generic login_not_authorized message is not evidence of a reviewer identity mismatch.

A fresh browser attempt reached a different blocker: Auth redirected login to http://localhost:3000, where no UI was running. The existing container used ASPNETCORE_ENVIRONMENT=Development. Its application includes the localhost:3000 development URL.

Ran the same installed image in Production environment with the same ports, mounts, network, and firely-auth alias. Retained the original stopped container as firely-learning-auth-before-ui-20261003T191031Z. The replacement keeps the original service name firely-learning-auth. Existing Auth data/runtime volumes were reused; no image was rebuilt and no database was replaced.

Live authorization now redirects to https://localhost:5001/login. The Firely Auth login form was visibly rendered in the browser. Discovery returned HTTP 200 using the local CA with certificate validation enabled. Production here names the ASP.NET runtime environment; this remains a synthetic learning project, not a claim of production healthcare readiness.

### Signing-key incident and remediation

A broad diagnostic search inadvertently printed private RSA signing material into tool output. It was not copied into this report. Rotated the RSA key to a fresh 3072-bit RS256 key in the local settings and active runtime settings. Discovery was checked: the new key is published and the old key is absent. Restarted the existing FHIR container and the identified viewer process to clear cached signing keys. Token verification, PKCE, audience, issuer, nonce, scope and reviewer identity checks remain enabled.

Old private signing material remains in restricted pre-change checkpoints. Do not publish these checkpoints or restore the exposed signing key. The stored account passwords and database credentials were not changed.

## Account and client inspection

Read-only account inspection found Demo Reviewer with UserType Practitioner, confirmed email, no LockoutEnd, and fhirUser mapping Practitioner/demo-reviewer. Runtime client firely-learning-viewer is enabled, requires PKCE and consent, requires no client secret, and registers https://localhost:8082/auth/callback. Stored identity scopes include openid, profile and fhirUser. The viewer additionally requests user/Patient.rs, user/Observation.rs, user/Appointment.rs and user/DocumentReference.rs. Reviewer consent and successful viewer token validation were subsequently verified through the live signed-in demonstration; token contents were not displayed or saved.

The callback maps any provider error parameter to login_not_authorized after state validation and before token exchange. It is inappropriate to remove openid or weaken identity validation to allow the prior admin login.

## Current service checks

| Check | Result |
|---|---|
| Existing FHIR /$readiness | HTTP 200 |
| FHIR Patient read without token | HTTP 401 |
| Auth discovery with validated TLS | HTTP 200 |
| Provider authorization redirect | HTTPS localhost:5001/login |
| Browser login form | Visible |
| Viewer /health with validated TLS | HTTP 200 |
| Viewer patient summary without session | HTTP 401 |
| Viewer document without session, earlier live check | HTTP 401 |
| Mailpit, last container inspection | Running and healthy |

Viewer: https://localhost:8082
Login entry: https://localhost:8082/auth/login

## Tests: simulated versus live

Existing test_viewer_auth: 21/21 passed in the preceding milestone attempt. These use real RSA signatures but simulated provider/FHIR/S3 responses and temporary local HTTP route tests. They cover permitted login, wrong user/scopes, invalid signatures/issuer/audience/time/nonce, browser-bound PKCE state, anonymous denial, document authorization/integrity, request isolation, and logout/replay denial. The initial sandbox run failed to bind test sockets; the authorized rerun passed. No authentication source code has changed since that run.

Existing test_worklist: 9/9 passed using a temporary synthetic worklist store. No live Firely records changed. Includes roles, review, reassessment, resolution, reopening, replay handling, and resolution history.

Read-only inspection of the real local worklist found one resolved item with created, in_review and resolved history entries. This is stored-state verification, not a new assessment against live FHIR.

The live checks are listed separately above. Unit tests do not establish a completed reviewer demonstration.

## Checkpoints

- checkpoints/reviewer-milestone-20261003T185755Z/: worklist and local auth-config copies; private Auth account database inspection copy. The database copy is not an application-consistent restore backup.
- checkpoints/auth-ui-repair-20261003T191031Z/: local settings/key checkpoint, original runtime settings, private Docker inspection, previous milestone report, and sanitized change summary.
- Retained stopped container: firely-learning-auth-before-ui-20261003T191031Z.

Checkpoint files were restricted to owner access. They contain sensitive configuration and must not be published. The old and new Auth containers share existing named volumes; never run them concurrently. Do not restore the exposed signing key during any rollback.

## Live demonstration results

The user completed reviewer login and consent. Browser inspection confirmed Signed in: Demo Reviewer and fresh retrieval of both patients through the running viewer and AWS-backed FHIR service.

- Ravi (demo-patient-002): final glucose results 95 and 102 mg/dL; booked demo-appointment-002; Configured information complete; No linked documents returned; no saved work items.
- Training Person02 (fixture-v2-p02): final glucose 95 mg/dL; booked fixture-v2-a02; Configured information complete; saved missing-record work item is resolved.
- Expanded resolution history visibly preserves created → in review → resolved, including the original information_gap evidence and the recorded reason that a synthetic result arrived and fresh assessment passed.
- Existing PDF and PNG downloaded through authenticated viewer links. PDF: 1,900 bytes; PNG: 24,402 bytes. Both file signatures, sizes and SHA-256 hashes match the existing registry.
- Missing-document UI behavior verified on Ravi: No linked documents returned. A separate unregistered-document browser navigation was blocked by the browser client; its HTTP status was not exposed, so live authenticated rejection of that URL is not claimed. Existing simulated route tests cover wrong-patient/unregistered document gates.
- Live Sign out of viewer cleared both open viewer tabs to the sign-in page. Subsequent anonymous HTTP probes returned authenticated=false, summary 401 and document 401. FHIR readiness remained 200.
- The worklist SQLite SHA-256 remained unchanged throughout the demonstration.
- Exact replay of the old browser cookie was not captured/performed live. It is covered by the passed simulated authentication tests. No cookies or tokens were saved in evidence.

The provider retained the reviewer SSO session. Reentering login reached the same consent screen without password entry, consistent with separate provider and viewer sessions. The first attempted consent click was rejected by automatic approval review pending fresh confirmation. The user subsequently approved it. The same permissions were accepted with Prompt me again next time selected; the browser returned to Signed in: Demo Reviewer and loaded Ravi records successfully.

The historical admin access_denied is explained by the provider log reason (admin cannot request openid). The working reviewer login is direct evidence that the reviewer identity and requested scopes can complete the flow after repair. No admin credentials were used to reproduce that denied attempt again.

No extra fixtures or clinical records were created or changed. Existing synthetic dates are fixture dates. Assessments concern information availability, not clinical clearance. No S3/Snowflake phase was started; only the already-existing viewer document retrieval path was tested.

## Startup and shutdown

```sh
# Renew only if the existing AWS session expired.
aws login --profile firely-learning
# Verify current native IPv4 and the existing single-IP SQL access rule.
curl -4 --silent --show-error https://checkip.amazonaws.com
# Reuse these containers; the Auth service name now points to the repaired instance.
docker start firely-learning-mailpit firely-learning-auth
docker start firely-learning-aws
curl --fail --silent --show-error 'http://localhost:8081/$readiness'
cd ~/firely-learning
document-tools-venv/bin/python -B worklist/authenticated_viewer_server.py
```

Check whether the viewer is already running before starting it. Keep its terminal open. Existing requirements: Docker Desktop, reachable RDS, local TLS certificates, installed PyJWT/cryptography, and an AWS session for existing document retrieval. Do not start the retained before-ui Auth container alongside the repaired service.

To stop locally: Ctrl+C in the viewer terminal, then:

```sh
docker stop firely-learning-aws firely-learning-auth firely-learning-mailpit
```

No shutdown command above deletes containers, volumes or records. Stopping local services does not stop RDS; no RDS lifecycle change has been made.

## Demo walkthrough and current handoff

1. Open https://localhost:8082 and sign in as Demo Reviewer. Grant the existing four resource read/search permissions plus identity/profile permissions, using Prompt me again next time.
2. Load Ravi: review the two laboratory results, booked visit, complete information assessment and empty documents list.
3. Load Training Person02: review the complete assessment, resolved work item and expanded resolution history; open the PDF and image.
4. Sign out: patient details clear across tabs and protected requests require a new viewer session. Provider SSO may remain signed in.

This walkthrough was exercised live through step 4. The user explicitly confirmed renewed consent. It was completed, and the signed-in viewer was restored and visually verified. No action is currently required. The viewer session expires after at most 15 minutes; a later demonstration may require sign-in again.

## Evidence and report checkpoint

Sanitized live evidence: worklist/evidence/reviewer-live-milestone-20261003T192742Z.json

Previous report checkpoint: checkpoints/live-demo-report-20261003T192742Z

No source changes were needed in this final verification pass. The source/configuration checkpoints and retained Auth container listed above remain available. Downloaded synthetic demonstration files are in the user's Downloads folder as doc-fixture-v2-p02-pdf.pdf and doc-fixture-v2-p02-png.png.

Reference: Firely's RSA JWK settings documentation: https://docs.fire.ly/projects/Firely-Server/en/6.8.1/security/firely-auth/firely-auth-settings.html

## Final checkpoint

Saved after the approved consent renewal: checkpoints/reviewer-milestone-passed-20261003T193009Z

Visual evidence: worklist/evidence/reviewer-milestone-signed-in.jpg

Final viewer URL: https://localhost:8082/

This milestone ends here. No additional project phase has been started. Remaining live negative-test gaps (old-cookie replay and authenticated wrong-document status) are explicitly documented above; their passing simulated tests are not relabeled as live tests.

## Subsequent verification milestone

The previously documented live old-cookie replay and authenticated wrong-document rejection gaps were closed on October 3, 2026 by the repeatable real-login runner (15/15 live checks passed). See REPEATABLE-VERIFICATION-MILESTONE-2026-10-03.md and worklist/evidence/repeatable-reviewer-20261003T213039864194Z.json. Earlier descriptions above retain the evidence available at that time.
