# Connection check — October 4, 2026

Read-only live checks; no configuration, AWS resources or service state changed.

- Docker context desktop-linux works. Existing FHIR, Auth and Mailpit containers running.
- Configured RDS endpoint matches <RDS_ENDPOINT>:1433. IPv4 DNS resolution and TCP 1433 succeeded. Encrypt=True and TrustServerCertificate=False retained. TCP alone does not verify database authentication.
- AWS profile firely-learning session expired. Renew using `aws login --profile firely-learning`. RDS control-plane status, attached security-group access and existing PDF/PNG S3 metadata could not be verified with the expired session.
- FHIR readiness and Auth discovery return HTTP 402, including direct requests bypassing proxies. Cause not established by the sanitized response/log checks. Readiness has not passed today.
- Viewer health passed; signed-out viewer summary/document and FHIR Patient requests correctly returned 401.
- Mailpit UI returned HTTP 200.
- Authenticated patient/document flows were not rerun. Prior milestone evidence remains historical, not proof of current readiness.

Evidence: worklist/evidence/repeatable-preflight-20261004T224207846267Z.json, worklist/evidence/repeatable-smoke-20261004T224206924354Z.json, worklist/evidence/repeatable-connection-followup-20261004T224315743816Z.json.

## After AWS renewal and recovery

AWS preflight passed 6/6. Both existing document objects passed authenticated S3 metadata/size checks. Evidence: repeatable-preflight-20261004T224718908387Z.json and repeatable-documents-renewed-20261004T224749525580Z.json under worklist/evidence/.

Structured service errors established the HTTP 402 cause: both Firely services exceeded the evaluation maximum uptime of 12 hours. FHIR reported code 5007; both messages explicitly permit restarting to continue evaluation. Restarted only existing firely-learning-aws and firely-learning-auth containers. No volume, record, license, AWS setting or configuration changes. Early startup checks failed while initializing; both endpoints subsequently returned 200. Fresh reviewer login is the next browser check; authenticated record retrieval has not been repeated today.
