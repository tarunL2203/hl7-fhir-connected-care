"""Read-only preflight/smoke checks and an opt-in real-login verification runner.

Never print or persist credentials, cookies, tokens, callback URLs or raw errors.
The reviewer command owns a normal viewer server; it does not mint sessions.
"""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
import ssl

ROOT = Path(__file__).resolve().parent.parent
VIEWER = "https://localhost:8082"
FHIR = "http://localhost:8081"
AUTH = "https://localhost:5001"
CONTAINERS = ("firely-learning-mailpit", "firely-learning-auth", "firely-learning-aws")


class CheckError(Exception):
    pass


def command(args):
    try:
        result = subprocess.run(args, capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        raise CheckError("command_unavailable_or_timed_out") from None
    if result.returncode:
        error = result.stderr.decode(errors="replace").lower()
        if any(x in error for x in ("expired", "sso session", "error loading sso")):
            raise CheckError("aws_login_required: aws login --profile firely-learning")
        if "accessdenied" in error or "unauthorizedoperation" in error:
            raise CheckError("aws_read_permission_denied")
        if "docker" == args[0]:
            raise CheckError("docker_unavailable_or_permission_denied")
        raise CheckError("command_failed")
    return result.stdout


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request(path, cookie=None, body=None, origin=None):
    url = path if path.startswith((FHIR + "/", AUTH + "/")) else VIEWER + path
    ctx = ssl.create_default_context(cafile=str(ROOT / "auth/certs/local-rootCA.crt"))
    opener = build_opener(HTTPSHandler(context=ctx), NoRedirects())
    headers = {}
    if cookie:
        headers["Cookie"] = "__Host-firely_viewer=" + cookie
    if origin:
        headers["Origin"] = origin
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    try:
        response = opener.open(Request(url, headers=headers, data=data), timeout=70)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.headers.get("Content-Type", ""), response.read(10 * 1024 * 1024)


def sql_settings(connection):
    values = {}
    for field in connection.split(";"):
        key, sep, value = field.partition("=")
        if sep:
            values[re.sub(r"\s+", "", key).lower()] = value.strip()
    endpoint = values.get("server", values.get("datasource", "")).removeprefix("tcp:")
    host, _, port = endpoint.partition(",")
    if not host or not values.get("encrypt", "").lower() in ("true", "mandatory", "strict"):
        raise CheckError("sql_encryption_not_enabled")
    if values.get("trustservercertificate", "").lower() != "false":
        raise CheckError("sql_certificate_validation_not_confirmed")
    return host, int(port or 1433)


def permits_ipv4(permission, address, port):
    if permission.get("IpProtocol") == "-1" or (
        permission.get("IpProtocol") == "tcp"
        and permission.get("FromPort", 65536) <= port <= permission.get("ToPort", -1)
    ):
        return any(ipaddress.ip_address(address) in ipaddress.ip_network(x["CidrIp"])
                   for x in permission.get("IpRanges", []))
    return False


class Checks:
    def __init__(self, mode):
        self.mode, self.results = mode, []

    def run(self, name, fn):
        try:
            detail = fn()
            result = {"check": name, "passed": True, "detail": detail}
        except Exception as error:
            # Only our fixed safe errors may reach output; raw exceptions can hold secrets.
            reason = str(error) if isinstance(error, CheckError) else type(error).__name__
            result = {"check": name, "passed": False, "reason": reason}
        self.results.append(result)
        print(("PASS " if result["passed"] else "FAIL ") + name, flush=True)
        if not result["passed"]:
            print("  " + result["reason"], flush=True)
        return result["passed"]

    def save(self):
        path = ROOT / "worklist/evidence" / (
            "repeatable-" + self.mode + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
        path.write_text(json.dumps({"mode": self.mode, "live": True,
            "at": datetime.now(timezone.utc).isoformat(),
            "passed": all(x["passed"] for x in self.results), "checks": self.results}, indent=2) + "\n")
        print("Evidence: " + str(path), flush=True)
        return all(x["passed"] for x in self.results)


def require(condition, code):
    if not condition:
        raise CheckError(code)


def preflight(checks):
    config = json.loads((ROOT / "worklist/spec/v2/document-storage.json").read_text())
    def aws(*args):
        return json.loads(command(["aws", *args, "--profile", config["aws_profile"],
            "--region", config["region"], "--output", "json", "--no-cli-pager"]))
    state = {}
    def docker():
        rows = json.loads(command(["docker", "inspect", *CONTAINERS]))
        state["containers"] = {x["Name"].lstrip("/"): x for x in rows}
        return {name: x["State"]["Status"] for name, x in state["containers"].items()}
    checks.run("existing Docker containers", docker)
    checks.run("AWS login session", lambda: bool(aws("sts", "get-caller-identity")))
    def ip():
        samples = [str(ipaddress.IPv4Address(command(["curl", "-4", "--silent", "--show-error",
            "--max-time", "10", "https://checkip.amazonaws.com"]).decode().strip())) for _ in range(2)]
        require(samples[0] == samples[1], "ipv4_egress_changed_during_check")
        state["ip"] = samples[0]
        return samples[0] + "/32"
    checks.run("stable native IPv4 egress", ip)
    def database():
        d = aws("rds", "describe-db-instances", "--db-instance-identifier", "firely-learning-db")["DBInstances"][0]
        state["rds"] = d
        require(d["DBInstanceStatus"] == "available", "rds_not_available")
        require(d["PubliclyAccessible"], "rds_not_publicly_accessible_from_this_demo")
        return {"status": d["DBInstanceStatus"], "public": d["PubliclyAccessible"]}
    checks.run("RDS availability", database)
    def rules():
        require("rds" in state and "ip" in state, "prerequisite_unavailable")
        ids = [g["VpcSecurityGroupId"] for g in state["rds"]["VpcSecurityGroups"]]
        groups = aws("ec2", "describe-security-groups", "--group-ids", *ids)["SecurityGroups"]
        require(any(permits_ipv4(p, state["ip"], 1433) for g in groups for p in g["IpPermissions"]),
                "current_ipv4_not_allowed_for_tcp_1433; review_single_IP_rule_before_starting")
        return {"current_ipv4_allowed": True, "groups": ids, "aws_changes": False}
    checks.run("current IPv4 security-group access", rules)
    def tcp():
        require("containers" in state and "rds" in state, "prerequisite_unavailable")
        env = dict(v.split("=", 1) for v in state["containers"]["firely-learning-aws"]["Config"]["Env"])
        host, port = sql_settings(env["VONK_SqlDbOptions__ConnectionString"])
        require(host == state["rds"]["Endpoint"]["Address"] and port == state["rds"]["Endpoint"]["Port"], "sql_endpoint_mismatch")
        address = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)[0][4]
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(8)
            sock.connect(address)
        return {"ipv4_tcp": "reachable", "encrypt": True, "trust_server_certificate": False}
    checks.run("configured SQL TLS settings and IPv4 TCP", tcp)


def expect_http(path, status, cookie=None, body=None, origin=None):
    actual, mime, content = request(path, cookie, body, origin)
    require(actual == status, "unexpected_http_status_" + str(actual))
    return mime, content


def smoke(checks):
    for label, path, expected in [
        ("FHIR readiness", FHIR + "/$readiness", 200),
        ("FHIR anonymous Patient denial", FHIR + "/Patient/demo-patient-002", 401),
        ("viewer health", "/health", 200),
        ("anonymous summary denial", "/patients/demo-patient-002/summary", 401),
        ("anonymous document denial", "/patients/fixture-v2-p02/documents/doc-fixture-v2-p02-pdf", 401),
    ]:
        def check(p=path, status=expected):
            expect_http(p, status)
            return {"http": status}
        checks.run(label, check)
    def discovery():
        _, data = expect_http(AUTH + "/.well-known/openid-configuration", 200)
        require(json.loads(data)["issuer"] == AUTH, "issuer_mismatch")
        return {"trusted_tls": True, "issuer_matches": True}
    checks.run("Auth TLS and discovery issuer", discovery)


def reviewer(checks, timeout, keep_serving):
    from authenticated_viewer_server import create_server
    db = ROOT / "worklist/data/worklist.sqlite"
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    server = create_server()  # Real AuthService, real TLS, unchanged application handler.
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        smoke(checks)
        print("Open https://localhost:8082/auth/login and sign in as Demo Reviewer.", flush=True)
        print("Waiting for a real verified login. Tests will log this viewer session out.", flush=True)
        deadline = time.monotonic() + timeout
        sid = session = None
        while time.monotonic() < deadline:
            with server.auth.lock:
                server.auth.prune()
                entries = list(server.auth.sessions.items())
            if entries:
                sid, session = entries[0]
                entries.clear()
                break
            time.sleep(0.2)
        require(sid is not None, "real_reviewer_login_timeout")
        for patient in ["demo-patient-002", "fixture-v2-p02"]:
            def summary(pid=patient):
                _, body = expect_http("/patients/" + pid + "/summary", 200, sid)
                data = json.loads(body)
                require(data["patient"]["id"] == pid and data["observations"] and data["appointments"], "live_records_incomplete")
                require(data["assessments"] and all(a["outcome"] == "information_complete" for a in data["assessments"]), "fixture_assessment_changed")
                if pid == "fixture-v2-p02":
                    require(any(w["status"] == "resolved" and [h["action"] for h in w["history"]] ==
                                ["created", "in_review", "resolved"] for w in data["work_items"]), "resolution_history_changed")
                else:
                    require(not data["documents"], "ravi_empty_document_fixture_changed")
                return {"patient_id": pid, "observations": len(data["observations"]), "appointments": len(data["appointments"]),
                        "assessments": [a["outcome"] for a in data["assessments"]],
                        "worklist_statuses": [w["status"] for w in data["work_items"]]}
            checks.run("authenticated summary " + patient, summary)
        cfg = json.loads((ROOT / "worklist/spec/v2/document-storage.json").read_text())
        for document in cfg["documents"]:
            def download(doc=document):
                mime, data = expect_http("/patients/" + cfg["patient_id"] + "/documents/" + doc["document_reference_id"], 200, sid)
                require(mime == doc["content_type"] and len(data) == doc["size_bytes"]
                        and hashlib.sha256(data).hexdigest() == doc["sha256"], "document_integrity_mismatch")
                return {"bytes": len(data), "sha256_matches": True}
            checks.run("authenticated document " + document["document_reference_id"], download)
        for name, path in [
            ("wrong-patient document denied", "/patients/demo-patient-002/documents/doc-fixture-v2-p02-pdf"),
            ("unregistered document denied", "/patients/fixture-v2-p02/documents/verification-unregistered"),
        ]:
            def denied(p=path):
                _, body = expect_http(p, 403, sid)
                require(json.loads(body)["error"] == "document_patient_or_registry_mismatch", "unexpected_denial_reason")
                return {"http": 403}
            checks.run(name, denied)
        def invalid_logout():
            expect_http("/auth/logout", 403, sid, {"csrf": "deliberately-invalid"}, VIEWER)
            expect_http("/auth/logout", 403, sid, {"csrf": session["csrf"]}, "https://example.invalid")
            _, data = expect_http("/auth/session", 200, sid)
            require(json.loads(data)["authenticated"], "invalid_logout_ended_session")
            return {"invalid_csrf_denied": True, "wrong_origin_denied": True, "session_retained": True}
        checks.run("logout CSRF enforcement", invalid_logout)
        def logout_and_replay():
            expect_http("/auth/logout", 200, sid, {"csrf": session["csrf"]}, VIEWER)
            # Deliberately retain the original cookie in memory and replay it over HTTPS.
            expect_http("/patients/demo-patient-002/summary", 401, sid)
            expect_http("/patients/fixture-v2-p02/documents/doc-fixture-v2-p02-pdf", 401, sid)
            _, data = expect_http("/auth/session", 200, sid)
            require(json.loads(data)["authenticated"] is False, "old_cookie_still_authenticated")
            expect_http("/auth/logout", 403, sid, {"csrf": session["csrf"]}, VIEWER)
            return {"logout": 200, "old_cookie_summary": 401, "old_cookie_document": 401,
                    "old_cookie_authenticated": False, "logout_replay": 403}
        checks.run("real logout and old-session-cookie replay", logout_and_replay)
        checks.run("worklist preserved", lambda: require(hashlib.sha256(db.read_bytes()).hexdigest() == before, "worklist_changed"))
        sid = session = None
        passed = checks.save()
        if keep_serving:
            print("Verification finished. Normal viewer remains available; Ctrl+C stops it.", flush=True)
            while True:
                time.sleep(1)
        return passed
    finally:
        server.shutdown()
        server.server_close()
        with server.auth.lock:
            server.auth.sessions.clear()
            server.auth.pending.clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["preflight", "smoke", "reviewer", "start"])
    parser.add_argument("--login-timeout", type=int, default=600)
    parser.add_argument("--keep-serving", action="store_true")
    args = parser.parse_args()
    checks = Checks(args.mode)
    try:
        if args.mode == "reviewer":
            return 0 if reviewer(checks, args.login_timeout, args.keep_serving) else 1
        if args.mode in ("preflight", "start"):
            preflight(checks)
        if args.mode == "smoke":
            smoke(checks)
        passed = checks.save()
        if args.mode == "start" and passed:
            command(["docker", "start", *CONTAINERS])
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                try:
                    expect_http(FHIR + "/$readiness", 200)
                    expect_http(AUTH + "/.well-known/openid-configuration", 200)
                    break
                except Exception:
                    time.sleep(2)
            else:
                raise CheckError("services_not_ready_after_90_seconds")
            try:
                _, content = expect_http("/health", 200)
                require(json.loads(content).get("authentication") == "required", "unexpected_viewer_on_port_8082")
                print("Existing authenticated viewer ready at " + VIEWER)
            except (ConnectionError, OSError):
                os.execv(sys.executable, [sys.executable, "-B", str(ROOT / "worklist/authenticated_viewer_server.py")])
        return 0 if passed else 1
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        checks.run("runner completion", lambda: (_ for _ in ()).throw(error))
        checks.save()
        return 1


if __name__ == "__main__":
    sys.exit(main())
