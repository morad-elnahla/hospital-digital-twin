"""Explainable, replay-safe forecasts and rolling-origin evaluation.

The candidate is a ridge-stabilized linear model with weekday effects, a linear
trend and annual/semi-annual Fourier terms. It is selected only when its rolling
origin MAE and WAPE both beat the weekday-mean baseline.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta

ORIGINS = 90
MIN_TRAINING_DAYS = 180
HORIZONS = tuple(range(1, 8))
MODEL_NAME = "weekday_trend_seasonal"
BASELINE_NAME = "weekday_mean"


def _float(value):
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _features(day: date, anchor: date) -> list[float]:
    t = (day - anchor).days / 365.2425
    annual = 2 * math.pi * (day.timetuple().tm_yday - 1) / 365.2425
    return ([1.0] + [1.0 if day.weekday() == w else 0.0 for w in range(1, 7)]
            + [t, math.sin(annual), math.cos(annual), math.sin(2 * annual), math.cos(2 * annual)])


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Small pivoted Gauss-Jordan solve; no numerical package or hidden model dependency."""
    n = len(vector)
    a = [matrix[i][:] + [vector[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(a[row][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise ArithmeticError("singular forecast design")
        a[col], a[pivot] = a[pivot], a[col]
        scale = a[col][col]
        a[col] = [x / scale for x in a[col]]
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            if factor:
                a[row] = [x - factor * y for x, y in zip(a[row], a[col])]
    return [a[i][-1] for i in range(n)]


def _fit_trend_seasonal(history: list[tuple[date, float]]):
    if len(history) < MIN_TRAINING_DAYS:
        return None
    anchor = history[0][0]
    rows = [(_features(day, anchor), value) for day, value in history]
    width = len(rows[0][0])
    gram = [[0.0] * width for _ in range(width)]
    rhs = [0.0] * width
    for x, y in rows:
        for i in range(width):
            rhs[i] += x[i] * y
            for j in range(width):
                gram[i][j] += x[i] * x[j]
    for i in range(1, width):
        gram[i][i] += 1e-6
    try:
        beta = _solve(gram, rhs)
    except ArithmeticError:
        return None
    return anchor, beta


def _predict_fitted(fitted, target: date) -> float | None:
    if fitted is None:
        return None
    anchor, beta = fitted
    return max(0.0, sum(x * b for x, b in zip(_features(target, anchor), beta)))


def _weekday_mean(history: list[tuple[date, float]], target: date) -> float | None:
    same_day = [value for day, value in history if day.weekday() == target.weekday()]
    return statistics.fmean(same_day) if same_day else (statistics.fmean(v for _, v in history) if history else None)


def _score(pairs: list[tuple[float, float]]) -> dict:
    total = sum(abs(actual) for _, actual in pairs)
    return {
        "n": len(pairs),
        "mae": round(statistics.fmean(abs(predicted - actual) for predicted, actual in pairs), 4) if pairs else None,
        "wape": round(sum(abs(predicted - actual) for predicted, actual in pairs) / total, 4) if total else None,
        "bias": round(statistics.fmean(predicted - actual for predicted, actual in pairs), 4) if pairs else None,
        "mean_actual": round(statistics.fmean(actual for _, actual in pairs), 4) if pairs else None,
    }


def _rolling(values: dict[date, float], stop: date) -> dict:
    by_horizon = {h: {BASELINE_NAME: [], MODEL_NAME: []} for h in HORIZONS}
    if not values:
        return {"window": {"from": None, "to": None}, "horizons": {}, "overall": {}, "beats_baseline": False}
    first = min(values)
    start = max(first + timedelta(days=MIN_TRAINING_DAYS), stop - timedelta(days=ORIGINS))
    for offset in range(max(0, (stop - start).days)):
        origin = start + timedelta(days=offset)
        history = sorted((day, value) for day, value in values.items() if day < origin)
        if len(history) < MIN_TRAINING_DAYS:
            continue
        fitted = _fit_trend_seasonal(history)
        for horizon in HORIZONS:
            target = origin + timedelta(days=horizon)
            if target >= stop or target not in values:
                continue
            actual = values[target]
            baseline = _weekday_mean(history, target)
            candidate = _predict_fitted(fitted, target)
            if baseline is not None:
                by_horizon[horizon][BASELINE_NAME].append((baseline, actual))
            if candidate is not None:
                by_horizon[horizon][MODEL_NAME].append((candidate, actual))
    horizon_scores = {
        str(h): {name: _score(pairs) for name, pairs in methods.items()}
        for h, methods in by_horizon.items()
    }
    all_pairs = {name: [pair for h in HORIZONS for pair in by_horizon[h][name]]
                 for name in (BASELINE_NAME, MODEL_NAME)}
    overall = {name: _score(pairs) for name, pairs in all_pairs.items()}
    base, candidate = overall[BASELINE_NAME], overall[MODEL_NAME]
    for name, metrics in overall.items():
        metrics["skill_vs_weekday_mean"] = (0.0 if name == BASELINE_NAME else
                                            None if base["mae"] in (None, 0) or metrics["mae"] is None else
                                            round(1 - metrics["mae"] / base["mae"], 4))
    enough = min(base["n"], candidate["n"]) >= 100
    beats = bool(enough and base["mae"] is not None and candidate["mae"] is not None
                 and base["wape"] is not None and candidate["wape"] is not None
                 and candidate["mae"] < base["mae"] and candidate["wape"] < base["wape"])
    last_actual = min(stop - timedelta(days=1), max(values))
    first_actual = max(start, min(values))
    return {"window": {"from": first_actual.isoformat(), "to": last_actual.isoformat()},
            "horizons": horizon_scores, "overall": overall, "beats_baseline": beats,
            "selection_rule": "use trend-seasonal only when rolling-origin MAE and WAPE are both below weekday mean"}


def _targets(td) -> dict[str, dict]:
    # TwinData instances are immutable replay snapshots. Target extraction scans the
    # full nursing roster, so reuse the indexed targets across scenarios on one snapshot.
    cached = getattr(td, "_phase3_targets_cache", None)
    if cached is not None:
        return cached
    vals: dict[str, dict[date, float]] = defaultdict(dict)
    for day_text, departments in td.metrics.items():
        day = date.fromisoformat(day_text)
        for unit in ("ER", "ICU", "WARD"):
            dep = td.dept_by_type.get(unit)
            row = departments.get(dep, {}) if dep else {}
            value = _float(row.get("occupancy_rate"))
            if value is not None:
                vals[f"{unit}:occupancy"][day] = value
            if unit == "ER":
                for alias, column in (("er_arrivals", "arrivals_count"), ("er_wait", "avg_wait_minutes")):
                    value = _float(row.get(column))
                    if value is not None:
                        vals[alias][day] = value
        or_dep = td.dept_by_type.get("OR")
        or_row = departments.get(or_dep, {}) if or_dep else {}
        value = _float(or_row.get("or_utilization_rate"))
        if value is not None:
            vals["or_util"][day] = value

    # Coverage records report required nursing per shift. The daily target is the highest
    # sourced shift requirement for that unit; no doctor-demand target exists in the pack.
    for row in td.t.get("nurse_coverage_shift_detail", ()):
        unit = next((name for name in ("ER", "ICU", "WARD") if td.dept_by_type.get(name) == row["unit"]), None)
        value = _float(row.get("required_nurses"))
        if unit and value is not None:
            day = date.fromisoformat(row["date"])
            alias = f"{unit}:nurses"
            vals[alias][day] = max(vals[alias].get(day, 0.0), value)

    targets = {key: {"values": value, "table": "nurse_coverage_shift_detail" if key.endswith(":nurses") else "daily_metrics"}
               for key, value in vals.items()}
    td._phase3_targets_cache = targets
    return targets


def build(td, as_of: datetime) -> dict[str, dict]:
    targets = _targets(td)
    cache_key = (as_of.date(), tuple((key, tuple(sorted(value["values"].items())))
                                     for key, value in sorted(targets.items())))
    cache = getattr(td, "_phase3_forecast_cache", None)
    if cache is None:
        cache = td._phase3_forecast_cache = {}
    if cache_key in cache:
        return cache[cache_key]

    stop = as_of.date()
    out = {}
    for key, target in targets.items():
        values = target["values"]
        history = sorted((day, value) for day, value in values.items() if day < stop)
        rolling = _rolling(values, stop)
        use_model = rolling["beats_baseline"]
        selected = MODEL_NAME if use_model else BASELINE_NAME
        fitted = _fit_trend_seasonal(history)
        history_start = stop - timedelta(days=14)
        historical_points = [{"date": (history_start + timedelta(days=i)).isoformat(),
                              "value": values.get(history_start + timedelta(days=i))}
                             for i in range(14)]
        points = []
        for offset in range(1, 8):
            day = stop + timedelta(days=offset)
            model_value = _predict_fitted(fitted, day)
            baseline_value = _weekday_mean(history, day)
            predicted = model_value if use_model else baseline_value
            if predicted is None:
                continue
            points.append({"date": day.isoformat(), "predicted": round(predicted, 4),
                           "lower": None, "upper": None,
                           "actual": round(values[day], 4) if day in values else None})
        out[key] = {"table": target["table"], "history": historical_points, "points": points,
                    "training_period": {"from": history[0][0].isoformat() if history else None,
                                        "to": history[-1][0].isoformat() if history else None},
                    "selected_model": selected,
                    "beats_baseline": use_model, "rolling": rolling,
                    "abstain_reason": None if use_model else
                    "Trend-seasonal forecast did not beat weekday-mean MAE and WAPE in rolling-origin validation; agents abstain.",
                    "history_days": len(history)}
    if len(cache) >= 16:
        cache.clear()
    cache[cache_key] = out
    return out


def evaluation_rows(td, as_of: datetime, report: dict | None = None) -> list[dict]:
    report = report or build(td, as_of)
    bed_counts = {unit: td.beds_total.get(unit, 0) for unit in ("ER", "ICU", "WARD")}
    evaluation_targets = {
        "er_arrivals": ("ER:arrivals", 1.0),
        "er_wait": ("ER:wait_minutes", 1.0),
        "ER:occupancy": ("ER:beds:demand", float(bed_counts["ER"])),
        "ICU:occupancy": ("ICU:beds:demand", float(bed_counts["ICU"])),
        "WARD:occupancy": ("WARD:beds:demand", float(bed_counts["WARD"])),
        "or_util": ("OR:utilization", 100.0),
        "ER:nurses": ("ER:nurses:demand", 1.0),
        "ICU:nurses": ("ICU:nurses:demand", 1.0),
        "WARD:nurses": ("WARD:nurses:demand", 1.0),
    }
    rows = []
    for alias, (label, scale) in evaluation_targets.items():
        item = report.get(alias)
        if item is None:
            continue
        horizon_scores = {"0": item["rolling"]["overall"], **item["rolling"]["horizons"]}
        for horizon, method_scores in horizon_scores.items():
            base = method_scores[BASELINE_NAME]
            candidate = method_scores[MODEL_NAME]
            for model_name, score in ((BASELINE_NAME, base), (MODEL_NAME, candidate)):
                mae = score["mae"]
                wape = score["wape"]
                rows.append({
                    "run_group": "phase3_rolling_origin_v1", "target": label,
                    "horizon_days": int(horizon), "model_name": model_name,
                    "n": score["n"], "mae": None if mae is None else round(mae * scale, 4),
                    "wape": wape, "mape_floor": None, "mape_floor_value": None,
                    "bias": None if score["bias"] is None else round(score["bias"] * scale, 4),
                    "pinball_loss": None, "coverage_80": None, "capped_day_share": None,
                    "skill_vs_naive": (0.0 if model_name == BASELINE_NAME else
                                        None if base["mae"] in (None, 0) or mae is None else round(1 - mae / base["mae"], 4)),
                })
    return rows
