"""Shared helpers for talking to upstream data sources.

Every upstream call is limited to 10 seconds in total. httpx's own timeout
applies per read, so we also wrap each call in asyncio.wait_for.
"""
import asyncio

import httpx

UPSTREAM_TIMEOUT = 10.0  # seconds, hard limit for one upstream request


class SourceUnavailable(Exception):
    """Raised with a short, farmer-readable reason when a source cannot give data."""


def describe_failure(source_name: str, exc: BaseException) -> str:
    """A short plain-language reason for a failure. Never includes URLs or response bodies."""
    if isinstance(exc, SourceUnavailable):
        return str(exc)
    if isinstance(exc, (asyncio.TimeoutError, httpx.TimeoutException)):
        return f"{source_name} did not respond in time"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"{source_name} returned an error ({exc.response.status_code})"
    if isinstance(exc, httpx.HTTPError):
        return f"{source_name} could not be reached"
    return f"{source_name} sent data we could not read"


def make_client() -> httpx.AsyncClient:
    """The real HTTP client used in production. Tests pass a MockTransport client instead."""
    return httpx.AsyncClient(timeout=httpx.Timeout(UPSTREAM_TIMEOUT), follow_redirects=True)


async def get_json(client: httpx.AsyncClient, url: str, params: dict | None = None, timeout: float | None = None):
    """GET a URL and return parsed JSON. Raises on timeout, HTTP error, or bad JSON.

    timeout: only for offline scripts that call slow services (NDVI); page requests keep 10 s.
    """
    if timeout is None:
        r = await asyncio.wait_for(client.get(url, params=params), UPSTREAM_TIMEOUT)
    else:
        r = await asyncio.wait_for(client.get(url, params=params, timeout=timeout), timeout)
    r.raise_for_status()
    return r.json()


async def get_text(client: httpx.AsyncClient, url: str, params: dict | None = None) -> str:
    """GET a URL and return the body as text. Raises on timeout or HTTP error."""
    r = await asyncio.wait_for(client.get(url, params=params), UPSTREAM_TIMEOUT)
    r.raise_for_status()
    return r.text


async def post_json(client: httpx.AsyncClient, url: str, body: dict):
    """POST a JSON body and return parsed JSON. Raises on timeout, HTTP error, or bad JSON."""
    r = await asyncio.wait_for(client.post(url, json=body), UPSTREAM_TIMEOUT)
    r.raise_for_status()
    return r.json()
