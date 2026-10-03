# Authenticated learning viewer

This update adds a public-client OpenID Connect authorization-code flow with
PKCE to the existing synthetic learning viewer. The registered callback is
`https://localhost:8082/auth/callback` and the client is `firely-learning-viewer`.

## Installation and startup

For this already-installed project, use [repeatable verification and startup](README-verification.md).
The package installation instructions below are historical; do not rerun the old installer
over the current milestone.

Extract this package under `~/Downloads/viewer-auth-update/`.
Stop the old document viewer with Ctrl+C in its terminal. Keep Docker running.

```sh
python3 "$HOME/Downloads/viewer-auth-update/install_viewer_auth.py"
"$HOME/firely-learning/document-tools-venv/bin/python" \
  "$HOME/firely-learning/worklist/authenticated_viewer_server.py"
```

Open `https://localhost:8082`, choose Sign in with Firely, and use the reviewer
account. Consent to the four resource types with read/search scopes. The account
must have the configured `fhirUser` of `Practitioner/demo-reviewer`. The admin
account is deliberately not an accepted viewer identity.

The installer verifies package checksums and hashes of the previously supplied
source files before modifying anything. It preserves rollback copies and accepts
an already-installed update. It does not install libraries, alter the FHIR
container, or change the worklist database/specifications. Required Python
dependencies are `PyJWT[crypto]` (PyJWT 2.x) and its cryptography dependency.

Certificates must exist under `~/firely-learning/auth/certs/`:
`localhost.pem`, `localhost-key.pem`, and `local-rootCA.crt`. Firely Auth must
respond at `https://localhost:5001`. Its public discovery document must identify
that issuer. The FHIR token audience is `http://host.docker.internal:8081`, while
the viewer reads the loopback FHIR service at `http://localhost:8081`.

## Security behavior

- ID and access tokens undergo RSA/RS256 signature, issuer, audience, time,
  subject, client, nonce, and scope checks. The ID token's access-token hash is
  checked when supplied. Provider endpoints stay on the configured HTTPS origin;
  redirects to other endpoints are blocked.
- OAuth state expires after five minutes, is bound to the initiating browser
  cookie, and is single-use. The code is exchanged with a PKCE verifier.
- Access tokens live only in server memory. Browser cookies contain random session
  identifiers and use Secure, HttpOnly, SameSite=Lax, and the __Host- prefix.
  Sessions expire with the access token or after 15 minutes, whichever comes first.
  Restarting the viewer ends all viewer sessions. No refresh tokens are requested.
- Every summary and document request requires a viewer session. Every FHIR read,
  including pagination and the DocumentReference access check, forwards that
  session's token. Request contexts isolate concurrent users' tokens.
- An S3 read follows a successful authorized DocumentReference read and the
  existing patient, registry, content-type, size, and SHA-256 checks.
- The worklist remains read-only. The existing assessment logic is preserved.
- Logout is a same-origin, CSRF-protected POST. It invalidates the viewer session,
  clears the browser cookie and displayed records, and notifies other viewer tabs.
  The server rejects reuse of a logged-out session cookie.
- Authorization codes, states, passwords, cookies, and tokens are not logged.
  Login errors expose a short code, not provider responses or token contents.

## Logout and remaining limitations

**Sign out of viewer ends the viewer's session. It does not end Firely Auth's
separate sign-in session.** A subsequent sign-in can reuse the provider session.
The earlier development-mode redirect to `http://localhost:3000` was repaired by
running the same Auth image in the Production environment with its existing volumes.
The login UI now uses `https://localhost:5001`. Activation/reset and global provider
logout have not been included in the reviewer milestone. The viewer's own logout is separate.

The current access model is restricted to the explicit synthetic demo reviewer;
it is not a general care-team or organization authorization policy. Existing
administrative workflow role tests are separate from the read-only viewer login.
S3 retrieval still uses the local AWS CLI profile, after the FHIR access gate.
The FHIR connection is HTTP over local loopback. Cloud deployment needs a reviewed
HTTPS topology, durable session storage if scaled, and appropriately scoped cloud
credentials. This local Python HTTP server is a learning implementation, not a
production deployment or a compliance certification.

## Verification

Offline tests use real RSA signatures with a simulated provider, local HTTP test
requests, simulated FHIR responses, and simulated S3 downloads. They do not contact
AWS or validate your actual Firely deployment. Run after installation:

```sh
cd "$HOME/firely-learning/worklist"
"$HOME/firely-learning/document-tools-venv/bin/python" -m unittest test_viewer_auth -v
"$HOME/firely-learning/document-tools-venv/bin/python" test_worklist.py
```

Live acceptance checks:

1. Signed out: `/patients/demo-patient-002/summary` and the registered document
   routes return HTTP 401 without invoking retrieval.
2. Sign in as reviewer and consent: both selectable patients load with their
   original assessments and worklist history.
3. Training Person02's PDF and PNG open. A wrong-patient document route returns
   HTTP 403, and an unregistered document remains inaccessible.
4. Sign out of viewer: records clear; refresh shows the sign-in page. Anonymous
   summary/document requests still return 401. Sign in again to resume.

If login fails, report only the safe error code or startup error. Do not share
the callback URL, activation/reset link, cookies, passwords, or token responses.
