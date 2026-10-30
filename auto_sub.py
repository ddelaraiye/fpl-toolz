# auto_sub.py — Auto-Sub Simulation Brain (V2)
# ============================================================
# Simulates FPL's actual automatic substitution rules so bench order
# can be optimised BEFORE the deadline:
#   * bench order is processed strictly 1 -> 2 -> 3 -> 4
#   * the GK slot can only be filled by the bench GK
#   * an outfield sub only enters if the formation stays legal
#     (1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD)
#   * captain cannot be substituted out by the manager; if the captain
#     does not play, the armband passes to the VICE automatically
# ============================================================

POS_SLOT = {1: "gk", 2: "def", 3: "mid", 4: "fwd"}
FORMATION = {"gk": (1, 1), "def": (3, 5), "mid": (2, 5), "fwd": (1, 3)}


def _counts(xi):
    c = {"gk": 0, "def": 0, "mid": 0, "fwd": 0}
    for r in xi:
        c[POS_SLOT[r["pos"]]] += 1
    return c


def simulate(xi, bench, missing_ids, captain_id=None, vice_id=None):
    """Run one simulation. missing_ids = starters that did not play.
    Returns dict with final XI, subs used, blocked subs, and armband note."""
    xi = [dict(r) for r in xi]
    bench = [dict(r) for r in bench]
    used, blocked = [], []
    arm = None

    if captain_id is not None and captain_id in missing_ids:
        arm = ("Captain did not play - armband passes to the VICE. "
               "Set a vice you trust.")
        for r in xi + bench:
            if r["id"] == vice_id:
                arm = (f"Captain did not play - armband passes to VICE "
                       f"{r.get('name', '?')}.")
                break

    for mid in missing_ids:
        starter = next((r for r in xi if r["id"] == mid), None)
        if starter is None:
            continue
        slot = POS_SLOT[starter["pos"]]
        xi.remove(starter)
        taken = None
        for cand in bench:
            cslot = POS_SLOT[cand["pos"]]
            if starter["pos"] == 1 and cand["pos"] != 1:
                continue                     # GK slot: bench GK only
            if starter["pos"] != 1 and cand["pos"] == 1:
                continue                     # never burn the GK sub outfield
            c = _counts(xi)
            trial = dict(c)
            trial[cslot] += 1
            if all(FORMATION[s][0] <= trial[s] <= FORMATION[s][1]
                   for s in ("gk", "def", "mid", "fwd")):
                taken = cand
                break
        if taken is not None:
            bench.remove(taken)
            xi.append(taken)
            used.append({"out": starter.get("name"),
                         "in": taken.get("name")})
        else:
            xi.append(starter)               # no legal sub: slot stays empty
            blocked.append({
                "out": starter.get("name"), "slot": slot.upper(),
                "why": ("No bench player keeps the formation legal for a "
                        f"{slot.upper()} replacement.")})
    return {"xi": xi, "subs_used": used, "blocked": blocked, "armband": arm}


def bench_order_suggestion(xi, bench):
    """Recommended bench order: GK first, then P(play) x projection."""
    gk = [r for r in bench if r["pos"] == 1]
    out = [r for r in bench if r["pos"] != 1]
    out.sort(key=lambda r: (r.get("play_prob", 100) *
                            max(r.get("proj", 0), 0.1)), reverse=True)
    ordered = gk + out
    notes = []
    xi_counts = _counts(xi)
    cover = {"GK": bool(gk),
             "DEF": any(r["pos"] == 2 for r in bench),
             "MID": any(r["pos"] == 3 for r in bench),
             "FWD": any(r["pos"] == 4 for r in bench)}
    for slot in ("GK", "DEF", "MID", "FWD"):
        key = slot.lower()
        if not cover[slot] and xi_counts.get(key, 0) >= \
                FORMATION[key][0]:
            notes.append(f"No {slot} bench cover - a missing {slot} starter "
                         "cannot be auto-subbed.")
    return ordered, notes


def stress_test(xi, bench, captain_id=None, vice_id=None):
    """Worst-case sweep: every single starter missing, one at a time."""
    results = []
    for r in xi:
        sim = simulate(xi, bench, [r["id"]], captain_id, vice_id)
        lost = round(r.get("proj", 0) -
                     (sim["xi"] and sum(x.get("proj", 0) for x in sim["xi"]) -
                      sum(x.get("proj", 0) for x in xi) or 0), 2)
        results.append({
            "if_missing": r.get("name"),
            "sub_in": (sim["subs_used"][0]["in"] if sim["subs_used"]
                       else "NONE - points lost"),
            "blocked": bool(sim["blocked"]),
            "armband": sim["armband"]})
    return results
