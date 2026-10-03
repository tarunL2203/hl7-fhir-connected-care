"""Local demo OIDC code/PKCE flow. No passwords or tokens are written to disk."""
import base64
import hashlib
import hmac
import json
import secrets
import ssl
import threading
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPSHandler, HTTPRedirectHandler, build_opener
import jwt

ISSUER = "https://localhost:5001"
ORIGIN = "https://localhost:8082"
CLIENT_ID = "firely-learning-viewer"
AUDIENCE = "http://host.docker.internal:8081"
CALLBACK = ORIGIN + "/auth/callback"
RESOURCE_TYPES = ("Patient", "Observation", "Appointment", "DocumentReference")
READ_SCOPES = {"user/" + resource + ".rs" for resource in RESOURCE_TYPES}
SCOPES = " ".join(["openid", "profile", "fhirUser", *sorted(READ_SCOPES)])
REVIEWER = "Practitioner/demo-reviewer"

class AuthError(Exception):
    """Safe error code; never contains a token or provider response."""

class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise AuthError("provider_redirect_blocked")

def provider_url(url):
    p = urlsplit(url)
    if (p.scheme != "https" or p.netloc != "localhost:5001"
            or p.username or p.password or p.fragment):
        raise AuthError("unexpected_provider_endpoint")
    return url

class Provider:
    def __init__(self, ca_file):
        context = ssl.create_default_context(cafile=str(ca_file))
        self.opener = build_opener(NoRedirects(), HTTPSHandler(context=context))

    def fetch(self, url, form=None, token=None):
        headers = {"Accept": "application/json"}
        body = None
        if form is not None:
            body = urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if token:
            headers["Authorization"] = "Bearer " + token
        request = Request(provider_url(url), data=body, headers=headers)
        try:
            with self.opener.open(request, timeout=20) as response:
                raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise AuthError("provider_response_too_large")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise AuthError("invalid_provider_response")
            return value
        except AuthError:
            raise
        except Exception:
            raise AuthError("provider_request_failed") from None

class AuthService:
    def __init__(self, provider):
        self.provider = provider
        self.lock = threading.RLock()
        self.pending = {}
        self.sessions = {}
        self.discovery = provider.fetch(ISSUER + "/.well-known/openid-configuration")
        if self.discovery.get("issuer") != ISSUER:
            raise AuthError("unexpected_provider_issuer")
        for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            provider_url(self.discovery[field])
        if self.discovery.get("userinfo_endpoint"):
            provider_url(self.discovery["userinfo_endpoint"])
        self.keys = []
        self.refresh_keys()

    def refresh_keys(self):
        keys = self.provider.fetch(self.discovery["jwks_uri"]).get("keys")
        if not isinstance(keys, list):
            raise AuthError("invalid_provider_keys")
        with self.lock:
            self.keys = keys

    def prune(self):
        now = time.time()
        self.pending = {k: v for k, v in self.pending.items() if v["expires"] > now}
        self.sessions = {k: v for k, v in self.sessions.items() if v["expires"] > now}

    def begin(self):
        state, browser, nonce, verifier = [secrets.token_urlsafe(32) for _ in range(4)]
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).rstrip(b"=").decode()
        with self.lock:
            self.prune()
            if len(self.pending) >= 128:
                raise AuthError("too_many_login_attempts")
            self.pending[state] = {
                "browser": browser, "nonce": nonce, "verifier": verifier,
                "expires": time.time() + 300
            }
        query = urlencode({
            "client_id": CLIENT_ID, "redirect_uri": CALLBACK,
            "response_type": "code", "response_mode": "query",
            "scope": SCOPES, "aud": AUDIENCE,
            "state": state, "nonce": nonce,
            "code_challenge": challenge, "code_challenge_method": "S256"
        })
        return self.discovery["authorization_endpoint"] + "?" + query, browser

    def consume(self, state, browser):
        with self.lock:
            self.prune()
            pending = self.pending.get(state)
            if not pending or not browser or not hmac.compare_digest(pending["browser"], browser):
                raise AuthError("invalid_or_expired_login_state")
            return self.pending.pop(state)

    def decode(self, token, audience):
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise AuthError("unsupported_token_signing_algorithm")
            def matching_keys():
                with self.lock:
                    return [key for key in self.keys
                            if key.get("kid") == header["kid"]
                            and key.get("kty") == "RSA"
                            and key.get("use", "sig") == "sig"
                            and key.get("alg", "RS256") == "RS256"]
            keys = matching_keys()
            if not keys:
                self.refresh_keys()
                keys = matching_keys()
            if len(keys) != 1:
                raise AuthError("unknown_token_signing_key")
            key = jwt.PyJWK.from_dict(keys[0]).key
            return jwt.decode(
                token, key, algorithms=["RS256"], issuer=ISSUER,
                audience=audience, leeway=0,
                options={"require": ["iss", "aud", "sub", "exp", "iat"]}
            )
        except AuthError:
            raise
        except Exception:
            raise AuthError("token_validation_failed") from None

    def complete(self, pending, code):
        response = self.provider.fetch(self.discovery["token_endpoint"], form={
            "grant_type": "authorization_code", "client_id": CLIENT_ID,
            "redirect_uri": CALLBACK, "code": code,
            "code_verifier": pending["verifier"]
        })
        if str(response.get("token_type", "")).lower() != "bearer":
            raise AuthError("unexpected_token_type")
        access = response.get("access_token")
        identity = response.get("id_token")
        if not isinstance(access, str) or not isinstance(identity, str):
            raise AuthError("missing_login_tokens")
        claims = self.decode(access, AUDIENCE)
        id_claims = self.decode(identity, CLIENT_ID)
        if id_claims.get("azp", CLIENT_ID) != CLIENT_ID:
            raise AuthError("unexpected_authorized_party")
        if isinstance(id_claims["aud"], list) and len(id_claims["aud"]) > 1 and "azp" not in id_claims:
            raise AuthError("missing_authorized_party")
        if not isinstance(id_claims.get("nonce"), str) or not hmac.compare_digest(id_claims["nonce"], pending["nonce"]):
            raise AuthError("login_nonce_mismatch")
        if claims["sub"] != id_claims["sub"] or claims.get("client_id") != CLIENT_ID:
            raise AuthError("login_subject_or_client_mismatch")
        if "at_hash" in id_claims:
            expected = base64.urlsafe_b64encode(
                hashlib.sha256(access.encode()).digest()[:16]
            ).rstrip(b"=").decode()
            if not isinstance(id_claims["at_hash"], str) or not hmac.compare_digest(expected, id_claims["at_hash"]):
                raise AuthError("access_token_hash_mismatch")
        scope = claims.get("scope", [])
        scope = set(scope.split() if isinstance(scope, str) else scope)
        if not READ_SCOPES <= scope:
            raise AuthError("required_read_scopes_not_granted")
        fhir_user = id_claims.get("fhirUser") or claims.get("fhirUser")
        if not fhir_user and self.discovery.get("userinfo_endpoint"):
            userinfo = self.provider.fetch(self.discovery["userinfo_endpoint"], token=access)
            if userinfo.get("sub") != claims["sub"]:
                raise AuthError("userinfo_subject_mismatch")
            fhir_user = userinfo.get("fhirUser")
        permitted = {
            REVIEWER, "http://localhost:8081/" + REVIEWER,
            AUDIENCE + "/" + REVIEWER
        }
        if not isinstance(fhir_user, str) or fhir_user not in permitted:
            raise AuthError("demo_reviewer_identity_required")
        now = time.time()
        expires = min(float(claims["exp"]), now + 900)
        if expires <= now:
            raise AuthError("access_token_expired")
        session_id = secrets.token_urlsafe(32)
        session = {
            "access_token": access, "claims": claims,
            "expires": expires, "csrf": secrets.token_urlsafe(32),
            "fhir_user": REVIEWER, "display_name": "Demo Reviewer"
        }
        with self.lock:
            self.prune()
            if len(self.sessions) >= 128:
                raise AuthError("too_many_viewer_sessions")
            self.sessions[session_id] = session
        return session_id, session

    def session(self, session_id):
        with self.lock:
            self.prune()
            return self.sessions.get(session_id)

    def logout(self, session_id, csrf):
        with self.lock:
            session = self.session(session_id)
            if not session or not isinstance(csrf, str) or not hmac.compare_digest(session["csrf"], csrf):
                raise AuthError("invalid_logout_request")
            self.sessions.pop(session_id, None)
