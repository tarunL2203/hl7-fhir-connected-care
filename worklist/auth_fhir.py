"""FHIR reads using the current viewer request's verified access token."""
import json
from contextvars import ContextVar
from urllib.request import Request, build_opener
from fhir_client import BASE, allowed, LocalRedirects, paginate

__all__ = ["ACCESS_TOKEN", "BASE", "get_json", "search"]

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
    return paginate(path, resource_type, get_json)
