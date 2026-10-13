"""HTTP access to the secured Firely server: an allow-listed base URL and complete pagination."""
import json
import os
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE = os.environ.get("FHIR_SECURED_URL", "http://localhost:8081").rstrip("/")
_TRUSTED = urlsplit(BASE)
MAX_PAGES = 1000


def allowed(url):
    parsed = urlsplit(url)
    return (
        parsed.scheme == _TRUSTED.scheme
        and parsed.netloc == _TRUSTED.netloc
        and not parsed.username
        and not parsed.password
    )


class LocalRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed(newurl):
            raise RuntimeError("Redirect outside local Firely blocked")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


opener = build_opener(LocalRedirects())


def get_json(url):
    if not allowed(url):
        raise RuntimeError("Request outside local Firely blocked")
    request = Request(url, headers={"Accept": "application/fhir+json"})
    with opener.open(request, timeout=60) as response:
        return json.load(response)


def paginate(path, resource_type, fetch):
    """Follow every next link of a FHIR search. A partial result is never returned."""
    url = BASE + "/" + path
    visited, records = set(), {}
    while url:
        if url in visited or len(visited) >= MAX_PAGES:
            raise RuntimeError("Repeated or excessive pagination")
        visited.add(url)
        bundle = fetch(url)
        if bundle.get("resourceType") != "Bundle" or bundle.get("type") != "searchset":
            raise RuntimeError("Invalid search response")
        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "OperationOutcome":
                raise RuntimeError("Search returned an OperationOutcome; inspect before assessing")
            if resource.get("resourceType") == resource_type:
                records[resource["id"]] = resource
        links = [link["url"] for link in bundle.get("link", []) if link.get("relation") == "next"]
        if len(links) > 1:
            raise RuntimeError("Ambiguous pagination links")
        url = urljoin(url, links[0]) if links else None
    return list(records.values())


def search(path, resource_type):
    return paginate(path, resource_type, get_json)
