"""Exclusion rules (Req 7.3, 14.2), the future-risk case (Req 14.11), and the site-fact builders."""
from dataclasses import replace

import pytest

import rotation_fixtures as rf
from app.rotation import rules
from app.rotation.site_facts import Fact, SiteFacts, build_today, frost_months, parse_slope_high

CROPS = rf.crops()


def soil(value):
    return Fact(value, "", "USDA SSURGO (map-unit average)", 250, "current survey")


def climate(value, units=""):
    return Fact(value, units, "NASA POWER", 50000, "2016-2025")


BASE = SiteFacts(
    hydro_group=soil("B"), drainage=soil("Well drained"), flooding=soil("none"), ponding=soil("none"),
    rain_total=climate(900, "mm/year"), hot_days=climate(40, "days/year"),
    heat_months=(7,), frost_months=(12, 1, 2), frost_days=climate(15, "days/year"),
)


# ---- wet soil ----

def test_wet_soil_fires_for_occasional_flooding():
    e = rules.wet_soil(CROPS["cowpea"], replace(BASE, flooding=soil("occasional")))
    assert e["rule"] == "wet_soil" and "floods occasionally" in e["text"]
    assert e["evidence"][0]["source"].startswith("USDA SSURGO")


def test_wet_soil_fires_for_ponding_and_poor_drainage():
    assert rules.wet_soil(CROPS["cotton"], replace(BASE, ponding=soil("frequent")))
    assert rules.wet_soil(CROPS["cotton"], replace(BASE, drainage=soil("Somewhat poorly drained")))


def test_wet_soil_ignores_rare_flooding_and_tolerant_crops():
    assert rules.wet_soil(CROPS["cowpea"], replace(BASE, flooding=soil("rare"))) is None
    assert rules.wet_soil(CROPS["annual_ryegrass"], replace(BASE, flooding=soil("frequent"))) is None


def test_hydrologic_group_d_alone_is_not_an_exclusion():
    assert rules.wet_soil(CROPS["cotton"], replace(BASE, hydro_group=soil("D"))) is None


# ---- heat, frost, water ----

def test_heat_fires_when_a_heat_sensitive_crop_grows_in_a_heat_month():
    assert rules.heat(CROPS["forage_oats"], replace(BASE, heat_months=(4, 7))) is not None   # oats grow in April
    assert rules.heat(CROPS["forage_oats"], BASE) is None                                   # July only
    assert rules.heat(CROPS["sorghum_sudangrass"], replace(BASE, heat_months=(6, 7, 8))) is None  # heat tolerant


def test_frost_fires_when_a_frost_sensitive_crop_grows_in_the_frost_season():
    e = rules.frost(CROPS["corn"], replace(BASE, frost_months=(12, 1, 2, 3)))
    assert e["rule"] == "frost" and "Mar" in e["text"]
    assert rules.frost(CROPS["corn"], BASE) is None
    assert rules.frost(CROPS["hairy_vetch"], replace(BASE, frost_months=(11, 12, 1, 2, 3))) is None


def test_water_fires_only_without_irrigation_and_below_the_limit():
    dry = replace(BASE, rain_total=climate(700, "mm/year"))
    e = rules.water(CROPS["corn"], dry, irrigation=False)
    assert e["rule"] == "water" and "800" in e["text"] and "700" in e["text"]
    assert rules.water(CROPS["corn"], dry, irrigation=True) is None
    assert rules.water(CROPS["corn"], BASE, irrigation=False) is None          # 900 mm is enough
    assert rules.water(CROPS["grain_sorghum"], dry, irrigation=False) is None  # medium water need


def test_crop_fine_today_but_not_in_the_outlook_is_a_future_risk():
    today = replace(BASE, rain_total=climate(820, "mm/year"))
    outlook = replace(BASE, period="outlook", rain_total=Fact(780, "mm/year", "Open-Meteo Climate API", 10000, "2030-2049"))
    result = rules.evaluate(CROPS, today, outlook, irrigation=False)
    assert "corn" not in result["excluded"]
    assert [e["rule"] for e in result["future"]["corn"]] == ["water"]
    assert result["future"]["corn"][0]["period"] == "outlook"


def test_webberwood_exclusions():
    today, outlook, _, _ = rf.webberwood()
    result = rules.evaluate(CROPS, today, outlook, irrigation=False)
    assert {k: [e["rule"] for e in v] for k, v in result["excluded"].items()} == {
        "corn": ["water"], "cotton": ["wet_soil"], "cowpea": ["wet_soil"],
        "crimson_clover": ["wet_soil"], "sunn_hemp": ["wet_soil"],
    }


# ---- site-fact builders ----

@pytest.mark.parametrize("text,value", [("0 to 1", 1.0), ("8 to 20", 20.0), ("3", 3.0), ("", None), (None, None)])
def test_parse_slope_high(text, value):
    assert parse_slope_high(text) == value


def test_frost_months_span_the_new_year():
    assert frost_months(342, 50) == (1, 2, 12)        # Dec 8 to Feb 19
    assert frost_months(300, 100) == (1, 2, 3, 4, 10, 11, 12)
    assert frost_months(None, 50) == ()


def test_webberwood_today_facts():
    today, outlook, _, _ = rf.webberwood()
    assert today.hot_days.value == pytest.approx(90.8) and today.hot_days.period == "2016-2025"
    assert today.heat_months == (6, 7, 8) and today.frost_months == (1, 2, 12)
    assert today.wettest_month.value == 5 and today.rain_total.value == pytest.approx(771, abs=1)
    assert today.hydro_group.value == "D" and today.flooding.value == "occasional"
    assert today.slope_high.value == 1.0 and today.k_factor.value == 0.24
    assert today.missing_sources == ()


def test_webberwood_outlook_facts_add_september_to_the_heat_months():
    _, outlook, _, _ = rf.webberwood()
    assert outlook.period == "outlook"
    assert outlook.hot_days.value == pytest.approx(70.2 + 28.2, abs=0.2)
    assert outlook.heat_months == (6, 7, 8, 9)
    assert outlook.hydro_group.value == "D"  # soil does not change


def test_missing_sources_are_listed():
    sources = rf.farm_sources()
    sources["ssurgo"] = {"status": "unavailable", "source": "USDA SSURGO", "reason": "down"}
    today = build_today(sources, None, None)
    assert set(today.missing_sources) == {"USDA SSURGO soil", "USDA SSURGO soil profile", "NASA POWER daily climate since 1981"}
    assert today.hydro_group is None
