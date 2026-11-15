"""Rotation explorer: turns farm facts into crop-rotation options a farmer can compare.

Everything here is written as plain rules and formulas, not a trained model, so every
suggestion can be traced back to a number and its source:

- site_facts.py   the facts about one field (climate, soil, farmer choices), each with its source
- crops.py        loads and checks the sourced crop table in config/crops.json
- indicators.py   yearly climate measures from daily weather (hot days, frost days, dry spells...)
- trends.py       how those measures changed since 1981, and whether the change is clear
- current.py      the rotation the field has now, from the USDA crop map history
- rules.py        rules that rule a crop out for this field (wet soil, heat, frost, water)
- templates.py    the rotation patterns the tool can suggest
- scoring.py      0-100 scores on six farmer goals, with the formula shown
- findings.py     short plain sentences about what stands out on this field
- explain.py      why each option was suggested, its risks and what we don't know
- engine.py       puts it all together (no network access, so it is easy to test)

The tool supports farmer judgment. It does not replace it or local expertise.
"""
