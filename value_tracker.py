# value_tracker.py — Squad Value Tracker Brain (V2)
# ============================================================
# Tracks squad value + price changes over time so team value can be
# built for the second half of the season.
#   * current squad value  = sum(now_cost) + ITB
#   * season price drift   = sum(cost_change_start) for the 15
#   * GW-level trend       = entry history value/bank rows
# ============================================================


def summarize(hist_rows, squad_rows):
    if not squad_rows:
        return None
    squad_cost = sum(r["price"] for r in squad_rows)
    drift = sum(float(r.get("_raw", {}).get("cost_change_start") or 0)
                for r in squad_rows) / 10.0
    drift_this_gw = sum(
        float(r.get("_raw", {}).get("cost_change_event") or 0)
        for r in squad_rows) / 10.0

    trend = []
    for row in hist_rows[-8:]:
        trend.append({
            "gw": row.get("event"),
            "value": round((row.get("value") or 0) / 10.0, 1),
            "bank": round((row.get("bank") or 0) / 10.0, 1),
            "points": row.get("points"),
            "bench_pts": row.get("points_on_bench"),
        })
    first = trend[0]["value"] if trend else None
    latest = trend[-1]["value"] if trend else None
    delta = round(latest - first, 1) if (first is not None and
                                         latest is not None) else None
    return {
        "squad_cost": round(squad_cost, 1),
        "season_price_drift": round(drift, 1),
        "this_gw_price_drift": round(drift_this_gw, 1),
        "history_trend": trend,
        "value_delta_8gw": delta,
    }
