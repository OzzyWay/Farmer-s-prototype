"""Rotation engine: correctness properties 1-7 (design), priorities, findings and confidence.

Uses the real Webberwood inputs plus three made-up sites so the rules are exercised in
different directions: dry West Texas, wet sandy East Texas, and an Iowa corn-soybean farm.
"""
import json
from dataclasses import replace

import pytest

import rotation_fixtures as rf
from app.rotation import templates
from app.rotation.current import infer
from app.rotation.engine import run
from app.rotation.site_facts import Fact, FarmInputs, SiteFacts

CROPS = rf.crops()


def soil(value):
    return Fact(value, "", "USDA SSURGO (map-unit average)", 250, "current survey")


def climate(value, units=""):
    return Fact(value, units, "NASA POWER", 50000, "2016-2025")


DRY_WEST = SiteFacts(
    hot_days=climate(120, "days/year"), frost_days=climate(30, "days/year"), rain_total=climate(380, "mm/year"),
    heat_months=(5, 6, 7, 8, 9), frost_months=(11, 12, 1, 2, 3), wettest_month=climate(9, "month"),
    hydro_group=soil("B"), drainage=soil("Well drained"), flooding=soil("none"), ponding=soil("none"),
    om_pct=soil(0.8), k_factor=soil(0.28), slope_high=soil(3.0), texture_group=soil("sandy loam"),
)
WET_EAST = SiteFacts(
    hot_days=climate(30, "days/year"), frost_days=climate(15, "days/year"), rain_total=climate(1250, "mm/year"),
    heat_months=(), frost_months=(12, 1, 2), wettest_month=climate(5, "month"),
    hydro_group=soil("A/D"), drainage=soil("Poorly drained"), flooding=soil("frequent"), ponding=soil("occasional"),
    om_pct=soil(1.5), k_factor=soil(0.15), slope_high=soil(2.0), texture_group=soil("sand"),
)
IOWA = SiteFacts(
    hot_days=climate(5, "days/year"), frost_days=climate(140, "days/year"), rain_total=climate(900, "mm/year"),
    heat_months=(), frost_months=(11, 12, 1, 2), wettest_month=climate(6, "month"),
    hydro_group=soil("B"), drainage=soil("Moderately well drained"), flooding=soil("none"), ponding=soil("none"),
    om_pct=soil(4.0), k_factor=soil(0.37), slope_high=soil(9.0), texture_group=soil("silt"),
)

PASTURE = infer(rf.cdl_records(*rf.WEBBERWOOD_CDL), CROPS)
CORN_SOY = infer(rf.cdl_records("Corn", "Soybeans") * 4, CROPS)
SORGHUM = infer(rf.cdl_records(*["Sorghum"] * 8), CROPS)
FOREST = infer(rf.cdl_records(*["Deciduous Forest"] * 8), CROPS)


def webberwood_run(inputs=FarmInputs(livestock="yes")):
    today, outlook, current, doc = rf.webberwood()
    return run(today, outlook, CROPS, current, inputs, rf.trends(), doc)


SITES = [
    ("webberwood", None, None),
    ("dry_west", DRY_WEST, SORGHUM),
    ("wet_east", WET_EAST, PASTURE),
    ("iowa", IOWA, CORN_SOY),
]


def site_run(name, facts, current, inputs=FarmInputs(livestock="yes")):
    if name == "webberwood":
        return webberwood_run(inputs)
    return run(facts, None, CROPS, current, inputs)


def alternatives(result):
    return [s for s in result["strategies"] if not s["is_current"]]


# ---- correctness properties ----

@pytest.mark.parametrize("name,facts,current", SITES)
@pytest.mark.parametrize("inputs", [FarmInputs(livestock="yes"), FarmInputs(livestock="no", priorities=frozenset({"income"}))])
def test_property_1_at_least_three_strategies_one_current(name, facts, current, inputs):
    result = site_run(name, facts, current, inputs)
    assert len(result["strategies"]) >= 3
    assert sum(s["is_current"] for s in result["strategies"]) == 1
    assert result["strategies"][0]["is_current"]


@pytest.mark.parametrize("name,facts,current", SITES)
def test_property_2_excluded_crops_never_appear_in_alternatives(name, facts, current):
    result = site_run(name, facts, current)
    excluded = {e["crop_id"] for e in result["exclusions"]}
    for s in alternatives(result):
        added = {c for slot in s["slots"] if not slot["fixed"] for c in slot["crop_ids"]}
        assert not added & excluded, s["id"]


@pytest.mark.parametrize("name,facts,current", SITES)
def test_property_3_no_back_to_back_pest_family(name, facts, current):
    for s in alternatives(site_run(name, facts, current)):
        crops = [slot["crop_ids"] for slot in s["slots"]]
        pairs = list(zip(crops, crops[1:])) + ([(crops[-1], crops[0])] if len(crops) > 1 else [])
        for a, b in pairs:
            fa = {f for c in a for f in CROPS[c]["pest_families"]}
            fb = {f for c in b for f in CROPS[c]["pest_families"]}
            assert not fa & fb, (s["id"], a, b)


@pytest.mark.parametrize("name,facts,current", SITES)
def test_property_4_crops_only_in_their_months(name, facts, current):
    for s in site_run(name, facts, current)["strategies"]:
        assert templates.in_season(s, CROPS)
        for year in s["calendar"] or []:
            for cell in year:
                for crop_id in cell["crop_ids"]:
                    assert cell["month"] in CROPS[crop_id]["in_ground_months"]


@pytest.mark.parametrize("name,facts,current", SITES)
def test_property_5_same_input_same_output(name, facts, current):
    a = json.dumps(site_run(name, facts, current), sort_keys=True, default=str)
    b = json.dumps(site_run(name, facts, current), sort_keys=True, default=str)
    assert a == b


def test_property_6_priorities_change_ranking_but_not_exclusions_or_current():
    plain = webberwood_run(FarmInputs(livestock="yes"))
    forage = webberwood_run(FarmInputs(livestock="yes", priorities=frozenset({"forage"})))
    water = webberwood_run(FarmInputs(livestock="yes", priorities=frozenset({"save_water"})))
    assert plain["exclusions"] == forage["exclusions"] == water["exclusions"]
    for result in (plain, forage, water):
        assert result["strategies"][0]["is_current"]
    best = lambda r: next(s["id"] for s in r["strategies"] if s["best_fit"])  # noqa: E731
    assert best(forage) == "forage_double"
    assert best(water) == "native_perennial"
    assert best(forage) != best(water)


@pytest.mark.parametrize("name,facts,current", SITES)
def test_property_7_findings_and_reasons_cite_evidence(name, facts, current):
    result = site_run(name, facts, current)
    for f in result["findings"]:
        assert f["evidence"] and all(e.get("source") for e in f["evidence"]), f["id"]
    for s in alternatives(result):
        assert s["why"] and all(r["evidence"] for r in s["why"]), s["id"]


# ---- Webberwood specifics ----

def test_webberwood_current_alternatives_and_findings():
    result = webberwood_run()
    current = result["strategies"][0]
    assert current["crop_ids"] == ["bermudagrass"] and "7 of 8 years" in current["why"][0]["text"]
    assert {s["id"] for s in alternatives(result)} == {"native_perennial", "forage_double", "add_winter_legume"}
    assert [f["id"] for f in result["findings"]] == [
        "rising_heat", "warm_nights", "fewer_frosts", "outlook_heat", "slow_soak", "flood_risk"]
    assert all(s["confidence"] == "high" for s in result["strategies"])
    assert all(s["scores"]["outlook"] is not None for s in result["strategies"])


def test_scores_have_parts_and_priority_weights():
    s = alternatives(webberwood_run(FarmInputs(livestock="yes", priorities=frozenset({"build_soil"}))))[0]
    assert set(s["scores"]["today"]) == {"water", "soil", "erosion", "forage", "income", "passes", "overall"}
    assert s["weights"]["soil"] == 2 and s["weights"]["erosion"] == 2 and s["weights"]["water"] == 1
    for dim, parts in s["score_parts"].items():
        assert parts and all("label" in p and "points" in p for p in parts), dim


def test_no_livestock_drops_the_grazing_template_and_zeroes_forage():
    result = webberwood_run(FarmInputs(livestock="no"))
    assert "forage_double" not in {s["id"] for s in result["strategies"]}
    assert result["not_suggested"][0]["id"] == "forage_double"
    assert all(s["scores"]["today"]["forage"] == 0 for s in result["strategies"])


def test_without_the_outlook_confidence_is_medium_and_outlook_scores_are_empty():
    today, _, current, _ = rf.webberwood(with_outlook=False)
    result = run(today, None, CROPS, current, FarmInputs(livestock="yes"), rf.trends(), None)
    assert all(s["confidence"] == "medium" for s in result["strategies"])
    assert all(s["scores"]["outlook"] is None for s in result["strategies"])
    assert "outlook_heat" not in [f["id"] for f in result["findings"]]


def test_missing_soil_survey_lowers_confidence_to_low():
    today, _, current, _ = rf.webberwood(with_outlook=False)
    result = run(replace(today, missing_sources=("USDA SSURGO soil",)), None, CROPS, current, FarmInputs(), rf.trends())
    assert all(s["confidence"] == "low" for s in result["strategies"])
    assert any("Missing data: USDA SSURGO soil." in g for g in result["strategies"][1]["gaps"])


# ---- other sites ----

def test_unknown_current_still_gives_alternatives():
    result = run(DRY_WEST, None, CROPS, FOREST, FarmInputs(livestock="yes"))
    current = result["strategies"][0]
    assert current["is_current"] and current["scores"]["today"] is None and current["confidence"] == "low"
    assert len(alternatives(result)) >= 2


def test_wet_east_rules_out_wet_sensitive_crops():
    excluded = {e["crop_id"] for e in run(WET_EAST, None, CROPS, PASTURE, FarmInputs()).get("exclusions")}
    assert {"cowpea", "sunn_hemp", "crimson_clover", "cotton"} <= excluded


def test_dry_west_rules_out_corn_and_heat_sensitive_spring_crops():
    rules_by_crop = {}
    for e in run(DRY_WEST, None, CROPS, SORGHUM, FarmInputs())["exclusions"]:
        rules_by_crop.setdefault(e["crop_id"], set()).add(e["rule"])
    assert rules_by_crop["corn"] & {"water", "frost"}
    # Ryegrass is still growing in May (a heat month here) and needs more rain than 380 mm.
    assert rules_by_crop["annual_ryegrass"] == {"heat", "water"}


def test_iowa_corn_soy_gets_cereal_covers_between_legumes():
    result = run(IOWA, None, CROPS, CORN_SOY, FarmInputs(livestock="no"))
    assert result["strategies"][0]["crop_ids"] == ["corn", "soybean"]
    excluded = {e["crop_id"] for e in result["exclusions"]}
    legume_plan = templates.fill(templates.TEMPLATES[0], CORN_SOY, CROPS, excluded)
    assert legume_plan["id"] == "add_winter_legume"
    added = [c for slot in legume_plan["slots"] if not slot["fixed"] for c in slot["crop_ids"]]
    assert added == ["winter_wheat_cover", "winter_wheat_cover"]  # vetch would follow or precede soybean
    assert any(f["id"] == "erosion_risk" for f in result["findings"])  # K 0.37 on 9% slopes


def test_calendar_marks_bare_heat_frost_and_wettest_months():
    result = run(DRY_WEST, None, CROPS, SORGHUM, FarmInputs())
    cal = result["strategies"][0]["calendar"][0]
    by_month = {c["month"]: c for c in cal}
    assert by_month[5]["crop_ids"] == ["grain_sorghum"] and by_month[5]["heat"]
    assert by_month[1]["bare"] and by_month[1]["frost"]
    assert by_month[9]["wettest"] and by_month[9]["bare"]
    assert any(f["id"] == "bare_soil" for f in result["findings"])
