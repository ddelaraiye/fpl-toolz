# ui_engine.py — FPL Toolz V2 "Command Center" Engine
# ============================================================
# Self-contained decision engine for the Streamlit Command Center.
# Public FPL API only. No credentials. Cloud-safe (no required writes).
#
# Design sources:
#   - FPL Toolz V1 SPEC (frozen formula registry) — projection, Smart FDR,
#     captain five-factor, value floor, chip anchoring carried forward.
#   - V2 upgrade spec (DeepSeek build sessions, Oct 2026) — horizon toggle,
#     DefCon, bench reliability, true market scan, chips ledger,
#     price-change alerts, ML data hook.
#
# Environment behaviors this engine respects (verified against the live API):
#   * events.is_next            -> the ONLY reliable gameweek anchor
#   * events.is_finished        -> lies all season; never used
#   * entry/.../event/N/picks/  -> 404 until that GW's deadline has passed
#   * entry history 'chips'     -> empty until a played GW completes; the
#                                  local chips_used.json ledger is authoritative
#   * live points               -> stats.total_points only (post-GW)
# ============================================================

import json
import os
import time
import tempfile
from datetime import datetime, timezone

import requests

try:
    from h2h_adjuster import h2h_modifier_for  # optional brain
except Exception:  # pragma: no cover - standalone fallback
    def h2h_modifier_for(team_h, team_a, position):
        return 0.0, ""

BASE_URL = "https://fantasy.premierleague.com/api/"

# ---------------------------------------------------------------
# V2 FORMULA REGISTRY  (SPEC V2 §4 — frozen, do not tune per-output)
# ---------------------------------------------------------------
FDR_LOOKBACK_GW = 3          # opponent form window
POS_FLOOR = {1: 2.0, 2: 2.0, 3: 3.0, 4: 2.0}          # 1 GK, 2 DEF, 3 MID, 4 FWD
PTS_MULT = {1: 1.20, 2: 1.05, 3: 0.90, 4: 0.78, 5: 0.65}
CAPTAIN_W = {"fixture": 0.35, "form": 0.25, "underlying": 0.20,
             "role": 0.10, "ownership": 0.10}
CAPTAIN_VERDICT = [(8.5, "STRONG LOCK"), (7.0, "SOLID"), (5.5, "LEAN")]
VALUE_FLOOR = 3.0            # pts/GW; GK and core exempt
SWAP_EDGE = 4.0              # horizon pts gain needed to recommend a move
HIT_COST = 4
FT_BANK_CAP = 5              # 2025/26+ free-transfer banking cap
DEFCON_MEDIAN = 7.39         # defensive_contribution_per_90, defender median
DEFCON_P75 = 9.37            # defender 75th percentile
PRICE_ALERT_NET = -50000     # net transfers out that triggers a banner
POS_NAME = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

# ---------------------------------------------------------------
# State storage: local folder when writable (CLI parity with V1),
# temp dir otherwise (Streamlit Cloud resets anyway).
# ---------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
try:
    with open(os.path.join(_HERE, ".write_test"), "w") as f:
        f.write("ok")
    os.remove(os.path.join(_HERE, ".write_test"))
    STATE_DIR = _HERE
except Exception:
    STATE_DIR = tempfile.gettempdir()

SEED_FILE = os.path.join(STATE_DIR, "v2_squad.json")
CHIPS_FILE = os.path.join(STATE_DIR, "chips_used.json")
PRICES_FILE = os.path.join(STATE_DIR, "prices_v2.json")
ML_FILE = os.path.join(STATE_DIR, "ml_training_data.csv")

_TTL = {}


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        return True
    except Exception:
        return False


def get_json(path, ttl=600, params=None):
    """Cached GET with time-to-live (seconds). Single shared TTL map."""
    now = time.time()
    key = path + (json.dumps(params, sort_keys=True) if params else "")
    hit = _TTL.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    r = requests.get(BASE_URL + path, params=params, timeout=25)
    r.raise_for_status()
    data = r.json()
    _TTL[key] = (now, data)
    return data


def clear_cache():
    _TTL.clear()


# ===============================================================
# DATA LAYER
# ===============================================================
def fetch_bootstrap():
    data = get_json("bootstrap-static/", ttl=600)
    players = {p["id"]: p for p in data["elements"]}
    teams = {t["id"]: t for t in data["teams"]}
    events = data["events"]
    return players, teams, events


def fetch_fixtures():
    return get_json("fixtures/", ttl=600)


def next_gw_info(events):
    """The is_next anchor + deadline. is_finished is never trusted."""
    for e in events:
        if e.get("is_next"):
            dl = e.get("deadline_time_epoch")
            dl_iso = e.get("deadline_time")
            return {"gw": e["id"], "name": e["name"],
                    "deadline_epoch": dl, "deadline_iso": dl_iso}
    finished = [e["id"] for e in events if e.get("is_current")]
    gw = max(finished) if finished else 1
    return {"gw": gw, "name": f"GW{gw}", "deadline_epoch": None,
            "deadline_iso": None}


def fetch_entry_history(team_id):
    return get_json(f"entry/{team_id}/history/", ttl=300)


def fetch_entry_picks(team_id, gw):
    """Returns (picks_dict | None). 404 => blind window (pre-deadline)."""
    try:
        return get_json(f"entry/{team_id}/event/{gw}/picks/", ttl=120)
    except Exception:
        return None


def fetch_team_name(team_id):
    try:
        return get_json(f"entry/{team_id}/", ttl=3600).get("name",
                                                           f"Team {team_id}")
    except Exception:
        return f"Team {team_id}"


# ===============================================================
# SMART FDR  (V1 frozen: official difficulty +/- opponent last-3 form,
# plus the V2 H2H modifier when h2h.csv provides data)
# ===============================================================
def team_form(gw, fixtures):
    """Goals scored/conceded over the last FDR_LOOKBACK_GW completed GWs."""
    stats = {}
    for f in fixtures:
        if not f.get("finished") or f.get("event") is None:
            continue
        if f["event"] < gw - FDR_LOOKBACK_GW or f["event"] >= gw:
            continue
        h, a = f["team_h"], f["team_a"]
        hs = f.get("team_h_score") or 0
        as_ = f.get("team_a_score") or 0
        for tid, sc, con in ((h, hs, as_), (a, as_, hs)):
            d = stats.setdefault(tid, {"scored": 0, "conceded": 0, "games": 0})
            d["scored"] += sc
            d["conceded"] += con
            d["games"] += 1
    return stats


def smart_fdr(base_fdr, pos, opp_id, form, h2h_delta=0.0):
    """Adjusted difficulty 1..5 for a player of `pos` vs opponent opp_id."""
    opp = form.get(opp_id, {"scored": 3, "conceded": 3})
    modifier = 0
    if pos in (1, 2):                      # GK / DEF care about opp attack
        if opp["scored"] >= 5:
            modifier = 1
        elif opp["scored"] <= 1:
            modifier = -1
    else:                                  # MID / FWD care about opp defence
        if opp["conceded"] >= 5:
            modifier = -1
        elif opp["conceded"] <= 1:
            modifier = 1
    raw = base_fdr + modifier + h2h_delta
    return max(1, min(5, raw)), modifier


def fixtures_map(gw_start, horizon, fixtures, teams):
    """{team_id: [ {gw, opp, opp_short, ha, fdr} ... ] } for the window."""
    out = {}
    for f in fixtures:
        ev = f.get("event")
        if ev is None or not (gw_start <= ev < gw_start + horizon):
            continue
        for me, opp, fdr, ha in ((f["team_h"], f["team_a"],
                                  f["team_h_difficulty"], "H"),
                                 (f["team_a"], f["team_h"],
                                  f["team_a_difficulty"], "A")):
            out.setdefault(me, []).append({
                "gw": ev, "opp": opp, "opp_short": teams[opp]["short_name"],
                "ha": ha, "fdr": fdr})
    return out


def fdr_color(f):
    if f <= 1.99:
        return "green"
    if f <= 2.99:
        return "olive"
    if f <= 3.99:
        return "orange"
    return "red"


# ===============================================================
# SQUAD RESOLUTION  (three layers, V1-verified)
#   1) public picks for the NEXT gw  -> only after its deadline passed
#   2) v2_squad.json seed            -> pre-deadline intent (workbench)
#   3) last locked gw picks          -> previous truth (self-heals later)
# ===============================================================
def resolve_squad(team_id, gw, players, teams):
    info = {"source": None, "note": "", "picks": None, "bank": None,
            "captain_id": None, "vice_id": None, "bench_order": None}

    p = fetch_entry_picks(team_id, gw)
    if p is not None:
        info["source"] = "api_locked"
        info["note"] = (f"Official GW{gw} squad (deadline passed). "
                        "Auto-detected from the FPL API.")
        info["picks"] = [pick["element"] for pick in p["picks"]]
        info["bank"] = (p.get("entry_history", {}).get("bank", 0) or 0) / 10.0
        for pick in p["picks"]:
            if pick.get("is_captain"):
                info["captain_id"] = pick["element"]
            if pick.get("is_vice_captain"):
                info["vice_id"] = pick["element"]
        info["active_chip"] = p.get("active_chip")
        return info

    seed = _read_json(SEED_FILE, None)
    if seed and seed.get("gw") == gw and seed.get("players"):
        info["source"] = "seed"
        info["note"] = (f"Pre-deadline workbench squad for GW{gw} "
                        "(v2_squad.json). The API only publishes squads "
                        "after the deadline - this is your intended 15.")
        info["picks"] = [pl["id"] for pl in seed["players"]]
        info["bank"] = seed.get("itb")
        info["captain_id"] = seed.get("captain_id")
        info["vice_id"] = seed.get("vice_id")
        info["bench_order"] = seed.get("bench_order")
        info["active_chip"] = seed.get("active_chip")
        return info

    for back in range(1, 4):
        p = fetch_entry_picks(team_id, gw - back)
        if p is not None:
            info["source"] = "api_previous"
            info["note"] = (f"GW{gw - back} squad (last locked truth). "
                            f"GW{gw} is in the pre-deadline blind window - "
                            "update v2_squad.json if your intended team "
                            "differs.")
            info["picks"] = [pick["element"] for pick in p["picks"]]
            info["bank"] = (p.get("entry_history", {}).get("bank", 0) or 0) / 10.0
            for pick in p["picks"]:
                if pick.get("is_captain"):
                    info["captain_id"] = pick["element"]
                if pick.get("is_vice_captain"):
                    info["vice_id"] = pick["element"]
            return info

    if seed and seed.get("players"):
        info["source"] = "seed_stale"
        info["note"] = ("No API squad reachable; showing the last "
                        "v2_squad.json seed (GW%s)." % seed.get("gw"))
        info["picks"] = [pl["id"] for pl in seed["players"]]
        info["bank"] = seed.get("itb")
        info["captain_id"] = seed.get("captain_id")
        info["vice_id"] = seed.get("vice_id")
        info["bench_order"] = seed.get("bench_order")
        info["active_chip"] = seed.get("active_chip")
    return info


def save_seed(gw, player_ids, captain_id=None, vice_id=None,
              bench_order=None, itb=None, active_chip=None, label="manual"):
    """Workbench sync: persist an intended squad for the blind window."""
    seed = {"gw": gw, "updated": datetime.now(timezone.utc).isoformat(),
            "label": label, "players": [{"id": i} for i in player_ids],
            "captain_id": captain_id, "vice_id": vice_id,
            "bench_order": bench_order, "itb": itb,
            "active_chip": active_chip}
    return _write_json(SEED_FILE, seed)


# ===============================================================
# PROJECTION  (V1 frozen formula, per fixture, DGW-aware,
# health-weighted; horizon = mean over the window)
# ===============================================================
def health_weight(p):
    ch = p.get("chance_of_playing_next_round")
    ch_this = p.get("chance_of_playing_this_round")
    val = ch if ch is not None else ch_this
    if val is None:
        return 1.0
    return max(0.25, min(1.0, float(val) / 100.0))


def baseline_ppg(p):
    form = float(p.get("form") or 0)
    if (p.get("minutes") or 0) >= 90 and form > 0:
        return form
    return POS_FLOOR[p["element_type"]]


def project_player(p, fxs, form, horizon, use_defcon=False,
                   defcon_scale=None):
    """Mean projected pts/GW over the given fixtures (from fixtures_map)."""
    if not fxs:
        return 0.0, 3.0, []
    base = baseline_ppg(p)
    per = []
    for fx in fxs:
        h2h_delta, _ = h2h_modifier_for(fx.get("team_h_id", 0),
                                        fx.get("opp", 0), p["element_type"])
        f, _mod = smart_fdr(fx["fdr"], p["element_type"], fx["opp"], form,
                            h2h_delta)
        pts = base * PTS_MULT[int(round(f))]
        per.append({"gw": fx["gw"], "opp": fx["opp_short"], "ha": fx["ha"],
                    "fdr": round(f, 2), "pts": round(pts, 2)})
    mean_pts = sum(x["pts"] for x in per) / len(per)
    avg_fdr = sum(x["fdr"] for x in per) / len(per)
    if use_defcon and p["element_type"] == 2 and defcon_scale:
        dc = float(p.get("defensive_contribution_per_90") or 0)
        if dc >= defcon_scale.get("p75", DEFCON_P75):
            mean_pts *= 1.20
            per.append({"note": "DefCon +20% (top-quartile defender)"})
        elif dc >= defcon_scale.get("median", DEFCON_MEDIAN):
            mean_pts *= 1.10
            per.append({"note": "DefCon +10% (above-median defender)"})
    mean_pts *= health_weight(p)
    return round(mean_pts, 2), round(avg_fdr, 2), per


# ===============================================================
# CAPTAINCY  (V1 five-factor, weights frozen)
# ===============================================================
def captain_score(p, fx, form):
    """Returns (score 0-10, verdict, factor breakdown)."""
    h2h_delta, _ = h2h_modifier_for(fx.get("team_h_id", 0), fx.get("opp", 0),
                                    p["element_type"])
    f, mod = smart_fdr(fx["fdr"], p["element_type"], fx["opp"], form,
                       h2h_delta)
    fixture_score = 10 - (f - 1) * 2.5
    form_score = min(10.0, float(p.get("form") or 0) * 1.25)
    if p["element_type"] in (1, 2):
        dc = float(p.get("defensive_contribution_per_90") or 0)
        underlying = min(10.0, dc * 0.8)
    else:
        xgi = float(p.get("expected_goal_involvements_per_90") or 0)
        underlying = min(10.0, xgi * 12.0)
    pen = p.get("penalties_order") or 99
    crn = p.get("corners_and_indirect_freekicks_order") or 99
    fk = p.get("direct_freekicks_order") or 99
    role = 0.0
    if pen == 1:
        role = 10.0
    elif pen == 2:
        role = 7.0
    elif pen == 3:
        role = 5.0
    role = max(role, {1: 6.0, 2: 4.0, 3: 2.0}.get(crn, 0.0),
               {1: 5.0, 2: 3.0}.get(fk, 0.0))
    ownership = min(10.0, float(p.get("selected_by_percent") or 0) / 8.0)
    score = (CAPTAIN_W["fixture"] * fixture_score +
             CAPTAIN_W["form"] * form_score +
             CAPTAIN_W["underlying"] * underlying +
             CAPTAIN_W["role"] * role +
             CAPTAIN_W["ownership"] * ownership)
    verdict = "SIT"
    for thr, name in CAPTAIN_VERDICT:
        if score >= thr:
            verdict = name
            break
    return round(score, 2), verdict, {
        "fixture": round(fixture_score, 1), "form": round(form_score, 1),
        "underlying": round(underlying, 1), "role": round(role, 1),
        "ownership": round(ownership, 1), "smart_fdr": round(f, 2),
        "dynamic_mod": mod}


# ===============================================================
# LINEUP + BENCH (formation-legal XI, auto-sub aware bench order)
# ===============================================================
FORMATION = {"gk": (1, 1), "def": (3, 5), "mid": (2, 5), "fwd": (1, 3)}
POS_SLOT = {1: "gk", 2: "def", 3: "mid", 4: "fwd"}


def pick_best_xi(ranked):
    """Greedy: take best-projected players subject to per-slot maxima,
    then trim to exactly 11 while respecting per-slot minima."""
    xi, bench = [], []
    counts = {"gk": 0, "def": 0, "mid": 0, "fwd": 0}
    for row in ranked:
        slot = POS_SLOT[row["pos"]]
        _lo, hi = FORMATION[slot]
        if counts[slot] < hi:
            xi.append(row)
            counts[slot] += 1
        else:
            bench.append(row)
    # trim to exactly 11: drop the lowest-projected player whose slot
    # stays at or above its minimum
    xi.sort(key=lambda r: r["proj"], reverse=True)
    while len(xi) > 11:
        dropped = False
        for i in range(len(xi) - 1, -1, -1):
            slot = POS_SLOT[xi[i]["pos"]]
            lo, _hi = FORMATION[slot]
            if counts[slot] > lo:
                bench.append(xi.pop(i))
                counts[slot] -= 1
                dropped = True
                break
        if not dropped:
            break
    # guarantee minimums (3 DEF / 2 MID / 1 FWD / 1 GK)
    for slot, (lo, _hi) in FORMATION.items():
        while counts[slot] < lo and bench:
            take = next((r for r in bench if POS_SLOT[r["pos"]] == slot),
                        None)
            if take is None:
                break
            bench.remove(take)
            xi.append(take)
            counts[slot] += 1
    return xi, bench


def bench_reliability(p, games_played):
    ch = p.get("chance_of_playing_next_round")
    if ch is None:
        ch = p.get("chance_of_playing_this_round")
    ch = 100 if ch is None else float(ch)
    starts = float(p.get("starts") or 0)
    rate = starts / max(1.0, float(games_played or 1))
    if ch >= 75 and rate >= 0.60:
        return "Reliable", ch, rate
    if ch < 75:
        return "INJURY FLAG", ch, rate
    return "Rotation risk", ch, rate


def order_bench(bench_rows):
    """GK sub first (FPL auto-sub), then by P(play) x projection."""
    gk = [r for r in bench_rows if r["pos"] == 1]
    out = [r for r in bench_rows if r["pos"] != 1]
    out.sort(key=lambda r: (r.get("play_prob", 100) *
                            max(r["proj"], 0.1)), reverse=True)
    return gk + out


# ===============================================================
# TRANSFER ENGINE (value floor + true market scan, zero-hit default)
# ===============================================================
def banked_fts(history_rows, upto_gw):
    """FTs banked, flag-free, from completed GWs. WC/FH weeks freeze the bank."""
    banked = 0
    for row in history_rows:
        gw = row.get("event")
        if gw is None or gw >= upto_gw:
            break
        t = row.get("event_transfers") or 0
        cost = row.get("event_transfers_cost") or 0
        hits = int(cost) // 4
        banked = banked + 1 - t + hits
        banked = max(0, min(FT_BANK_CAP, banked))
    return banked


def sell_price_note(p):
    """Public picks expose no purchase price, so budget uses current price.
    FPL keeps half of any price profit when you sell - flagged when relevant."""
    rise = int(p.get("cost_change_start") or 0)
    if rise > 0:
        return (f"Sells near {p['now_cost'] / 10:.1f}m; FPL keeps half of the "
                f"{rise / 10:.1f}m rise since GW1 - true bank may be lower.")
    return None


def market_scan(players, owned_ids, pos, max_price, fx_map, form, horizon,
                use_defcon, defcon_scale, limit=5):
    rows = []
    for pid, p in players.items():
        if pid in owned_ids or p["element_type"] != pos:
            continue
        if p.get("status") != "a" or (p.get("minutes") or 0) < 90:
            continue
        if (p["now_cost"] / 10.0) > max_price + 1e-9:
            continue
        fxs = fx_map.get(p["team"], [])[:horizon]
        if not fxs:
            continue
        proj, avg_fdr, per = project_player(p, fxs, form, horizon,
                                            use_defcon, defcon_scale)
        rows.append({"id": pid, "name": p["web_name"],
                     "team": p["team"], "pos": pos,
                     "price": p["now_cost"] / 10.0,
                     "proj": proj, "avg_fdr": avg_fdr,
                     "form": float(p.get("form") or 0),
                     "sel": float(p.get("selected_by_percent") or 0),
                     "run": per})
    rows.sort(key=lambda r: r["proj"], reverse=True)
    return rows[:limit]


# ===============================================================
# CHIPS LEDGER (local file is authoritative pre-deadline)
# ===============================================================
CHIP_SET1 = ["wildcard", "freehit", "3xc", "bboost"]
CHIP_LABEL = {"wildcard": "Wildcard", "freehit": "Free Hit",
              "3xc": "Triple Captain", "bboost": "Bench Boost"}
SET2_START_GW = 20


def chips_state(history_rows, next_gw):
    ledger = _read_json(CHIPS_FILE, {"played": {}, "plan": {}, "notes": ""})
    played = dict(ledger.get("played", {}))
    for row in history_rows:                      # self-heal from API rows
        gw, pts = row.get("event"), row.get("event_transfers")
        if gw and pts and pts >= 8 and gw not in played:
            played[gw] = "wildcard"               # large squad turnover
    remaining_s1 = [c for c in CHIP_SET1 if c not in played.values()]
    active = None
    for gw, chip in played.items():
        if int(gw) == next_gw:
            active = chip
    return {"played": played, "plan": ledger.get("plan", {}),
            "notes": ledger.get("notes", ""),
            "remaining_set1": remaining_s1,
            "active": active,
            "set2_available_from": SET2_START_GW}


# ===============================================================
# PRICE RADAR (transfer flow + official price-change projections)
# ===============================================================
def price_alerts(squad_rows):
    alerts = []
    for r in squad_rows:
        p = r.get("_raw") or {}
        net = (p.get("transfers_in_event") or 0) - \
              (p.get("transfers_out_event") or 0)
        proj = p.get("price_change_projections") or []
        likelihood = proj[0].get("likelihood") if proj else None
        pct = proj[0].get("projected_percent") if proj else None
        try:
            pct = float(pct) if pct is not None else None
        except Exception:
            pct = None
        if likelihood is not None and int(likelihood) <= -1:
            alerts.append({"player": r["name"], "type": "fall",
                           "net": net, "pct": pct,
                           "likelihood": int(likelihood)})
        elif net <= PRICE_ALERT_NET:
            alerts.append({"player": r["name"], "type": "fall",
                           "net": net, "pct": pct, "likelihood": None})
        elif likelihood is not None and int(likelihood) >= 2:
            alerts.append({"player": r["name"], "type": "rise",
                           "net": net, "pct": pct,
                           "likelihood": int(likelihood)})
    return alerts


def snapshot_prices(players):
    """Persist now_cost snapshot for week-over-week risers/fallers."""
    prev = _read_json(PRICES_FILE, {})
    cur = {str(pid): p["now_cost"] for pid, p in players.items()}
    _write_json(PRICES_FILE, cur)
    if not prev:
        return []
    deltas = []
    for pid, cost in cur.items():
        old = prev.get(pid)
        if old is not None and old != cost:
            deltas.append({"id": int(pid), "delta": (cost - old) / 10.0})
    return deltas


# ===============================================================
# ML DATA HOOK (projection vs actual -> ml_training_data.csv)
# ===============================================================
ML_HEADER = ["date", "team_id", "gw", "projected_score", "actual_score",
             "captain", "captain_proj", "captain_actual", "engine_version"]


def log_ml_row(row):
    try:
        exists = os.path.exists(ML_FILE)
        with open(ML_FILE, "a", encoding="utf-8", newline="") as f:
            if not exists:
                f.write(",".join(ML_HEADER) + "\n")
            f.write(",".join('"%s"' % str(v).replace('"', "'")
                             for v in row) + "\n")
        return True
    except Exception:
        return False


def log_actual_result(team_id, gw, actual, captain_actual=""):
    """Fill the actual score into the newest projection row for that GW.
    Appends a fresh row if no projection exists yet."""
    try:
        lines = []
        if os.path.exists(ML_FILE):
            with open(ML_FILE, "r", encoding="utf-8") as f:
                lines = [l for l in f.read().splitlines() if l.strip()]
        if lines:
            rows = [l.split('","') for l in lines]
            rows = [[c.strip('"') for c in r] for r in rows]
            target = None
            for i in range(len(rows) - 1, 0, -1):
                try:
                    if int(rows[i][1]) == int(team_id) and \
                            int(rows[i][2]) == int(gw):
                        target = i
                        break
                except Exception:
                    continue
            if target is not None:
                rows[target][4] = str(actual)
                if captain_actual:
                    rows[target][7] = str(captain_actual)
                with open(ML_FILE, "w", encoding="utf-8", newline="") as f:
                    f.write(lines[0] + "\n")           # header stays clean
                    for r in rows[1:]:
                        f.write(",".join('"%s"' % c for c in r) + "\n")
                return True
        return log_ml_row([datetime.now(timezone.utc).strftime(
            "%Y-%m-%d %H:%M"), team_id, gw, "", actual, "", "", "",
            "V2.0"])
    except Exception:
        return False


def ml_accuracy():
    rows = []
    try:
        with open(ML_FILE, "r", encoding="utf-8") as f:
            lines = [l for l in f.read().splitlines() if l.strip()][1:]
        for l in lines:
            parts = [x.strip('"') for x in l.split('","')]
            if len(parts) >= 5 and parts[4]:
                rows.append(parts)
    except Exception:
        return None
    if not rows:
        return None
    errs, n = [], 0
    for r in rows:
        try:
            proj, act = float(r[3]), float(r[4])
            errs.append(abs(proj - act) / max(act, 1))
            n += 1
        except Exception:
            pass
    return {"weeks": n, "mean_abs_pct_error":
            round(100 * sum(errs) / max(1, len(errs)), 1)} if n else None


# ===============================================================
# ENGINE ENTRYPOINT
# ===============================================================
def run_engine(team_id, horizon=1, use_defcon=False):
    """One call -> everything the Command Center renders."""
    players, teams, events = fetch_bootstrap()
    fixtures = fetch_fixtures()
    gwinfo = next_gw_info(events)
    gw = gwinfo["gw"]
    history = fetch_entry_history(team_id)
    hist_rows = history.get("current", [])
    games_played = max(1, gw - 1)

    squad_info = resolve_squad(team_id, gw, players, teams)
    ids = squad_info["picks"] or []
    if not ids:
        return {"error": ("No squad could be resolved for team "
                          f"{team_id}. Check the team ID and v2_squad.json.")}

    form = team_form(gw, fixtures)
    fx_map = fixtures_map(gw, max(horizon, 8), fixtures, teams)
    fx1 = fixtures_map(gw, 1, fixtures, teams)

    # defenders' DefCon scale from live data (frozen thresholds, live ranks)
    dcs = sorted(float(p.get("defensive_contribution_per_90") or 0)
                 for p in players.values()
                 if p["element_type"] == 2 and (p.get("minutes") or 0) > 450)
    defcon_scale = ({"median": dcs[len(dcs) // 2],
                     "p75": dcs[int(len(dcs) * 0.75)]} if len(dcs) > 8 else
                    {"median": DEFCON_MEDIAN, "p75": DEFCON_P75})

    # ---- squad rows ----
    squad_rows = []
    for pid in ids:
        p = players.get(pid)
        if not p:
            continue
        fxs = fx_map.get(p["team"], [])[:horizon]
        proj, avg_fdr, per = project_player(p, fxs, form, horizon,
                                            use_defcon, defcon_scale)
        rel, ch, rate = bench_reliability(p, games_played)
        squad_rows.append({"id": pid, "name": p["web_name"],
                           "pos": p["element_type"],
                           "pos_name": POS_NAME[p["element_type"]],
                           "team": teams[p["team"]]["short_name"],
                           "team_id": p["team"],
                           "price": p["now_cost"] / 10.0,
                           "form": float(p.get("form") or 0),
                           "proj": proj, "avg_fdr": avg_fdr, "run": per,
                           "reliability": rel, "play_prob": ch,
                           "start_rate": round(rate, 2),
                           "ep_next": float(p.get("ep_next") or 0),
                           "news": (p.get("news") or "").strip(),
                           "status": p.get("status"), "_raw": p})

    # ---- captaincy ----
    cap_rows = []
    for row in squad_rows:
        fxs = fx1.get(row["team_id"], [])
        if not fxs:
            continue
        fx = fxs[0]
        score, verdict, factors = captain_score(row["_raw"], fx, form)
        cap_rows.append({"row": row, "score": score, "verdict": verdict,
                         "factors": factors,
                         "fixture": f"{fx['opp_short']} ({fx['ha']})",
                         "proj": row["proj"]})
    cap_rows.sort(key=lambda c: c["score"], reverse=True)
    captain = cap_rows[0] if cap_rows else None
    vice = cap_rows[1] if len(cap_rows) > 1 else None

    # ---- lineup ----
    ranked = sorted(squad_rows, key=lambda r: (r["proj"], r["play_prob"]),
                    reverse=True)
    xi, bench = pick_best_xi(ranked)
    bench = order_bench(bench)
    xi_proj = round(sum(r["proj"] for r in xi), 1)
    bench_proj = round(sum(r["proj"] for r in bench), 1)

    xi_counts = {"gk": 0, "def": 0, "mid": 0, "fwd": 0}
    for r in xi:
        xi_counts[POS_SLOT[r["pos"]]] += 1
    cover = {"gk": any(r["pos"] == 1 for r in bench),
             "def": any(r["pos"] == 2 for r in bench),
             "mid": any(r["pos"] == 3 for r in bench),
             "fwd": any(r["pos"] == 4 for r in bench)}
    sub_warnings = []
    for slot, has in cover.items():
        if not has and xi_counts[slot] > 0:
            sub_warnings.append(
                f"No {slot.upper()} cover on the bench - an auto-sub cannot "
                f"replace a missing {slot.upper()} starter.")

    # ---- transfers ----
    chips = chips_state(hist_rows, gw)
    bank = squad_info.get("bank")
    if bank is None and hist_rows:
        bank = (hist_rows[-1].get("bank", 0) or 0) / 10.0
    fts = banked_fts(hist_rows, gw)
    wc_active = (squad_info.get("active_chip") == "wildcard" or
                 chips.get("active") == "wildcard")

    sell_cand, buy_rows, transfer_verdict, reason = None, [], "SAVE", ""
    if wc_active:
        transfer_verdict = "WILDCARD ACTIVE"
        reason = ("Unlimited transfers until the deadline - shape the squad "
                  "freely; banked free transfers are preserved.")
    else:
        cands = [r for r in squad_rows
                 if r["pos"] != 1                       # GK never auto-sold
                 and not (r["price"] >= 8.0)            # premium core exempt
                 and r["proj"] < VALUE_FLOOR]
        cands.sort(key=lambda r: r["proj"])
        if cands:
            sell_cand = cands[0]
            budget = sell_cand["price"] + (bank or 0.0)
            buy_rows = market_scan(players, set(ids), sell_cand["pos"],
                                   budget, fx_map, form, horizon,
                                   use_defcon, defcon_scale, limit=4)
            best = buy_rows[0] if buy_rows else None
            if best:
                gain = round(best["proj"] - sell_cand["proj"], 2)
                if fts > 0:
                    if gain >= SWAP_EDGE:
                        transfer_verdict = "TRANSFER"
                        reason = (f"Net gain {gain:+.1f} pts over the "
                                  f"horizon - clears the {SWAP_EDGE:.0f}-pt "
                                  f"edge with a free transfer.")
                    else:
                        reason = (f"Best move gains only {gain:+.1f} pts - "
                                  f"below the {SWAP_EDGE:.0f}-pt edge. "
                                  f"Save the free transfer.")
                else:
                    net = gain - HIT_COST
                    if net > 0:
                        transfer_verdict = "HIT"
                        reason = (f"Gain {gain:+.1f} pts minus the -4 hit = "
                                  f"{net:+.1f} net. Worth it, but no free "
                                  f"transfer left this week.")
                    else:
                        reason = (f"Gain {gain:+.1f} pts does not cover a "
                                  f"-4 hit. Hold.")
        else:
            reason = ("No squad member is under the "
                      f"{VALUE_FLOOR:.1f} pts/GW value floor - hold and "
                      "bank value.")

    # ---- price + swing + value ----
    alerts = price_alerts(squad_rows)
    price_deltas = snapshot_prices(players)
    try:
        import fixture_swing
        swings = fixture_swing.detect(fx_map, teams)
    except Exception:
        swings = []
    try:
        import value_tracker
        value = value_tracker.summarize(hist_rows, squad_rows)
    except Exception:
        value = None

    engine_out = {
        "team_name": fetch_team_name(team_id),
        "team_id": team_id,
        "gw": gw, "gw_name": gwinfo["name"],
        "deadline_epoch": gwinfo["deadline_epoch"],
        "deadline_iso": gwinfo["deadline_iso"],
        "squad_source": squad_info["source"],
        "squad_note": squad_info["note"],
        "horizon": horizon, "defcon": use_defcon,
        "bank": bank, "fts": fts, "wc_active": wc_active,
        "squad": [{k: v for k, v in r.items() if k != "_raw"}
                  for r in squad_rows],
        "captain": ({"name": captain["row"]["name"],
                     "team": captain["row"]["team"],
                     "id": captain["row"]["id"],
                     "score": captain["score"],
                     "verdict": captain["verdict"],
                     "factors": captain["factors"],
                     "fixture": captain["fixture"],
                     "proj": captain["row"]["proj"],
                     "price": captain["row"]["price"],
                     "ep_next": captain["row"]["ep_next"]}
                    if captain else None),
        "vice": ({"name": vice["row"]["name"], "score": vice["score"],
                  "verdict": vice["verdict"],
                  "fixture": vice["fixture"]} if vice else None),
        "xi": [{k: v for k, v in r.items() if k != "_raw"} for r in xi],
        "bench": [{k: v for k, v in r.items() if k != "_raw"} for r in bench],
        "xi_proj": xi_proj, "bench_proj": bench_proj,
        "sub_warnings": sub_warnings,
        "transfer": {"verdict": transfer_verdict, "reason": reason,
                     "sell": ({k: v for k, v in sell_cand.items()
                               if k != "_raw"} if sell_cand else None),
                     "buys": buy_rows,
                     "sell_note": (sell_price_note(sell_cand["_raw"])
                                   if sell_cand else None)},
        "chips": chips,
        "price_alerts": alerts,
        "price_deltas_since_last_run": price_deltas,
        "fixture_swings": swings,
        "value": value,
        "history": hist_rows[-8:],
        "captain_board": [{"name": c["row"]["name"], "score": c["score"],
                           "verdict": c["verdict"], "fixture": c["fixture"],
                           "proj": c["proj"], "factors": c["factors"]}
                          for c in cap_rows[:5]],
        "ml": ml_accuracy(),
    }

    # ML hook: persist this run's projection (local only, silent on cloud)
    if captain and xi_proj:
        log_ml_row([datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    team_id, gw, xi_proj, "",
                    captain["row"]["name"],
                    round(captain["row"]["proj"] * 2, 1), "", "V2.0"])
    return engine_out


# ===============================================================
# IDEAL XI (global template + custom add/swap for the UI)
# ===============================================================
def ideal_xi(engine_out, players=None, teams=None, fixtures=None,
             form=None, horizon=5, use_defcon=False, swap_in=None):
    """Global template XI + roadmap; optional custom player swap."""
    if players is None:
        players, teams, events = fetch_bootstrap()
        fixtures = fetch_fixtures()
        gwinfo = next_gw_info(events)
        gw = gwinfo["gw"]
        form = team_form(gw, fixtures)
    else:
        gw = engine_out["gw"]
    fx_map = fixtures_map(gw, horizon, fixtures, teams)
    dcs = sorted(float(p.get("defensive_contribution_per_90") or 0)
                 for p in players.values()
                 if p["element_type"] == 2 and (p.get("minutes") or 0) > 450)
    defcon_scale = ({"median": dcs[len(dcs) // 2],
                     "p75": dcs[int(len(dcs) * 0.75)]} if len(dcs) > 8 else
                    {"median": DEFCON_MEDIAN, "p75": DEFCON_P75})

    owned = set(r["id"] for r in engine_out["squad"])
    if swap_in:
        owned.discard(swap_in)
    template = {1: [], 2: [], 3: [], 4: []}
    for pid, p in players.items():
        if p.get("status") != "a" or (p.get("minutes") or 0) < 90:
            continue
        fxs = fx_map.get(p["team"], [])[:horizon]
        if not fxs:
            continue
        proj, avg_fdr, per = project_player(p, fxs, form, horizon,
                                            use_defcon, defcon_scale)
        template[p["element_type"]].append(
            {"id": pid, "name": p["web_name"],
             "team": teams[p["team"]]["short_name"],
             "pos_name": POS_NAME[p["element_type"]],
             "price": p["now_cost"] / 10.0, "proj": proj,
             "avg_fdr": avg_fdr, "run": per,
             "sel": float(p.get("selected_by_percent") or 0),
             "owned": pid in owned})
    for pos in template:
        template[pos].sort(key=lambda r: r["proj"], reverse=True)

    slots = {1: 1, 2: 4, 3: 4, 4: 2}
    xi = {}
    for pos, n in slots.items():
        rows = template[pos][:n]
        if swap_in and swap_in in {r["id"] for r in template[pos]} and \
                swap_in not in {r["id"] for r in rows}:
            forced = next(r for r in template[pos] if r["id"] == swap_in)
            rows = rows[:-1] + [forced]          # replace weakest slot
            rows.sort(key=lambda r: r["proj"], reverse=True)
        xi[POS_NAME[pos]] = rows
    cost = sum(r["price"] for rows in xi.values() for r in rows)
    missing = [{"name": r["name"], "team": r["team"],
                "pos_name": r["pos_name"], "price": r["price"],
                "proj": r["proj"]}
               for rows in xi.values() for r in rows if not r["owned"]]
    return {"xi": xi, "cost": round(cost, 1), "missing": missing,
            "swap_in": swap_in}


# ===============================================================
# NAME RESOLVER (seed sync by names - pre_gwplan pattern)
# ===============================================================
def resolve_names(name_list, players, teams):
    """Fuzzy name -> id resolution for workbench sync."""
    resolved, misses = [], []
    norm = {}
    for pid, p in players.items():
        norm.setdefault(p["web_name"].lower().replace(" ", ""), []).append(p)
        full = (p["first_name"] + " " + p["second_name"]).lower()
        norm.setdefault(full, []).append(p)
    for entry in name_list:
        name = entry.strip().lower().replace(" ", "")
        hits = norm.get(name, [])
        for alt in (name.lstrip("n."), name.replace(".", "")):
            if len(hits) != 1:
                hits = norm.get(alt, hits)
        if len(hits) == 1:
            resolved.append((hits[0]["id"], hits[0]["web_name"],
                             teams[hits[0]["team"]]["short_name"]))
        else:
            misses.append(entry)
    return resolved, misses
