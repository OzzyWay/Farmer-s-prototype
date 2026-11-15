from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_demo_farms_has_coordinates():
    farms = client.get("/api/demo-farms").json()["farms"]
    assert len(farms) >= 1
    assert -90 <= farms[0]["lat"] <= 90
    assert -180 <= farms[0]["lon"] <= 180


def test_earthdata_token_loaded_without_exposing_it():
    """The token must be readable by the backend. Never print its value."""
    import os

    import pytest

    if not os.getenv("EARTHDATA_TOKEN"):
        pytest.skip("EARTHDATA_TOKEN not set in .env yet (needed for Task 5 only)")
    assert len(os.getenv("EARTHDATA_TOKEN")) > 20
