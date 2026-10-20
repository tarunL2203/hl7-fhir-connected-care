# Worklist and reviewer portal

The pre-visit rules engine, the follow-up worklist and the authenticated reviewer portal. For how these fit into the platform, see the [architecture](../docs/architecture.md).

## Modules

| Module | Responsibility |
|---|---|
| [`evaluator_v2.py`](evaluator_v2.py) | Evaluates one visit against [`spec/v2/policy.json`](spec/v2/policy.json). Returns `information_complete`, `information_gap`, `unable_to_assess` or `requirements_not_configured`, with the matched, rejected and uncertain records |
| [`worklist_store.py`](worklist_store.py), [`worklist_bridge.py`](worklist_bridge.py) | SQLite worklist: work items deduplicated on appointment + requirement + issue, guarded transitions (open → in_review → resolved), append-only history, reopening of reappearing issues |
| [`fhir_client.py`](fhir_client.py) | Allow-listed access to the secured FHIR server (`FHIR_SECURED_URL`, default `http://localhost:8081`) with complete, loop-safe pagination |
| [`auth_fhir.py`](auth_fhir.py) | The same reads using the current request's verified access token |
| [`viewer_auth.py`](viewer_auth.py) | OpenID Connect authorization code + PKCE: state, nonce, RS256 token validation and server-side sessions |
| [`authenticated_viewer_server.py`](authenticated_viewer_server.py) | HTTPS entry point (`https://localhost:8082`): sign-in, callback, CSRF-protected logout, authenticated routing |
| [`summary_api.py`](summary_api.py) | Patient summary: patient, observations, appointments, assessments and worklist history |
| [`document_viewer_server.py`](document_viewer_server.py) | Verified document retrieval; local-mode verification and batch export routes |
| [`portal_batch_export.py`](portal_batch_export.py) | Builds an NDJSON batch and manifest from two matching authenticated reads |
| [`demo_check.py`](demo_check.py) | Read-only `preflight` and `smoke` checks, `start`, and an opt-in live `reviewer` verification run |
| [`viewer.html`](viewer.html), [`viewer_server.py`](viewer_server.py) | The reviewer page |
| `assess_demo_patient.py`, `assess_missing_demo.py`, `load_missing_demo.py`, `register_documents.py`, `sync_demo_worklist.py` | Scripts that load and assess the two demo patients against a running Firely server |

Configuration lives in [`spec/v2/`](spec/v2/): the policy, visit assignments, the document registry, test scenarios and the local-mode switch. Offline assessment cases are in [`fixtures/v2/`](fixtures/v2/).

## Tests

All offline, with no network access, Docker or cloud accounts:

```sh
python -B -m unittest test_viewer_auth test_demo_check   # 26 auth, route and startup guardrail tests
python -B test_worklist.py                               # 9 workflow tests
```

The authentication tests use real RS256 signatures against a simulated provider, FHIR server and S3. They cover anonymous denial, PKCE and state handling, token checks, CSRF and origin checks on logout, session replay, wrong-patient documents, hash failures and local-mode deferral.

## Running the portal

With Firely Server, Firely Auth and the local TLS certificates in `auth/certs/` in place (see the [sanitized Firely Auth configuration](../infra/firely-auth/appsettings.instance.example.json)):

```sh
python worklist/demo_check.py preflight   # read-only checks of containers, database access and FHIR readiness
python worklist/authenticated_viewer_server.py
```

Then open `https://localhost:8082` and sign in as the reviewer. Sessions last 15 minutes. Signing out ends the portal session; Firely Auth may keep its own sign-in session.

---

<sub>[← README](../README.md) · [Project tour](../docs/tour.md)</sub>
