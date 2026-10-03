"""FHIR reads using the current viewer request's verified access token."""
import json
from contextvars import ContextVar
from urllib.parse import urljoin
from urllib.request import Request, build_opener
from assess_ravi import BASE, allowed, LocalRedirects

ACCESS_TOKEN = ContextVar("viewer_access_token", default=None)
opener = build_opener(LocalRedirects())

def get_json(url):
    token = ACCESS_TOKEN.get()
    if not token:
        raise RuntimeError("Authenticated FHIR context required")
    if not allowed(url):
        raise RuntimeError("Request outside local Firely blocked")
    request = Request(url, headers={
        "Accept": "application/fhir+json",
        "Authorization": "Bearer " + token
    })
    with opener.open(request, timeout=60) as response:
        return json.load(response)

def search(path, resource_type):
    url = BASE + "/" + path
    visited, records = set(), {}
    while url:
        if url in visited or len(visited) >= 1000:
            raise RuntimeError("Repeated or excessive pagination")
        visited.add(url)
        bundle = get_json(url)
        if bundle.get("resourceType") != "Bundle" or bundle.get("type") != "searchset":
            raise RuntimeError("Invalid search response")
        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "OperationOutcome":
                raise RuntimeError("Search returned an OperationOutcome")
            if resource.get("resourceType") == resource_type:
                records[resource["id"]] = resource
        links = [link["url"] for link in bundle.get("link", [])
                 if link.get("relation") == "next"]
        if len(links) > 1:
            raise RuntimeError("Ambiguous pagination links")
        url = urljoin(url, links[0]) if links else None
    return list(records.values())
