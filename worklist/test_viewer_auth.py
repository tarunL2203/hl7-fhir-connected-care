"""Offline security tests: real signatures, simulated provider/FHIR/S3."""
import base64
import hashlib
import io
import json
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from http.server import ThreadingHTTPServer
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

import auth_fhir
import document_viewer_server
from authenticated_viewer_server import AuthenticatedHandler, SESSION_COOKIE
from viewer_auth import AuthService, AuthError, ISSUER, CLIENT_ID, AUDIENCE, READ_SCOPES, REVIEWER

class FakeProvider:
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self.public.update(kid="test-key", use="sig", alg="RS256")
        self.access_changes, self.id_changes = {}, {}
        self.calls = []
        self.transaction = None

    def token(self, claims):
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "test-key"})

    def fetch(self, url, form=None, token=None):
        self.calls.append((url, form))
        if url.endswith("openid-configuration"):
            return {"issuer": ISSUER, "authorization_endpoint": ISSUER + "/connect/authorize",
                    "token_endpoint": ISSUER + "/connect/token", "jwks_uri": ISSUER + "/keys"}
        if url.endswith("/keys"):
            return {"keys": [self.public]}
        if url.endswith("/connect/token"):
            if form["code"] != "one-use-test-code" or form["code_verifier"] != self.transaction["verifier"]:
                raise AuthError("invalid_test_code_or_verifier")
            now = int(time.time())
            access = {"iss": ISSUER, "aud": AUDIENCE, "sub": "reviewer-id",
                      "iat": now - 1, "exp": now + 900, "client_id": CLIENT_ID,
                      "scope": sorted(READ_SCOPES)}
            identity = {"iss": ISSUER, "aud": CLIENT_ID, "sub": "reviewer-id",
                        "iat": now - 1, "exp": now + 900,
                        "nonce": self.transaction["nonce"], "fhirUser": REVIEWER}
            access.update(self.access_changes)
            identity.update(self.id_changes)
            return {"token_type": "Bearer", "access_token": self.token(access),
                    "id_token": self.token(identity)}
        raise AssertionError("Unexpected provider URL")

class AuthTests(unittest.TestCase):
    def setUp(self):
        self.provider = FakeProvider()
        self.auth = AuthService(self.provider)

    def transaction(self):
        location, browser = self.auth.begin()
        query = parse_qs(urlsplit(location).query)
        pending = self.auth.consume(query["state"][0], browser)
        self.provider.transaction = pending
        return pending

    def login(self):
        return self.auth.complete(self.transaction(), "one-use-test-code")

    def test_successful_verified_login(self):
        sid, session = self.login()
        self.assertIs(self.auth.session(sid), session)
        self.assertEqual(session["fhir_user"], REVIEWER)

    def test_pkce_challenge_and_browser_binding(self):
        location, browser = self.auth.begin()
        query = parse_qs(urlsplit(location).query)
        state = query["state"][0]
        with self.assertRaises(AuthError):
            self.auth.consume(state, "other-browser")
        pending = self.auth.consume(state, browser)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(pending["verifier"].encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(query["code_challenge"], [challenge])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        with self.assertRaises(AuthError):
            self.auth.consume(state, browser)

    def test_expired_login_state(self):
        location, browser = self.auth.begin()
        state = parse_qs(urlsplit(location).query)["state"][0]
        self.auth.pending[state]["expires"] = time.time() - 1
        with self.assertRaises(AuthError):
            self.auth.consume(state, browser)

    def test_nonce_mismatch(self):
        self.provider.id_changes["nonce"] = "wrong-nonce"
        with self.assertRaisesRegex(AuthError, "nonce"):
            self.login()

    def test_bad_signature(self):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.provider.token = lambda claims: jwt.encode(claims, other, algorithm="RS256", headers={"kid": "test-key"})
        with self.assertRaises(AuthError):
            self.login()

    def test_wrong_issuer_audience_expiry_and_subject(self):
        for change in ({"iss": "https://attacker.test"}, {"aud": "other-audience"},
                       {"exp": int(time.time()) - 1}, {"sub": "another-user"},
                       {"client_id": "another-client"}):
            with self.subTest(change=change):
                self.provider.access_changes = change
                with self.assertRaises(AuthError):
                    self.login()

    def test_algorithm_confusion_blocked(self):
        token = jwt.encode({"sub": "x"}, "not-an-rsa-key-but-long-enough-for-hmac", algorithm="HS256", headers={"kid": "test-key"})
        with self.assertRaisesRegex(AuthError, "algorithm"):
            self.auth.decode(token, AUDIENCE)

    def test_wrong_user_and_insufficient_scopes(self):
        self.provider.id_changes["fhirUser"] = "Patient/demo-patient-002"
        with self.assertRaisesRegex(AuthError, "reviewer"):
            self.login()
        self.provider.id_changes.clear()
        self.provider.access_changes["scope"] = ["user/Patient.rs"]
        with self.assertRaisesRegex(AuthError, "scopes"):
            self.login()

    def test_logout_csrf_and_expiration(self):
        sid, session = self.login()
        with self.assertRaises(AuthError):
            self.auth.logout(sid, "wrong-csrf")
        self.assertIsNotNone(self.auth.session(sid))
        self.auth.logout(sid, session["csrf"])
        self.assertIsNone(self.auth.session(sid))
        sid, session = self.login()
        session["expires"] = time.time() - 1
        self.assertIsNone(self.auth.session(sid))

class FakeOpener:
    def __init__(self):
        self.headers = []
        self.responses = []
    def open(self, request, timeout):
        self.headers.append(request.get_header("Authorization"))
        return io.BytesIO(json.dumps(self.responses.pop(0)).encode())

class TransportTests(unittest.TestCase):
    def test_no_token_no_network(self):
        with patch.object(auth_fhir.opener, "open") as network:
            with self.assertRaises(RuntimeError):
                auth_fhir.get_json("http://localhost:8081/Patient")
            network.assert_not_called()

    def test_all_pages_forward_token(self):
        opener = FakeOpener()
        opener.responses = [
            {"resourceType": "Bundle", "type": "searchset", "entry": [],
             "link": [{"relation": "next", "url": "http://localhost:8081/Patient?page=2"}]},
            {"resourceType": "Bundle", "type": "searchset", "entry": []}
        ]
        context = auth_fhir.ACCESS_TOKEN.set("test-token")
        try:
            with patch.object(auth_fhir, "opener", opener):
                self.assertEqual(auth_fhir.search("Patient", "Patient"), [])
        finally:
            auth_fhir.ACCESS_TOKEN.reset(context)
        self.assertEqual(opener.headers, ["Bearer test-token", "Bearer test-token"])

    def test_external_pagination_blocked(self):
        opener = FakeOpener()
        opener.responses = [{"resourceType": "Bundle", "type": "searchset", "entry": [],
                             "link": [{"relation": "next", "url": "https://attacker.test/Patient"}]}]
        context = auth_fhir.ACCESS_TOKEN.set("test-token")
        try:
            with patch.object(auth_fhir, "opener", opener):
                with self.assertRaises(RuntimeError):
                    auth_fhir.search("Patient", "Patient")
        finally:
            auth_fhir.ACCESS_TOKEN.reset(context)
        self.assertEqual(len(opener.headers), 1)

    def test_thread_token_isolation(self):
        results = {}
        barrier = threading.Barrier(2)
        def worker(name):
            context = auth_fhir.ACCESS_TOKEN.set(name)
            barrier.wait()
            results[name] = auth_fhir.ACCESS_TOKEN.get()
            auth_fhir.ACCESS_TOKEN.reset(context)
        threads = [threading.Thread(target=worker, args=(name,)) for name in ("one", "two")]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(results, {"one": "one", "two": "two"})
        self.assertIsNone(auth_fhir.ACCESS_TOKEN.get())

class QuietHandler(AuthenticatedHandler):
    def log_message(self, *args):
        pass

class NoFollow(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

class RouteTests(unittest.TestCase):
    def setUp(self):
        self.root_patch = patch.object(document_viewer_server, "ROOT", Path(__file__).parent)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        # These tests exercise the document gate; local mode (deferred documents) is tested separately.
        self.mode_patch = patch.object(document_viewer_server, "local_mode", return_value=False)
        self.mode_patch.start()
        self.addCleanup(self.mode_patch.stop)
        self.provider = FakeProvider()
        self.auth = AuthService(self.provider)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        self.server.auth = self.auth
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_port)
        self.opener = build_opener(NoFollow())

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, cookie=None, body=None, origin=None):
        headers = {"Host": "localhost:8082"}
        if cookie: headers["Cookie"] = cookie
        if origin: headers["Origin"] = origin
        raw = json.dumps(body).encode() if body is not None else None
        try:
            response = self.opener.open(Request(self.base + path, data=raw, headers=headers), timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def make_session(self):
        location, browser = self.auth.begin()
        state = parse_qs(urlsplit(location).query)["state"][0]
        self.provider.transaction = self.auth.consume(state, browser)
        sid, session = self.auth.complete(self.provider.transaction, "one-use-test-code")
        return sid, session, SESSION_COOKIE + "=" + sid

    def test_anonymous_summary_and_document_never_touch_backend(self):
        with patch.object(document_viewer_server, "summary") as summary, patch.object(document_viewer_server.subprocess, "run") as s3:
            for path in ("/patients/demo-patient-002/summary", "/patients/fixture-v2-p02/documents/doc-fixture-v2-p02-pdf"):
                self.assertEqual(self.request(path)[0], 401)
            summary.assert_not_called()
            s3.assert_not_called()
        self.assertIn(b"Sign in with Firely", self.request("/")[2])

    def test_login_callback_cookie_and_replay(self):
        status, headers, _ = self.request("/auth/login")
        self.assertEqual(status, 303)
        query = parse_qs(urlsplit(headers["Location"]).query)
        state = query["state"][0]
        browser_cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.provider.transaction = self.auth.pending[state]
        path = "/auth/callback?state=" + state + "&code=one-use-test-code"
        status, headers, _ = self.request(path, browser_cookie)
        self.assertEqual(status, 303)
        cookies = headers.get_all("Set-Cookie")
        self.assertTrue(any("Secure; HttpOnly; SameSite=Lax" in item for item in cookies))
        session_cookie = next(item.split(";", 1)[0] for item in cookies if item.startswith(SESSION_COOKIE))
        payload = json.loads(self.request("/auth/session", session_cookie)[2])
        self.assertTrue(payload["authenticated"])
        self.assertNotIn("access_token", payload)
        self.assertEqual(self.request(path, browser_cookie)[0], 403)

    def test_logout_origin_csrf_and_replay(self):
        sid, session, cookie = self.make_session()
        self.assertEqual(self.request("/auth/logout", cookie, {"csrf": session["csrf"]}, "https://attacker.test")[0], 403)
        self.assertEqual(self.request("/auth/logout", cookie, {"csrf": "wrong"}, "https://localhost:8082")[0], 403)
        self.assertIsNotNone(self.auth.session(sid))
        self.assertEqual(self.request("/auth/logout", cookie, {"csrf": session["csrf"]}, "https://localhost:8082")[0], 200)
        self.assertEqual(self.request("/patients/demo-patient-002/summary", cookie)[0], 401)

    def test_authenticated_summary_receives_token(self):
        sid, session, cookie = self.make_session()
        seen = []
        def fake_summary(patient):
            seen.append(auth_fhir.ACCESS_TOKEN.get())
            return {"supported_record_types": ["Patient", "Observation", "Appointment"], "patient": {"id": patient}}
        with patch.object(document_viewer_server, "summary", fake_summary), patch.object(document_viewer_server, "search", return_value=[]):
            status, _, _ = self.request("/patients/demo-patient-002/summary", cookie)
        self.assertEqual(status, 200)
        self.assertEqual(seen, [session["access_token"]])
        self.assertIsNone(auth_fhir.ACCESS_TOKEN.get())

    def test_expired_session_blocks_documents(self):
        sid, session, cookie = self.make_session()
        session["expires"] = time.time() - 1
        self.assertEqual(self.request("/patients/fixture-v2-p02/documents/doc-fixture-v2-p02-pdf", cookie)[0], 401)

    def test_wrong_patient_document_blocked(self):
        _, _, cookie = self.make_session()
        with patch.object(document_viewer_server.subprocess, "run") as s3:
            self.assertEqual(self.request("/patients/demo-patient-002/documents/doc-fixture-v2-p02-pdf", cookie)[0], 403)
            s3.assert_not_called()

    def test_authorized_documents_and_hash_failure(self):
        _, session, cookie = self.make_session()
        config = json.loads((Path(__file__).parent / "spec/v2/document-storage.json").read_text())
        for document in config["documents"]:
            with self.subTest(content_type=document["content_type"]):
                content = b"synthetic-test-document"
                document["size_bytes"] = len(content)
                document["sha256"] = hashlib.sha256(content).hexdigest()
                reference = {"status": "current", "subject": {"reference": "Patient/" + config["patient_id"]},
                             "content": [{"attachment": {
                                 "url": "https://" + config["bucket"] + ".s3." + config["region"] + ".amazonaws.com/" + document["key"],
                                 "contentType": document["content_type"], "size": len(content)
                             }}]}
                seen = []
                def read_reference(url):
                    seen.append(auth_fhir.ACCESS_TOKEN.get())
                    return reference
                def download(args, **kwargs):
                    Path(args[-1]).write_bytes(content)
                    return type("Completed", (), {"returncode": 0})()
                path = "/patients/" + config["patient_id"] + "/documents/" + document["document_reference_id"]
                with patch.object(document_viewer_server, "configuration", return_value=config), \
                     patch.object(document_viewer_server, "get_json", side_effect=read_reference), \
                     patch.object(document_viewer_server.shutil, "which", return_value="aws"), \
                     patch.object(document_viewer_server.subprocess, "run", side_effect=download):
                    status, headers, body = self.request(path, cookie)
                    self.assertEqual(status, 200)
                    self.assertEqual(body, content)
                    self.assertEqual(headers["Content-Type"], document["content_type"])
                    document["sha256"] = "0" * 64
                    self.assertEqual(self.request(path, cookie)[0], 502)
                self.assertEqual(seen, [session["access_token"], session["access_token"]])

    def test_fhir_denial_prevents_s3_access(self):
        _, _, cookie = self.make_session()
        with patch.object(document_viewer_server, "get_json", side_effect=HTTPError("local", 403, "Forbidden", {}, None)), \
             patch.object(document_viewer_server.subprocess, "run") as s3:
            status, _, _ = self.request("/patients/fixture-v2-p02/documents/doc-fixture-v2-p02-pdf", cookie)
            self.assertEqual(status, 502)
            s3.assert_not_called()

    def test_local_mode_defers_documents(self):
        _, _, cookie = self.make_session()
        with patch.object(document_viewer_server, "local_mode", return_value=True), \
             patch.object(document_viewer_server.subprocess, "run") as s3:
            status, _, body = self.request("/patients/fixture-v2-p02/documents/doc-fixture-v2-p02-pdf", cookie)
            self.assertEqual(status, 503)
            self.assertEqual(json.loads(body)["error"], "documents_deferred_to_aws_phase")
            s3.assert_not_called()

if __name__ == "__main__":
    unittest.main()
