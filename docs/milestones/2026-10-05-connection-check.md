# Connection check — October 5, 2026

Checked approximately 00:22–00:25 America/New_York. RAW milestone remains BLOCKED.

## Live results

- Docker context desktop-linux; existing Firely FHIR/Auth containers running approximately 6 hours, Mailpit healthy.
- RDS hostname resolved and TCP 1433 connection succeeded from the Mac.
- FHIR readiness passed; anonymous Patient access denied as expected.
- Firely Auth trusted TLS/discovery issuer check passed.
- Viewer port 8082 initially had no listener. Started the existing worklist/authenticated_viewer_server.py with the existing Python environment. No source/configuration edits or container restart.
- After startup all 6 smoke checks passed: FHIR readiness, anonymous FHIR denial, viewer health, anonymous summary/document denial, Auth TLS/discovery.
- AWS profile firely-learning session expired. RDS control-plane availability, security-group rules and direct S3/IAM checks could not be freshly verified. User was asked to run aws login --profile firely-learning.
- Snowflake browser session remained authenticated as <SNOWFLAKE_USER>. Existing workspace reopened. Historical October 4 RAW count result displayed 0; this is not a new count query.
- Fresh LIST @CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_STAGE executed October 5 at 00:24:04 local time. Result: AWS denies sts:AssumeRole to arn:aws:iam::<SNOWFLAKE_AWS_ACCOUNT>:user/<snowflake-iam-user> on arn:aws:iam::<AWS_ACCOUNT_ID>:role/firely-snowflake-read-5dd08717. No COPY attempted. No query ID captured in this check.

## Evidence

- worklist/evidence/repeatable-preflight-20261005T042227855928Z.json
- worklist/evidence/repeatable-smoke-20261005T042336464044Z.json (6/6 passed)
- analytics/evidence/snowflake-assume-role-denied-20261005.png

Earlier sandbox-restricted attempts reported Docker/network failures; these were execution-environment limitations, superseded by checks with required access. They are not evidence that the services were down. The viewer failure was independently confirmed by no listener and corrected.

## Next step

Renew existing AWS login, then verify caller identity and resume read-only diagnosis of the exact role-assumption denial. The previous Organizations simulator clue is not a proven policy root cause. No AWS policy/security group, Snowflake integration, clinical data, batch or authentication setting changed during this check. The existing viewer is serving at https://localhost:8082/; its authenticated reviewer session and private document retrieval were not retested this turn.

## After AWS renewal

User completed login renewal. All 6 infrastructure preflight checks passed, including RDS availability, current IPv4 ingress, configured SQL TLS settings and TCP. Evidence: worklist/evidence/repeatable-preflight-20261005T042506546310Z.json.

Live role trust and inline read policy exactly match the saved scoped configuration; no permissions boundary is attached. Organizations describes <AWS_ORG_ID> with management account <AWS_MGMT_ACCOUNT_ID>. ListParents, SCP listing and RCP listing each return AccessDeniedException. Sanitized evidence: analytics/evidence/renewed-access-check-20261005.json.

User clarified this is an AWS trial account with potentially restricted features. Do not infer that trial status itself proves the cause. No privileges were expanded. Next necessary clarification: whether management account <AWS_MGMT_ACCOUNT_ID> is recognized/accessible, or the account is administered by a trial/lab provider. The latter requires the provider's scoped review rather than a privilege workaround.
