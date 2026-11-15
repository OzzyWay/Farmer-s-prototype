"""Put everything together for one field: options, scores, explanations and findings (Req 7, 9).

Pure: no network and no files, so the tests call it directly with hand-made facts.

Steps:
1. Run the rules to find crops ruled out today, and crops at risk under the 2030-2049 outlook.
2. Build the current rotation as a strategy, and fill every template that applies.
3. Draw each strategy's calendar and score it for today and for the outlook.
4. Keep the current strategy first, then the best 3 alternatives by today's overall score
   (ties go to the template order, so the order is always the same).
5. Explain each one, and add the findings about the field.
"""
from app.rotation import explain, scoring, templates
from app.rotation.findings import findings as find_findings
from app.rotation.rules import evaluate
from app.rotation.site_facts import FarmInputs, SiteFacts

MAX_ALTERNATIVES = 3


def _future_risks(strategy, future):
    return [dict(e, crop_id=crop_id) for crop_id in strategy["crop_ids"] for e in future.get(crop_id, [])]


def _build(strategy, crops, today, outlook, inputs, rule_result, current, found, missing, outlook_loaded):
    cal = templates.calendar(strategy, crops, today)
    now = scoring.score(strategy, cal, crops, today, inputs)
    future_risks = _future_risks(strategy, rule_result["future"])
    scores = {"today": now["scores"], "outlook": None}
    if outlook is not None:
        later = scoring.score(strategy, templates.calendar(strategy, crops, outlook), crops, outlook, inputs)
        scores["outlook"] = dict(later["scores"], overall=scoring.outlook_overall(later["scores"]["overall"], len(future_risks)))
    level, missing_facts = explain.confidence(missing, outlook_loaded, current)
    return dict(
        strategy,
        calendar=cal,
        scores=scores,
        score_parts=now["parts"],
        weights=now["weights"],
        why=explain.why(strategy, crops, today, current, found),
        benefits=explain.benefits(strategy, crops, inputs),
        risks=explain.risks(strategy, crops, today),
        future_risks=future_risks,
        gaps=explain.gaps(missing),
        soil_health_notes=explain.soil_health_notes(strategy, crops),
        confidence=level,
        missing_facts=missing_facts,
        best_fit=False,
    )


def run(today: SiteFacts, outlook: SiteFacts | None, crops: dict, current: dict, inputs: FarmInputs,
        trends: dict | None = None, outlook_doc: dict | None = None) -> dict:
    """Return {"current_rotation", "strategies", "exclusions", "not_suggested", "findings"}."""
    rule_result = evaluate(crops, today, outlook, inputs.irrigation)
    excluded = set(rule_result["excluded"])
    missing = list(today.missing_sources)
    outlook_loaded = outlook is not None

    current_strategy = templates.current_strategy(current, crops)
    current_cal = templates.calendar(current_strategy, crops, today) if current_strategy["slots"] else None
    found = find_findings(today, trends, outlook_doc, current_cal)

    alternatives, not_suggested = [], []
    for template in templates.TEMPLATES:
        if template.get("needs_livestock") and inputs.livestock == "no":
            not_suggested.append({"id": template["id"], "name": template["name"],
                                  "reason": "Its main benefit is grazing, and you said you have no livestock."})
            continue
        filled = templates.fill(template, current, crops, excluded)
        if filled is None:
            continue
        if filled["crop_ids"] == current_strategy["crop_ids"]:
            continue  # nothing new compared with the current rotation
        alternatives.append(filled)

    built = [_build(s, crops, today, outlook, inputs, rule_result, current, found, missing, outlook_loaded)
             for s in alternatives]
    order = {tid: i for i, tid in enumerate(templates.TEMPLATE_ORDER)}
    built.sort(key=lambda s: (-s["scores"]["today"]["overall"], order[s["id"]]))
    built = built[:MAX_ALTERNATIVES]
    if built:
        built[0]["best_fit"] = True

    if current_strategy["slots"]:
        current_built = _build(current_strategy, crops, today, outlook, inputs, rule_result, current, found,
                               missing, outlook_loaded)
    else:
        level, missing_facts = explain.confidence(missing, outlook_loaded, current)
        current_built = dict(current_strategy, calendar=None, scores={"today": None, "outlook": None}, score_parts={},
                             weights={}, why=[{"text": current.get("reason", "Not known."), "evidence": []}],
                             benefits=[], risks=[], future_risks=[], gaps=explain.gaps(missing),
                             soil_health_notes=[], confidence=level, missing_facts=missing_facts, best_fit=False)

    exclusions = [e for crop_id in sorted(rule_result["excluded"]) for e in rule_result["excluded"][crop_id]]
    return {
        "current_rotation": current,
        "strategies": [current_built] + built,
        "exclusions": exclusions,
        "not_suggested": not_suggested,
        "findings": found,
        "ranking_note": "Ranked by your priorities. These are starting points to discuss with your county extension agent, not recommendations.",
    }
