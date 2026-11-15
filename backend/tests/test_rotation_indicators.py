"""Yearly climate indicators, tested on small hand-made daily series (Req 14.10)."""
from datetime import date, timedelta

import pytest

from app.rotation import indicators as ind


def year_of(year, fn):
    """Daily {date: value} for a whole year; fn(date) gives the value (None = missing)."""
    out, d = {}, date(year, 1, 1)
    while d.year == year:
        v = fn(d)
        if v is not None:
            out[d] = float(v)
        d += timedelta(days=1)
    return out


def flat(year, value):
    return year_of(year, lambda d: value)


def test_from_power_drops_fill_values_and_bad_keys():
    got = ind.from_power({"20240101": 5.0, "20240102": -999, "2024013x": 1.0, "20240103": None})
    assert got == {date(2024, 1, 1): 5.0}


def test_from_lists_drops_missing_values():
    got = ind.from_lists(["2030-01-01", "2030-01-02", "bad"], [1.5, None, 2.0])
    assert got == {date(2030, 1, 1): 1.5}


def test_year_with_more_than_10_percent_missing_is_skipped():
    full = flat(2021, 10)
    sparse = year_of(2022, lambda d: 10 if d.month <= 10 else None)  # Nov-Dec missing (16%)
    assert set(ind.by_year({**full, **sparse})) == {2021}


def test_leap_year_counts_366_days():
    leap = flat(2024, 36)  # every day is hot
    assert len(leap) == 366
    assert ind.yearly_indicators(flat(2024, 10), leap, flat(2024, 2))["hot_days"] == {2024: 366}


def test_hot_days_threshold_is_strictly_above_35():
    tmax = year_of(2021, lambda d: 36 if d.month == 7 else (35 if d.month == 8 else 30))
    assert ind.yearly_indicators(flat(2021, 10), tmax, flat(2021, 2))["hot_days"] == {2021: 31}


def test_warm_nights_and_frost_days():
    tmin = year_of(2021, lambda d: 25 if d.month == 7 else (0 if d.month == 1 and d.day <= 3 else (-2 if d.month == 12 and d.day >= 30 else 10)))
    out = ind.yearly_indicators(tmin, flat(2021, 20), flat(2021, 2))
    assert out["warm_nights"] == {2021: 31}
    assert out["frost_days"] == {2021: 5}  # 0 °C counts as frost


def test_frost_dates_split_at_1_july():
    tmin = year_of(2021, lambda d: -1 if d in (date(2021, 3, 10), date(2021, 6, 30), date(2021, 7, 1), date(2021, 11, 20)) else 10)
    out = ind.yearly_indicators(tmin, flat(2021, 20), flat(2021, 2))
    assert out["last_spring_frost"] == {2021: ind.day_of_year(date(2021, 6, 30))}
    assert out["first_fall_frost"] == {2021: ind.day_of_year(date(2021, 7, 1))}


def test_no_frost_year_has_no_frost_dates():
    out = ind.yearly_indicators(flat(2021, 10), flat(2021, 20), flat(2021, 2))
    assert out["frost_days"] == {2021: 0}
    assert "last_spring_frost" not in out and "first_fall_frost" not in out


def test_day_of_year_ignores_leap_day():
    assert ind.day_of_year(date(2024, 3, 1)) == ind.day_of_year(date(2023, 3, 1)) == 60
    assert ind.day_of_year(date(2024, 2, 29)) == 59
    assert ind.doy_to_month_day(60) == "03-01"


def test_rain_totals_and_growing_season():
    rain = year_of(2021, lambda d: 2 if d.month in (4, 5, 6, 7, 8, 9) else 1)
    out = ind.yearly_indicators(flat(2021, 10), flat(2021, 20), rain)
    growing_days = sum(1 for d in rain if d.month in range(4, 10))
    assert out["rain_growing"] == {2021: 2.0 * growing_days}
    assert out["rain_total"] == {2021: 2.0 * growing_days + 1.0 * (365 - growing_days)}


def test_longest_dry_spell():
    # dry (0 mm) from 10 to 29 June (20 days), and a 5-day dry run in March
    def rain(d):
        if d.month == 6 and 10 <= d.day <= 29:
            return 0
        if d.month == 3 and d.day <= 5:
            return 0.5
        return 3
    out = ind.yearly_indicators(flat(2021, 10), flat(2021, 20), year_of(2021, rain))
    assert out["dry_spell"] == {2021: 20}


def test_dry_spell_is_broken_by_a_missing_day():
    rain = year_of(2021, lambda d: None if d == date(2021, 6, 15) else (0 if d.month == 6 else 3))
    out = ind.yearly_indicators(flat(2021, 10), flat(2021, 20), rain)
    assert out["dry_spell"] == {2021: 15}  # 16-30 June


def test_heavy_rain_days_use_the_local_threshold():
    rain = year_of(2021, lambda d: 60 if d.day == 1 else (5 if d.day % 2 else 0))
    out = ind.yearly_indicators(flat(2021, 10), flat(2021, 20), rain, heavy_threshold=40)
    assert out["heavy_rain_days"] == {2021: 12}


def test_heavy_rain_threshold_is_95th_percentile_of_wet_days():
    # 1981-1990: wet days are 1..100 mm spread evenly, so the 95th percentile is about 95 mm
    rain = {}
    for y in range(1981, 1991):
        rain.update(year_of(y, lambda d: (d.timetuple().tm_yday % 100) + 1 if d.day % 3 == 0 else 0))
    assert ind.heavy_rain_threshold(rain) == pytest.approx(95, abs=2)


def test_water_balance_and_soil_wetness():
    out = ind.yearly_indicators(flat(2021, 10), flat(2021, 20), flat(2021, 3),
                                evap=flat(2021, 2), soil=year_of(2021, lambda d: 0.8 if d.month in range(4, 10) else 0.2))
    assert out["water_balance"] == {2021: 365.0}
    assert out["soil_wetness"] == {2021: 0.8}


def test_optional_inputs_missing_leave_those_indicators_out():
    out = ind.yearly_indicators(flat(2021, 10), flat(2021, 20), flat(2021, 3))
    assert "water_balance" not in out and "soil_wetness" not in out


def test_averages_cv_and_monthly_climate():
    series = {2016: 80, 2017: 90, 2018: 100, 2019: 110, 2020: 120}
    assert ind.average(series, range(2018, 2021)) == 110.0
    assert ind.average(series, [1999]) is None
    assert ind.coefficient_of_variation(series) == pytest.approx(15.8, abs=0.1)
    tmax = {**year_of(2021, lambda d: 37 if d.month == 7 else 25), **year_of(2022, lambda d: 35 if d.month == 7 else 25)}
    rain = {**year_of(2021, lambda d: 4 if d.month == 5 else 1), **year_of(2022, lambda d: 2 if d.month == 5 else 1)}
    m = ind.monthly_climate(tmax, rain, [2021, 2022])
    assert m["avg_high_c"][6] == 36.0 and m["avg_high_c"][0] == 25.0
    assert m["rain_mm"][4] == 93.0  # May: (124 + 62) / 2
