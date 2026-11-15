"""Geocoder tests. Network calls are mocked with httpx.MockTransport."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.geocode import GeocodeError, geocode, is_in_us, parse_coordinates
from app.main import app


def make_client(census_json=None, nominatim_json=None, census_status=200):
    def handler(request: httpx.Request):
        if "census.gov" in request.url.host:
            return httpx.Response(census_status, json=census_json or {})
        return httpx.Response(200, json=nominatim_json if nominatim_json is not None else [])
    return httpx.Client(transport=httpx.MockTransport(handler))


CENSUS_HIT = {"result": {"addressMatches": [{
    "matchedAddress": "100 W MAIN ST, FREDERICKSBURG, TX, 78624",
    "coordinates": {"x": -98.8720, "y": 30.2752},
}]}}


def test_parse_coordinates():
    assert parse_coordinates("30.2752, -98.872") == (30.2752, -98.872)
    assert parse_coordinates("100 Main St") is None
    with pytest.raises(GeocodeError):
        parse_coordinates("95, -98")


def test_coordinates_skip_network():
    # A client that fails on any request proves no call is made.
    def boom(request):
        raise AssertionError("network should not be used")
    client = httpx.Client(transport=httpx.MockTransport(boom))
    r = geocode("30.2752, -98.872", client)
    assert r["source"] == "Entered coordinates"


def test_census_match():
    r = geocode("100 W Main St, Fredericksburg, TX", make_client(census_json=CENSUS_HIT))
    assert r["lat"] == 30.2752 and r["lon"] == -98.872
    assert r["source"] == "US Census Geocoder"


def test_falls_back_to_nominatim_when_census_fails():
    client = make_client(census_status=500, nominatim_json=[
        {"lat": "30.27", "lon": "-98.87", "display_name": "Fredericksburg, TX"}])
    assert geocode("Fredericksburg TX", client)["source"] == "OpenStreetMap Nominatim"


def test_not_found():
    with pytest.raises(GeocodeError, match="not found"):
        geocode("zzzz nowhere", make_client(census_json={"result": {"addressMatches": []}}))


def test_non_us_rejected():
    assert not is_in_us(48.8566, 2.3522)  # Paris
    with pytest.raises(GeocodeError, match="outside the US"):
        geocode("48.8566, 2.3522")


def test_endpoint_returns_400_with_message():
    r = TestClient(app).get("/api/geocode", params={"q": "48.8566, 2.3522"})
    assert r.status_code == 400
    assert "outside the US" in r.json()["detail"]
