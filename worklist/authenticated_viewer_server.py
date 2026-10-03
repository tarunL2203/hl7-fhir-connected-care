"""Run this HTTPS entry point instead of the original HTTP document viewer."""
import json
import ssl
from http.cookies import SimpleCookie, CookieError
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from auth_fhir import ACCESS_TOKEN
from document_viewer_server import DocumentHandler
from summary_api import ROOT
from viewer_auth import AuthService, Provider, AuthError, ORIGIN

SESSION_COOKIE = "__Host-firely_viewer"
LOGIN_COOKIE = "__Host-firely_login"
LOGIN_PAGE = b'''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign in | Visit Information Worklist</title></head>
<body style="font:18px system-ui;max-width:650px;margin:80px auto;padding:20px">
<h1>Visit Information Worklist</h1><p>Sign in to review synthetic patient records and documents.</p>
<p><a href="/auth/login">Sign in with Firely</a></p>
<p>Use the Demo Reviewer account. Viewer sessions last up to 15 minutes.</p>
<p>This viewer's sign-out ends its session. Firely may retain its separate sign-in session.</p>
</body></html>'''

class AuthenticatedHandler(DocumentHandler):
    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        super().end_headers()

    def log_message(self, *args):
        # Never log authorization codes, states, cookies, or token responses.
        print("Viewer:", self.command, urlsplit(self.path).path, flush=True)

    def cookies(self):
        jar = SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie", ""))
        except CookieError:
            return {}
        return {key: value.value for key, value in jar.items()}

    def cookie(self, name, value, max_age):
        self.send_header("Set-Cookie", f"{name}={value}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age={max_age}")

    def redirect(self, location, cookie=None):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        if cookie:
            self.cookie(*cookie)
        self.end_headers()

    def current_session(self):
        return self.server.auth.session(self.cookies().get(SESSION_COOKIE))

    def valid_host(self):
        return self.headers.get("Host") in ("localhost:8082", "127.0.0.1:8082")

    def do_GET(self):
        if not self.valid_host():
            self.send_json(400, {"error": "unexpected_host"})
            return
        path = urlsplit(self.path).path
        auth = self.server.auth
        if path == "/health":
            self.send_json(200, {"status": "running", "authentication": "required"})
            return
        if path == "/auth/session":
            session = self.current_session()
            self.send_json(200, {
                "authenticated": bool(session),
                **({"name": session["display_name"], "expires_at": session["expires"],
                    "csrf": session["csrf"]} if session else {})
            })
            return
        if path == "/auth/login":
            try:
                location, browser = auth.begin()
                self.redirect(location, (LOGIN_COOKIE, browser, 300))
            except AuthError as error:
                self.send_json(503, {"error": str(error)})
            return
        if path == "/auth/callback":
            try:
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if len(query.get("state", [])) != 1:
                    raise AuthError("invalid_login_callback")
                pending = auth.consume(query["state"][0], self.cookies().get(LOGIN_COOKIE))
                if "error" in query:
                    raise AuthError("login_not_authorized")
                if len(query.get("code", [])) != 1 or not query["code"][0]:
                    raise AuthError("missing_authorization_code")
                session_id, session = auth.complete(pending, query["code"][0])
                old = self.cookies().get(SESSION_COOKIE)
                with auth.lock:
                    auth.sessions.pop(old, None)
                self.send_response(303)
                self.send_header("Location", "/")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.cookie(SESSION_COOKIE, session_id, 900)
                self.cookie(LOGIN_COOKIE, "", 0)
                self.end_headers()
            except AuthError as error:
                self.send_json(403, {"error": str(error), "message": "Sign in again using the Demo Reviewer account."})
            except Exception:
                self.send_json(502, {"error": "login_not_completed"})
            return
        session = self.current_session()
        if not session:
            if path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(LOGIN_PAGE)))
                self.end_headers()
                self.wfile.write(LOGIN_PAGE)
            else:
                self.send_json(401, {"error": "login_required", "assessment_completed": False})
            return
        context = ACCESS_TOKEN.set(session["access_token"])
        try:
            super().do_GET()
        finally:
            ACCESS_TOKEN.reset(context)

    def do_POST(self):
        if not self.valid_host() or self.headers.get("Origin") != ORIGIN:
            self.send_json(403, {"error": "invalid_request_origin"})
            return
        if urlsplit(self.path).path != "/auth/logout":
            self.send_json(405, {"error": "read_only_viewer"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 1024:
                raise AuthError("invalid_logout_request")
            body = json.loads(self.rfile.read(size))
            self.server.auth.logout(self.cookies().get(SESSION_COOKIE), body.get("csrf"))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            data = b'{"signed_out":true}'
            self.send_header("Content-Length", str(len(data)))
            self.cookie(SESSION_COOKIE, "", 0)
            self.cookie(LOGIN_COOKIE, "", 0)
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_json(403, {"error": "invalid_logout_request"})

def create_server():
    """Build the same verified HTTPS server for normal use and live verification."""
    certs = Path.home() / "firely-learning/auth/certs"
    try:
        auth = AuthService(Provider(certs / "local-rootCA.crt"))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(certs / "localhost.pem", certs / "localhost-key.pem")
        server = ThreadingHTTPServer(("127.0.0.1", 8082), AuthenticatedHandler)
        server.auth = auth
        server.socket = context.wrap_socket(server.socket, server_side=True)
    except AuthError as error:
        raise SystemExit("Viewer startup stopped: " + str(error))
    return server

def main():
    server = create_server()
    auth = server.auth
    print("Authenticated viewer: " + ORIGIN, flush=True)
    print("Keep this terminal open. Ctrl+C stops the viewer.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        with auth.lock:
            auth.sessions.clear()
            auth.pending.clear()

if __name__ == "__main__":
    main()
