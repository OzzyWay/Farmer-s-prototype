"""check_location: plain-language errors for bad query parameters."""
import pytest

from app.geocode import GeocodeError, check_location


def test_valid_us_location():
    assert check_location("30.2752", "-98.872") == (30.2752, -98.872)


@pytest.mark.parametrize("lat,lon,fragment", [
    (None, "-98", "required"),
    ("30", None, "required"),
    ("abc", "-98", "numbers"),
    ("", "", "numbers"),
    ("95", "-98", "out of range"),
    ("30", "-200", "out of range"),
    ("48.8566", "2.3522", "outside the US"),
])
def test_bad_locations(lat, lon, fragment):
    with pytest.raises(GeocodeError, match=fragment):
        check_location(lat, lon)
