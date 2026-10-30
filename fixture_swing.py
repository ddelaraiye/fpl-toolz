# fixture_swing.py — Fixture Swing Detector Brain (V2)
# ============================================================
# Detects when a team's fixtures turn green or red over the next
# 6 gameweeks and alerts 2-3 weeks in advance, so transfers can be
# made BEFORE the swing (buy on the turn, not after it).
#
# Rule (frozen):
#   near = mean FDR of GW+1..GW+3   far = mean FDR of GW+4..GW+6
#   GREEN TURN: far - near <= -0.8   (schedule eases sharply)
#   RED TURN  : far - near >= +0.8   (schedule hardens sharply)
#   BLANK flag: team has no fixture inside the window
# ============================================================


def detect(fx_map, teams, swing_threshold=0.8):
    """fx_map: {team_id: [ {gw, fdr, opp_short, ha} ... ]} from ui_engine."""
    alerts = []
    for tid, fxs in fx_map.items():
        if not fxs:
            continue
        fxs = sorted(fxs, key=lambda x: x["gw"])[:6]
        near = [x for x in fxs if x["gw"] <= fxs[0]["gw"] + 2]
        far = [x for x in fxs if x["gw"] > fxs[0]["gw"] + 2]
        if not near:
            continue
        near_avg = sum(x["fdr"] for x in near) / len(near)
        if far:
            far_avg = sum(x["fdr"] for x in far) / len(far)
        else:
            far_avg = near_avg
        delta = far_avg - near_avg
        blank_gws = []
        if len(fxs) < 6:
            have = {x["gw"] for x in fxs}
            for gw in range(fxs[0]["gw"], fxs[0]["gw"] + 6):
                if gw not in have:
                    blank_gws.append(gw)
        short = teams[tid]["short_name"] if isinstance(teams[tid], dict) \
            else str(tid)
        run = " ".join(_dot(x["fdr"]) for x in fxs)
        if blank_gws:
            alerts.append({
                "team": short, "type": "BLANK",
                "run": run,
                "message": (f"{short} blank in "
                            f"GW{','.join(map(str, blank_gws))} - plan "
                            "bench cover or a Free Hit.")})
        elif delta <= -swing_threshold:
            alerts.append({
                "team": short, "type": "GREEN TURN", "run": run,
                "message": (f"{short} fixtures turn GREEN after GW"
                            f"{near[-1]['gw']} "
                            f"(avg {near_avg:.1f} -> {far_avg:.1f}). "
                            "Buy their assets BEFORE the run.")})
        elif delta >= swing_threshold:
            alerts.append({
                "team": short, "type": "RED TURN", "run": run,
                "message": (f"{short} fixtures turn RED after GW"
                            f"{near[-1]['gw']} "
                            f"(avg {near_avg:.1f} -> {far_avg:.1f}). "
                            "Sell into strength before the run.")})
    order = {"GREEN TURN": 0, "BLANK": 1, "RED TURN": 2}
    alerts.sort(key=lambda a: (order.get(a["type"], 3), a["team"]))
    return alerts


def _dot(f):
    if f <= 1.99:
        return "G"
    if f <= 2.99:
        return "g"
    if f <= 3.99:
        return "o"
    return "R"
