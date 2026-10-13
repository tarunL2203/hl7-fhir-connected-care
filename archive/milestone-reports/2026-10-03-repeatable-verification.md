# Repeatable verification milestone — October 3, 2026

Status: PASSED. The prior live security-test gaps are now verified against running services after a real Demo Reviewer login and user-approved consent.

## What changed

- Added worklist/demo_check.py with preflight, smoke, start and reviewer modes.
- Extracted create_server() from authenticated_viewer_server.py so normal use and live verification construct the same AuthService, TLS server and request handler. Authentication logic was not changed.
- Added four offline startup guardrail tests and worklist/README-verification.md. Updated the original auth README to point at current startup instructions and record the repaired provider UI.
- No AWS resources or ingress rules were changed in this milestone. No FHIR records, document objects or worklist rows were modified. No additional paid resources or new project phase were started.

## Live results

Preflight: 6/6 passed. It verified the existing containers, AWS login, two consistent native-IPv4 egress samples, available/public RDS, current IP allowed by attached security groups, matching SQL endpoint, required encryption/certificate-validation flags, and native IPv4 SQL TCP access.

Anonymous smoke: 6/6 passed. FHIR readiness and viewer health returned 200; anonymous FHIR Patient, viewer summary and document requests returned 401; Auth discovery passed TLS validation and issuer checking.

Real reviewer run: 15/15 passed. This included the six checks above plus:

- Both existing synthetic patient summaries: real patient/observation/appointment reads, information_complete assessments, Ravi's empty document list, and Person02's resolved work item with created → in_review → resolved history.
- Existing PDF and PNG retrieval through the viewer: correct content type, byte size and SHA-256.
- Wrong-patient document and unregistered document requests: HTTP 403 with the expected registry/patient denial code.
- Invalid CSRF and wrong-origin logout: HTTP 403; the valid session remained active afterward.
- Valid logout: HTTP 200. The runner deliberately retained the original cookie in memory and replayed it over HTTPS: summary 401, document 401, session authenticated=false, repeated logout 403. This was a live test, not a simulated replay.
- Worklist database hash unchanged.

The runner waits for a session created by normal OIDC/PKCE verification. It does not mint tokens, forge claims, seed sessions, extract browser cookies, add a diagnostic HTTP endpoint, or bypass authorization. The browser obtained normal consent; only the test process retained its own server's verified session identifier in memory for actual HTTP requests. No cookies, tokens or document bodies were saved in evidence.

## Offline regression results

- 21/21 existing authentication tests passed (simulated provider/FHIR/S3 and local temporary HTTP routes).
- 4/4 new guardrail tests passed: TLS settings, changed-IP/port/protocol denial, expired AWS session remediation, and suppression of raw credential-bearing CLI errors.
- 9/9 existing worklist tests passed against a temporary synthetic store.

These 34 offline checks are distinct from the live results above. No claims are made about general production healthcare readiness or clinical clearance.

## Repeatable commands

Run from ~/firely-learning:

```sh
# Read-only AWS, network and configuration checks.
document-tools-venv/bin/python -B worklist/demo_check.py preflight
# Start/reuse existing services only after preflight passes.
document-tools-venv/bin/python -B worklist/demo_check.py start
# Anonymous live checks; no login required.
document-tools-venv/bin/python -B worklist/demo_check.py smoke
```

For the full reviewer test, Ctrl+C the foreground viewer first, keep Docker/FHIR/Auth running, then:

```sh
document-tools-venv/bin/python -B worklist/demo_check.py reviewer --keep-serving
```

Complete the normal Demo Reviewer login at https://localhost:8082/auth/login. The test deliberately logs the viewer session out and verifies cookie replay denial. With --keep-serving the ordinary routes remain available; without it the test exits with its result and stops its own server. Default login wait is 600 seconds; OAuth state still expires after five minutes.

Commands never renew AWS login or edit security groups automatically. An expired AWS session calls for aws login --profile firely-learning. An IP mismatch reports the condition for review. Detailed startup/shutdown and error instructions are in worklist/README-verification.md.

## Saved evidence

- worklist/evidence/repeatable-preflight-20261003T212556289254Z.json
- worklist/evidence/repeatable-smoke-20261003T212558136700Z.json
- worklist/evidence/repeatable-reviewer-20261003T213039864194Z.json
- worklist/evidence/repeatable-start-20261003T212906720214Z.json (already-running viewer reuse)
- worklist/evidence/repeatable-start-20261003T213146362882Z.json (normal viewer launched after verification)
- worklist/evidence/repeatable-verification-complete.jpg

## Checkpoints and final state

Before editing: checkpoints/before-repeatable-verification-20261003T212033Z/

Completed source, documentation and evidence checkpoint: checkpoints/repeatable-verification-passed-20261003T213341Z

After the completed verification runner was stopped, the new start command passed preflight and restored the normal viewer. The final browser shows the sign-in page at https://localhost:8082/. This signed-out state is intentional following logout testing. Services remain available; a fresh viewer login may require consent.

The earlier private Auth configuration checkpoints and retained before-ui container are unchanged. Do not restore the exposed old signing key. The current security-group rule remains the previously recorded single-IP rule; it was not changed here.

## Remaining limits

This is a local synthetic learning demo. Network IPs, AWS sessions and viewer sessions can expire or change; the new commands detect those conditions rather than silently changing access. Provider-wide logout, activation/reset flows, clinical validation, broader care-team authorization, and deployment hardening remain outside this milestone. No S3/Snowflake phase has been initiated.
