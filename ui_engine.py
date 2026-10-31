# ui_engine.py — FPL Toolz V2 "Command Center" Engine
import json
import os
import time
import tempfile
from datetime import datetime, timezone
import requests

try:
    from h2h_adjuster import h2h_modifier_for
except Exception:
    def h2h_modifier_for(team_h, team_a, position):
        return 0.0, ""

BASE_URL = "https://fantasy.premierleague.com/api/"

FDR_LOOKBACK_GW = 3
POS_FLOOR = {1: 2.0, 2: 2.0, 3: 3.0, 4: 2.0}
PTS_MULT = {1: 1.20, 2: 1.05, 3: 0.90, 4: 0.78, 5: 0.65}
CAPTAIN_W = {"fixture": 0.35, "form": 0.25, "underlying": 0.20, "role": 0.10, "ownership": 0.10}
CAPTAIN_VERDICT = [(8.5, "STRONG LOCK"), (7.0, "SOLID"), (5.5, "LEAN")]
VALUE_FLOOR = 3.0
SWAP_EDGE = 4.0
HIT_COST = 4
FT_BANK_CAP = 5
DEFCON_MEDIAN = 7.39
DEFCON_P75 = 9.37
PRICE_ALERT_NET = -50000
POS_NAME = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

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
    now = time.time()
    key = path + (json.dumps(params, sort_keys=True) if params else "")
    hit = _TTL.get(key)
    
    if hit and now - hit[0] < ttl:
        return hit[1]
        
    try:
        r = requests.get(BASE_URL + path, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        _TTL[key] = (now, data)
        return data
    except requests.RequestException as e:
        if hit:
            return hit[1] # Return stale cache if API fails
        raise Exception("FPL API is currently unavailable (Rate limited or Server Error). Please try again in a few minutes.")

def clear_cache():
    _TTL.clear()

def fetch_bootstrap():
    data = get_json("bootstrap-static/", ttl=600)
    players = {p["id"]: p for p in data["elements"]}
    teams = {t["id"]: t for t in data["teams"]}
    events = data["events"]
    return players, teams, events

def fetch_fixtures():
    return get_json("fixtures/", ttl=600)

def next_gw_info(events):
    for e in events:
        if e.get("is_next"):
            return {"gw": e["id"], "name": e["name"], "deadline_epoch": e.get("deadline_time_epoch")}
    return {"gw": 1, "name": "GW1", "deadline_epoch": None}

def fetch_entry_history(team_id):
    return get_json(f"entry/{team_id}/history/", ttl=300)

def fetch_entry_picks(team_id, gw):
    try: return get_json(f"entry/{team_id}/event/{gw}/picks/", ttl=120)
    except Exception: return None

def fetch_team_name(team_id):
    try: return get_json(f"entry/{team_id}/", ttl=3600).get("name", f"Team {team_id}")
    except Exception: return f"Team {team_id}"

def team_form(gw, fixtures):
    stats = {}
    for f in fixtures:
        if not f.get("finished") or f.get("event") is None: continue
        if f["event"] < gw - FDR_LOOKBACK_GW or f["event"] >= gw: continue
        h, a = f["team_h"], f["team_a"]
        hs, as_ = f.get("team_h_score") or 0, f.get("team_a_score") or 0
        for tid, sc, con in ((h, hs, as_), (a, as_, hs)):
            d = stats.setdefault(tid, {"scored": 0, "conceded": 0, "games": 0})
            d["scored"] += sc; d["conceded"] += con; d["games"] += 1
    return stats

def smart_fdr(base_fdr, pos, opp_id, form, h2h_delta=0.0):
    opp = form.get(opp_id, {"scored": 3, "conceded": 3})
    modifier = 0
    if pos in (1, 2):
        if opp["scored"] >= 5: modifier = 1
        elif opp["scored"] <= 1: modifier = -1
    else:
        if opp["conceded"] >= 5: modifier = -1
        elif opp["conceded"] <= 1: modifier = 1
    return max(1, min(5, base_fdr + modifier + h2h_delta)), modifier

def fixtures_map(gw_start, horizon, fixtures, teams):
    out = {}
    for f in fixtures:
        ev = f.get("event")
        if ev is None or not (gw_start <= ev < gw_start + horizon): continue
        for me, opp, fdr, ha in ((f["team_h"], f["team_a"], f["team_h_difficulty"], "H"), (f["team_a"], f["team_h"], f["team_a_difficulty"], "A")):
            out.setdefault(me, []).append({"gw": ev, "opp": opp, "opp_short": teams[opp]["short_name"], "ha": ha, "fdr": fdr})
    return out

def resolve_squad(team_id, gw, players, teams):
    info = {"source": None, "note": "", "picks": None, "bank": None, "captain_id": None, "vice_id": None}
    p = fetch_entry_picks(team_id, gw)
    if p is not None:
        info.update({"source": "api_locked", "note": f"Official GW{gw} squad.", "picks": [x["element"] for x in p["picks"]], "bank": (p.get("entry_history", {}).get("bank", 0) or 0) / 10.0, "active_chip": p.get("active_chip")})
        for pick in p["picks"]:
            if pick.get("is_captain"): info["captain_id"] = pick["element"]
            if pick.get("is_vice_captain"): info["vice_id"] = pick["element"]
        return info

    seed = _read_json(SEED_FILE, None)
    if seed and seed.get("gw") == gw and seed.get("players"):
        info.update({"source": "seed", "note": "Pre-deadline workbench squad (v2_squad.json).", "picks": [pl["id"] for pl in seed["players"]], "bank": seed.get("itb"), "captain_id": seed.get("captain_id"), "vice_id": seed.get("vice_id"), "active_chip": seed.get("active_chip")})
        return info

    for back in range(1, 4):
        p = fetch_entry_picks(team_id, gw - back)
        if p is not None:
            info.update({"source": "api_previous", "note": f"GW{gw - back} squad (last locked truth).", "picks": [x["element"] for x in p["picks"]], "bank": (p.get("entry_history", {}).get("bank", 0) or 0) / 10.0})
            for pick in p["picks"]:
                if pick.get("is_captain"): info["captain_id"] = pick["element"]
                if pick.get("is_vice_captain"): info["vice_id"] = pick["element"]
            return info
    return info

def save_seed(gw, player_ids, captain_id=None, vice_id=None, itb=None, active_chip=None):
    seed = {"gw": gw, "updated": datetime.now(timezone.utc).isoformat(), "players": [{"id": i} for i in player_ids], "captain_id": captain_id, "vice_id": vice_id, "itb": itb, "active_chip": active_chip}
    return _write_json(SEED_FILE, seed)

def health_weight(p):
    val = p.get("chance_of_playing_next_round") or p.get("chance_of_playing_this_round")
    return 1.0 if val is None else max(0.25, min(1.0, float(val) / 100.0))

def baseline_ppg(p):
    form = float(p.get("form") or 0)
    return form if (p.get("minutes") or 0) >= 90 and form > 0 else POS_FLOOR[p["element_type"]]

def project_player(p, fxs, form, use_defcon=False, defcon_scale=None):
    if not fxs: return 0.0, 3.0, []
    base = baseline_ppg(p)
    per = []
    for fx in fxs:
        h2h_delta, _ = h2h_modifier_for(fx.get("team_h_id", 0), fx.get("opp", 0), p["element_type"])
        f, _mod = smart_fdr(fx["fdr"], p["element_type"], fx["opp"], form, h2h_delta)
        per.append({"gw": fx["gw"], "opp": fx["opp_short"], "ha": fx["ha"], "fdr": round(f, 2), "pts": round(base * PTS_MULT[int(round(f))], 2)})
    mean_pts = sum(x["pts"] for x in per) / len(per)
    avg_fdr = sum(x["fdr"] for x in per) / len(per)
    if use_defcon and p["element_type"] == 2 and defcon_scale:
        dc = float(p.get("defensive_contribution_per_90") or 0)
        if dc >= defcon_scale.get("p75", DEFCON_P75): mean_pts *= 1.20
        elif dc >= defcon_scale.get("median", DEFCON_MEDIAN): mean_pts *= 1.10
    return round(mean_pts * health_weight(p), 2), round(avg_fdr, 2), per

def captain_score(p, fx, form):
    h2h_delta, _ = h2h_modifier_for(fx.get("team_h_id", 0), fx.get("opp", 0), p["element_type"])
    f, mod = smart_fdr(fx["fdr"], p["element_type"], fx["opp"], form, h2h_delta)
    fixture_score = 10 - (f - 1) * 2.5
    form_score = min(10.0, float(p.get("form") or 0) * 1.25)
    if p["element_type"] in (1, 2): underlying = min(10.0, float(p.get("defensive_contribution_per_90") or 0) * 0.8)
    else: underlying = min(10.0, float(p.get("expected_goal_involvements_per_90") or 0) * 12.0)
    pen = p.get("penalties_order") or 99
    crn = p.get("corners_and_indirect_freekicks_order") or 99
    role = 10.0 if pen == 1 else 7.0 if pen == 2 else 5.0 if pen == 3 else max({1: 6.0, 2: 4.0, 3: 2.0}.get(crn, 0.0), 4.0)
    own = min(10.0, float(p.get("selected_by_percent") or 0) / 8.0)
    score = (CAPTAIN_W["fixture"] * fixture_score + CAPTAIN_W["form"] * form_score + CAPTAIN_W["underlying"] * underlying + CAPTAIN_W["role"] * role + CAPTAIN_W["ownership"] * own)
    verdict = "SIT"
    for thr, name in CAPTAIN_VERDICT:
        if score >= thr: verdict = name; break
    return round(score, 2), verdict, {"fixture": round(fixture_score, 1), "form": round(form_score, 1), "underlying": round(underlying, 1), "role": round(role, 1), "ownership": round(own, 1), "smart_fdr": round(f, 2), "dynamic_mod": mod}

FORMATION = {"gk": (1, 1), "def": (3, 5), "mid": (2, 5), "fwd": (1, 3)}
POS_SLOT = {1: "gk", 2: "def", 3: "mid", 4: "fwd"}

def pick_best_xi(ranked):
    xi, bench, counts = [], [], {"gk": 0, "def": 0, "mid": 0, "fwd": 0}
    for row in ranked:
        slot = POS_SLOT[row["pos"]]
        if counts[slot] < FORMATION[slot][1]: xi.append(row); counts[slot] += 1
        else: bench.append(row)
    xi.sort(key=lambda r: r["proj"], reverse=True)
    while len(xi) > 11:
        for i in range(len(xi) - 1, -1, -1):
            slot = POS_SLOT[xi[i]["pos"]]
            if counts[slot] > FORMATION[slot][0]:
                bench.append(xi.pop(i)); counts[slot] -= 1; break
        else: break
    for slot, (lo, _) in FORMATION.items():
        while counts[slot] < lo and bench:
            take = next((r for r in bench if POS_SLOT[r["pos"]] == slot), None)
            if not take: break
            bench.remove(take); xi.append(take); counts[slot] += 1
    return xi, bench

def bench_reliability(p, games_played):
    ch = p.get("chance_of_playing_next_round") or p.get("chance_of_playing_this_round")
    ch = 100 if ch is None else float(ch)
    rate = float(p.get("starts") or 0) / max(1.0, float(games_played or 1))
    return ("Reliable", ch, rate) if ch >= 75 and rate >= 0.60 else ("INJURY FLAG", ch, rate) if ch < 75 else ("Rotation risk", ch, rate)

def order_bench(bench_rows):
    gk = [r for r in bench_rows if r["pos"] == 1]
    out = sorted([r for r in bench_rows if r["pos"] != 1], key=lambda r: (r.get("play_prob", 100) * max(r["proj"], 0.1)), reverse=True)
    return gk + out

def banked_fts(history_rows, upto_gw):
    banked = 0
    for row in history_rows:
        gw = row.get("event")
        if gw is None or gw >= upto_gw: break
        t, cost = row.get("event_transfers") or 0, row.get("event_transfers_cost") or 0
        banked = max(0, min(FT_BANK_CAP, banked + 1 - t + (int(cost) // 4)))
    return banked

def market_scan(players, owned_ids, pos, max_price, fx_map, form, horizon, use_defcon, defcon_scale, limit=5):
    rows = []
    for pid, p in players.items():
        if pid in owned_ids or p["element_type"] != pos or p.get("status") != "a" or (p.get("minutes") or 0) < 90 or (p["now_cost"] / 10.0) > max_price + 1e-9: continue
        fxs = fx_map.get(p["team"], [])[:horizon]
        if not fxs: continue
        proj, avg_fdr, per = project_player(p, fxs, form, use_defcon, defcon_scale)
        rows.append({"id": pid, "name": p["web_name"], "team": p["team"], "pos": pos, "price": p["now_cost"] / 10.0, "proj": proj, "avg_fdr": avg_fdr, "form": float(p.get("form") or 0), "sel": float(p.get("selected_by_percent") or 0), "run": per})
    rows.sort(key=lambda r: r["proj"], reverse=True)
    return rows[:limit]

CHIP_SET1 = ["wildcard", "freehit", "3xc", "bboost"]
CHIP_LABEL = {"wildcard": "Wildcard", "freehit": "Free Hit", "3xc": "Triple Captain", "bboost": "Bench Boost"}

def chips_state(history_rows, next_gw):
    ledger = _read_json(CHIPS_FILE, {"played": {}, "plan": {}, "notes": ""})
    played = dict(ledger.get("played", {}))
    for row in history_rows:
        gw, pts = row.get("event"), row.get("event_transfers")
        if gw and pts and pts >= 8 and gw not in played: played[gw] = "wildcard"
    return {"played": played, "plan": ledger.get("plan", {}), "notes": ledger.get("notes", ""), "remaining_set1": [c for c in CHIP_SET1 if c not in played.values()], "active": next((chip for gw, chip in played.items() if int(gw) == next_gw), None), "set2_available_from": 20}

def price_alerts(squad_rows):
    alerts = []
    for r in squad_rows:
        p = r.get("_raw") or {}
        net = (p.get("transfers_in_event") or 0) - (p.get("transfers_out_event") or 0)
        proj = p.get("price_change_projections") or []
        likelihood = proj[0].get("likelihood") if proj else None
        pct = float(proj[0].get("projected_percent")) if proj and proj[0].get("projected_percent") is not None else None
        if likelihood is not None and int(likelihood) <= -1: alerts.append({"player": r["name"], "type": "fall", "net": net, "pct": pct, "likelihood": int(likelihood)})
        elif net <= PRICE_ALERT_NET: alerts.append({"player": r["name"], "type": "fall", "net": net, "pct": pct, "likelihood": None})
        elif likelihood is not None and int(likelihood) >= 2: alerts.append({"player": r["name"], "type": "rise", "net": net, "pct": pct, "likelihood": int(likelihood)})
    return alerts

def snapshot_prices(players):
    prev = _read_json(PRICES_FILE, {})
    cur = {str(pid): p["now_cost"] for pid, p in players.items()}
    _write_json(PRICES_FILE, cur)
    if not prev: return []
    return [{"id": int(pid), "delta": (cost - prev[pid]) / 10.0} for pid, cost in cur.items() if pid in prev and prev[pid] != cost]

ML_HEADER = ["date", "team_id", "gw", "projected_score", "actual_score", "captain", "captain_proj", "captain_actual", "engine_version"]

def log_ml_row(row):
    try:
        exists = os.path.exists(ML_FILE)
        with open(ML_FILE, "a", encoding="utf-8", newline="") as f:
            if not exists: f.write(",".join(ML_HEADER) + "\n")
            f.write(",".join('"%s"' % str(v).replace('"', "'") for v in row) + "\n")
        return True
    except Exception: return False

def log_actual_result(team_id, gw, actual):
    try:
        lines = []
        if os.path.exists(ML_FILE):
            with open(ML_FILE, "r", encoding="utf-8") as f: lines = [l for l in f.read().splitlines() if l.strip()]
        if lines:
            rows = [[c.strip('"') for c in l.split('","')] for l in lines]
            target = next((i for i in range(len(rows) - 1, 0, -1) if int(rows[i][1]) == int(team_id) and int(rows[i][2]) == int(gw)), None)
            if target is not None:
                rows[target][4] = str(actual)
                with open(ML_FILE, "w", encoding="utf-8", newline="") as f:
                    f.write(lines[0] + "\n")
                    for r in rows[1:]: f.write(",".join('"%s"' % c for c in r) + "\n")
                return True
        return log_ml_row([datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), team_id, gw, "", actual, "", "", "", "V2.0"])
    except Exception: return False

def ml_accuracy():
    rows = []
    try:
        with open(ML_FILE, "r", encoding="utf-8") as f: lines = [l for l in f.read().splitlines() if l.strip()][1:]
        rows = [[x.strip('"') for x in l.split('","')] for l in lines if len(l.split('","')) >= 5 and l.split('","')[4]]
    except Exception: return None
    errs = [abs(float(r[3]) - float(r[4])) / max(float(r[4]), 1) for r in rows if r[3] and r[4]]
    return {"weeks": len(errs), "mean_abs_pct_error": round(100 * sum(errs) / max(1, len(errs)), 1)} if errs else None

def run_engine(team_id, horizon=1, use_defcon=False, override_seed=None):
    players, teams, events = fetch_bootstrap()
    fixtures = fetch_fixtures()
    gwinfo = next_gw_info(events)
    gw = gwinfo["gw"]
    history = fetch_entry_history(team_id)
    hist_rows = history.get("current", [])
    games_played = max(1, gw - 1)

    squad_info = override_seed if override_seed else resolve_squad(team_id, gw, players, teams)
    ids = squad_info["picks"] or []
    if not ids: return {"error": f"No squad could be resolved for team {team_id}."}

    form = team_form(gw, fixtures)
    fx_map = fixtures_map(gw, max(horizon, 8), fixtures, teams)
    fx1 = fixtures_map(gw, 1, fixtures, teams)
    dcs = sorted(float(p.get("defensive_contribution_per_90") or 0) for p in players.values() if p["element_type"] == 2 and (p.get("minutes") or 0) > 450)
    defcon_scale = {"median": dcs[len(dcs) // 2], "p75": dcs[int(len(dcs) * 0.75)]} if len(dcs) > 8 else {"median": DEFCON_MEDIAN, "p75": DEFCON_P75}

    squad_rows = []
    for pid in ids:
        p = players.get(pid)
        if not p: continue
        proj, avg_fdr, per = project_player(p, fx_map.get(p["team"], [])[:horizon], form, use_defcon, defcon_scale)
        rel, ch, rate = bench_reliability(p, games_played)
        squad_rows.append({"id": pid, "name": p["web_name"], "pos": p["element_type"], "pos_name": POS_NAME[p["element_type"]], "team": teams[p["team"]]["short_name"], "team_id": p["team"], "price": p["now_cost"] / 10.0, "form": float(p.get("form") or 0), "proj": proj, "avg_fdr": avg_fdr, "run": per, "reliability": rel, "play_prob": ch, "start_rate": round(rate, 2), "ep_next": float(p.get("ep_next") or 0), "news": (p.get("news") or "").strip(), "status": p.get("status"), "_raw": p})

    cap_rows = []
    for row in squad_rows:
        fxs = fx1.get(row["team_id"], [])
        if fxs:
            fx = fxs[0]
            score, verdict, factors = captain_score(row["_raw"], fx, form)
            cap_rows.append({"row": row, "score": score, "verdict": verdict, "factors": factors, "fixture": f"{fx['opp_short']} ({fx['ha']})", "proj": row["proj"]})
    cap_rows.sort(key=lambda c: c["score"], reverse=True)
    
    ranked = sorted(squad_rows, key=lambda r: (r["proj"], r["play_prob"]), reverse=True)
    xi, bench = pick_best_xi(ranked)
    bench = order_bench(bench)
    
    chips = chips_state(hist_rows, gw)
    bank = squad_info.get("bank") or (hist_rows[-1].get("bank", 0) or 0) / 10.0 if hist_rows else 0.0
    fts = banked_fts(hist_rows, gw)
    wc_active = (squad_info.get("active_chip") == "wildcard" or chips.get("active") == "wildcard")

    sell_cand, buy_rows, transfer_verdict, reason = None, [], "SAVE", ""
    if wc_active:
        transfer_verdict, reason = "WILDCARD ACTIVE", "Unlimited transfers. Top market upgrades:"
        buy_rows = market_scan(players, set(ids), 4, 15.0, fx_map, form, horizon, use_defcon, defcon_scale, limit=3)
    else:
        cands = sorted([r for r in squad_rows if r["pos"] != 1 and r["price"] < 8.0 and r["proj"] < VALUE_FLOOR], key=lambda r: r["proj"])
        if cands:
            sell_cand = cands[0]
            buy_rows = market_scan(players, set(ids), sell_cand["pos"], sell_cand["price"] + bank, fx_map, form, horizon, use_defcon, defcon_scale, limit=4)
            best = buy_rows[0] if buy_rows else None
            if best:
                gain = round(best["proj"] - sell_cand["proj"], 2)
                if fts > 0 and gain >= SWAP_EDGE: transfer_verdict, reason = "TRANSFER", f"Net gain {gain:+.1f} pts (clears edge)."
                elif fts == 0 and (gain - HIT_COST) > 0: transfer_verdict, reason = "HIT", f"Net gain {gain - HIT_COST:+.1f} after -4 hit."
                else: reason = f"Best move gains only {gain:+.1f} pts. Save transfer."
        else: reason = f"No players under {VALUE_FLOOR:.1f} pts/GW value floor."

    try: swings = __import__('fixture_swing').detect(fx_map, teams)
    except Exception: swings = []
    try: value = __import__('value_tracker').summarize(hist_rows, squad_rows)
    except Exception: value = None

    engine_out = {
        "team_name": fetch_team_name(team_id), "team_id": team_id, "gw": gw, "gw_name": gwinfo["name"], "deadline_epoch": gwinfo["deadline_epoch"],
        "squad_source": squad_info["source"], "squad_note": squad_info["note"], "horizon": horizon, "defcon": use_defcon,
        "bank": bank, "fts": fts, "wc_active": wc_active, "squad": [{k: v for k, v in r.items() if k != "_raw"} for r in squad_rows],
        "captain": {"name": cap_rows[0]["row"]["name"], "team": cap_rows[0]["row"]["team"], "id": cap_rows[0]["row"]["id"], "score": cap_rows[0]["score"], "verdict": cap_rows[0]["verdict"], "factors": cap_rows[0]["factors"], "fixture": cap_rows[0]["fixture"], "proj": cap_rows[0]["row"]["proj"], "price": cap_rows[0]["row"]["price"], "ep_next": cap_rows[0]["row"]["ep_next"]} if cap_rows else None,
        "vice": {"name": cap_rows[1]["row"]["name"], "score": cap_rows[1]["score"], "verdict": cap_rows[1]["verdict"], "fixture": cap_rows[1]["fixture"]} if len(cap_rows) > 1 else None,
        "xi": [{k: v for k, v in r.items() if k != "_raw"} for r in xi], "bench": [{k: v for k, v in r.items() if k != "_raw"} for r in bench],
        "xi_proj": round(sum(r["proj"] for r in xi), 1), "bench_proj": round(sum(r["proj"] for r in bench), 1),
        "sub_warnings": [f"No {s.upper()} cover on bench." for s, has in {"gk": any(r["pos"] == 1 for r in bench), "def": any(r["pos"] == 2 for r in bench), "mid": any(r["pos"] == 3 for r in bench), "fwd": any(r["pos"] == 4 for r in bench)}.items() if not has and any(r["pos"] == {"gk":1,"def":2,"mid":3,"fwd":4}[s] for r in xi)],
        "transfer": {"verdict": transfer_verdict, "reason": reason, "sell": ({k: v for k, v in sell_cand.items() if k != "_raw"} if sell_cand else None), "buys": buy_rows},
        "chips": chips, "price_alerts": price_alerts(squad_rows), "price_deltas_since_last_run": snapshot_prices(players), "fixture_swings": swings, "value": value,
        "history": hist_rows[-8:], "captain_board": [{"name": c["row"]["name"], "score": c["score"], "verdict": c["verdict"], "fixture": c["fixture"], "proj": c["proj"], "factors": c["factors"]} for c in cap_rows[:3]], "ml": ml_accuracy()
    }
    if cap_rows and engine_out["xi_proj"]: log_ml_row([datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), team_id, gw, engine_out["xi_proj"], "", cap_rows[0]["row"]["name"], round(cap_rows[0]["row"]["proj"] * 2, 1), "", "V2.0"])
    return engine_out

def ideal_xi(engine_out, players=None, teams=None, fixtures=None, form=None, horizon=5, use_defcon=False, swap_in=None):
    if players is None:
        players, teams, events = fetch_bootstrap()
        fixtures = fetch_fixtures()
        gw = next_gw_info(events)["gw"]
        form = team_form(gw, fixtures)
    else: gw = engine_out["gw"]
    fx_map = fixtures_map(gw, horizon, fixtures, teams)
    dcs = sorted(float(p.get("defensive_contribution_per_90") or 0) for p in players.values() if p["element_type"] == 2 and (p.get("minutes") or 0) > 450)
    defcon_scale = {"median": dcs[len(dcs) // 2], "p75": dcs[int(len(dcs) * 0.75)]} if len(dcs) > 8 else {"median": DEFCON_MEDIAN, "p75": DEFCON_P75}

    owned = set(r["id"] for r in engine_out["squad"])
    if swap_in: owned.discard(swap_in)
    template = {1: [], 2: [], 3: [], 4: []}
    for pid, p in players.items():
        if p.get("status") != "a" or (p.get("minutes") or 0) < 90: continue
        fxs = fx_map.get(p["team"], [])[:horizon]
        if not fxs: continue
        proj, avg_fdr, per = project_player(p, fxs, form, use_defcon, defcon_scale)
        template[p["element_type"]].append({"id": pid, "name": p["web_name"], "team": teams[p["team"]]["short_name"], "pos_name": POS_NAME[p["element_type"]], "price": p["now_cost"] / 10.0, "proj": proj, "avg_fdr": avg_fdr, "run": per, "sel": float(p.get("selected_by_percent") or 0), "owned": pid in owned})
    for pos in template: template[pos].sort(key=lambda r: r["proj"], reverse=True)

    slots = {1: 1, 2: 4, 3: 4, 4: 2}
    xi = {}
    for pos, n in slots.items():
        rows = template[pos][:n]
        if swap_in and swap_in in {r["id"] for r in template[pos]} and swap_in not in {r["id"] for r in rows}:
            rows = rows[:-1] + [next(r for r in template[pos] if r["id"] == swap_in)]
            rows.sort(key=lambda r: r["proj"], reverse=True)
        xi[POS_NAME[pos]] = rows
    cost = sum(r["price"] for rows in xi.values() for r in rows)
    missing = [{"name": r["name"], "team": r["team"], "pos_name": r["pos_name"], "price": r["price"], "proj": r["proj"]} for rows in xi.values() for r in rows if not r["owned"]]
    return {"xi": xi, "cost": round(cost, 1), "missing": missing, "swap_in": swap_in}