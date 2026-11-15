"""How a yearly climate measure has changed, and whether the change is clear.

Two standard methods, written out so no extra package is needed:

- Theil-Sen slope: the median of the slopes between every pair of years. Because it is a
  median, one extreme year (a record drought, a flood year) cannot swing it (Req 17.4).
- Mann-Kendall test: asks how likely a run of ups and downs at least this one-sided would be
  if there were no trend at all. A change is called "clear" only when that chance is below
  5% (p < 0.05). Otherwise the farmer sees "no clear change" (Req 17.5).

Rare events (for example heavy-rain days, where most years have none) make the Theil-Sen
slope collapse to zero. For a measure with zeros in more than half its years, the change is
reported as the average of the last 15 years minus the first 15 years (Req 17.12).

Known limit: year-to-year persistence (a wet year followed by a wet year) is not corrected
for. This is listed as an information gap in the results.
"""
import math
import statistics

MIN_YEARS = 10      # fewer years than this: no trend is reported
RARE_WINDOW = 15    # years at each end for the rare-event comparison
CLEAR_P = 0.05


def theil_sen_slope(years: list[int], values: list[float]) -> float:
    """Median slope between all pairs of points (units per year)."""
    slopes = [
        (values[j] - values[i]) / (years[j] - years[i])
        for i in range(len(years)) for j in range(i + 1, len(years))
        if years[j] != years[i]
    ]
    return statistics.median(slopes) if slopes else 0.0


def mann_kendall_p(values: list[float]) -> float:
    """Two-sided p-value of the Mann-Kendall trend test, with the correction for tied values."""
    n = len(values)
    if n < 3:
        return 1.0
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            s += (values[j] > values[i]) - (values[j] < values[i])
    ties: dict[float, int] = {}
    for v in values:
        ties[v] = ties.get(v, 0) + 1
    var = (n * (n - 1) * (2 * n + 5) - sum(t * (t - 1) * (2 * t + 5) for t in ties.values())) / 18
    if var <= 0:
        return 1.0
    if s > 0:
        z = (s - 1) / math.sqrt(var)
    elif s < 0:
        z = (s + 1) / math.sqrt(var)
    else:
        z = 0.0
    return 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))


def _mean(values):
    return round(statistics.fmean(values), 1) if values else None


def trend(series: dict[int, float]) -> dict:
    """Describe the change in a yearly series {year: value}.

    Returns a dict with: years ("1981-2025"), n_years, method ("theil_sen" or
    "first_last_15"), per_decade (Theil-Sen only), change (first_last_15 only), p_value,
    clear, first_decade_avg, last_decade_avg. With fewer than 10 years, method is
    "not_enough_years" and clear is False.
    """
    years = sorted(series)
    values = [series[y] for y in years]
    result = {
        "years": f"{years[0]}-{years[-1]}" if years else None,
        "n_years": len(years),
        "first_decade_avg": _mean(values[:10]),
        "last_decade_avg": _mean(values[-10:]),
        "per_decade": None,
        "change": None,
    }
    if len(years) < MIN_YEARS:
        return dict(result, method="not_enough_years", p_value=None, clear=False)

    p = round(mann_kendall_p(values), 4)
    zeros = sum(1 for v in values if v == 0)
    if zeros * 2 > len(values):
        window = min(RARE_WINDOW, len(values) // 2)
        change = statistics.fmean(values[-window:]) - statistics.fmean(values[:window])
        return dict(result, method="first_last_15", change=round(change, 2), p_value=p, clear=p < CLEAR_P)

    per_decade = theil_sen_slope(years, values) * 10
    return dict(result, method="theil_sen", per_decade=round(per_decade, 2), p_value=p, clear=p < CLEAR_P)
