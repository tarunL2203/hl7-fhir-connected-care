# Repeatable reviewer verification

Run from `~/firely-learning` using the existing environment.
Commands save sanitized results under `worklist/evidence/repeatable-*.json` and return
nonzero when a check fails. No passwords, tokens, cookies, callback URLs or raw
provider/CLI errors are printed or saved. No command edits AWS resources or FHIR records.

## Read-only preflight

```sh
document-tools-venv/bin/python -B worklist/demo_check.py preflight
```

Checks the three existing Docker containers, the existing AWS login, RDS availability,
two matching IPv4-forced egress samples, attached security-group access for that IP,
the configured SQL endpoint, encryption/certificate-validation flags, and native IPv4
TCP connectivity. A TCP result does not independently prove a SQL login or TLS handshake;
the separate FHIR readiness check establishes service readiness.

If AWS login expired, renew with `aws login --profile firely-learning` and rerun.
If the public IP is no longer allowed, review the single-IP rule before any separately
authorized update. This tool never changes ingress rules or broadens access. Use an
IPv4-forced IP check: IPv6-translated egress can report a different address on this network.

## Start existing local services

```sh
document-tools-venv/bin/python -B worklist/demo_check.py start
```

Preflight must pass first. This starts the existing mailpit/Auth/FHIR containers and
waits up to 90 seconds for Auth discovery and FHIR readiness. An already-running
authenticated viewer is reused. Otherwise the command starts the normal HTTPS viewer
in the foreground. Keep that terminal open. This does not start Docker Desktop or RDS;
start Docker Desktop or restore the existing RDS dependency separately if needed.

## Live anonymous smoke test

```sh
document-tools-venv/bin/python -B worklist/demo_check.py smoke
```

Checks FHIR readiness, unauthenticated FHIR Patient denial, viewer health,
unauthenticated summary/document denial, trusted Auth TLS, and the expected discovery
issuer. All requests target running services; no simulated responses are used.

## Real reviewer and logout/replay verification

First stop the foreground viewer with Ctrl+C. Do not stop Docker, FHIR or Auth.
The command must own port 8082; it never attaches to or extracts another process's sessions.

```sh
document-tools-venv/bin/python -B worklist/demo_check.py reviewer --keep-serving
```

Open `https://localhost:8082/auth/login`, sign in as Demo Reviewer, and consent to the
existing identity/profile and four resource read/search scopes. Use "Prompt me again
next time". Login must complete within 600 seconds (adjust with `--login-timeout`).
OAuth login state itself lasts five minutes; begin again from the login entry point
if the consent flow has expired.

This mode constructs the same AuthService, TLS server and AuthenticatedHandler as
normal use. It waits for a session created by actual OIDC/PKCE verification. It does
not manufacture tokens, seed a session, change client registration, or add a test route.
Session identifiers and CSRF values stay in process memory only.

After login it automatically checks:

- Real summaries, observations, appointments and complete assessments for the two
  existing synthetic patients, including resolved worklist/history and Ravi's empty
  document list.
- Existing PDF/PNG retrieval through the viewer, with content type, size and SHA-256.
- HTTP 403 for wrong-patient and unregistered documents.
- HTTP 403 for invalid-CSRF and wrong-origin logout, while retaining the valid session.
- Valid logout, then deliberate HTTPS replay of the same old session cookie: summary
  and document return 401, session reports unauthenticated, and repeated logout returns 403.
- Unchanged local worklist database hash.

The test deliberately signs the viewer out. With `--keep-serving`, the normal routes
remain available afterward until Ctrl+C; the command prints and saves the test result
before waiting. Without this option it shuts down its viewer and exits with the result.
No private document bodies or token contents are saved in evidence.

The fixtures are expected to retain their demonstrated state. A changed fixture causes
a failed check, not an automatic record rewrite. Ordinary viewer sessions still expire
after at most 15 minutes; provider SSO is separate.

## Offline regression tests

```sh
document-tools-venv/bin/python -B -m unittest discover -s worklist -p test_viewer_auth.py -v
document-tools-venv/bin/python -B -m unittest discover -s worklist -p test_demo_check.py -v
document-tools-venv/bin/python -B worklist/test_worklist.py
```

These test simulated provider/FHIR/S3 behavior, temporary local HTTP route servers,
startup guardrails and a temporary worklist. Label them offline/simulated; they do not
replace real reviewer verification.

To stop local services, Ctrl+C the viewer and then, if desired:

```sh
docker stop firely-learning-aws firely-learning-auth firely-learning-mailpit
```

Keep the retained `firely-learning-auth-before-ui-20261003T191031Z` container stopped.
Do not remove volumes or restore the exposed old signing key from private checkpoints.
