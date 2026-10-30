# app.py — FPL Toolz V2 "Command Center"
# ============================================================
# One screen. Three answers. No setup.
#
#   WHO TO CAPTAIN | TRANSFER OR SAVE | XI + BENCH + CHIP
#
# Run:   streamlit run app.py
# Stack: streamlit + requests (see requirements.txt)
# Data:  public FPL API only - no login, no credentials, cloud-safe.
#
# The engine is ui_engine.py (self-contained, V1 formula registry).
# Advanced brains: h2h_adjuster.py, auto_sub.py, fixture_swing.py,
# value_tracker.py.
# ============================================================

import time
from datetime import datetime, timezone

import streamlit as st

import ui_engine
import auto_sub
from h2h_adjuster import h2h_context_table

st.set_page_config(page_title="FPL Toolz — Command Center",
                   page_icon="⚽", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
.big-font { font-size:26px !important; font-weight:800; letter-spacing:-.5px; }
.answer-card { background:#0f1724; padding:18px 20px; border-radius:14px;
               border:1px solid #22304a; }
.chip { display:inline-block; padding:2px 10px; border-radius:999px;
        font-size:.78em; font-weight:700; }
.chip-green  { background:#123b2a; color:#5dd6a3; }
.chip-red    { background:#3b1512; color:#ff8a7a; }
.chip-amber  { background:#3b2f12; color:#ffcf7a; }
.chip-blue   { background:#12293b; color:#7ac2ff; }
.sq { display:inline-block; width:14px; height:14px; border-radius:3px;
      margin-right:3px; vertical-align:middle; }
.sq-green { background:#22c55e; } .sq-olive { background:#84cc16; }
.sq-orange { background:#f59e0b; } .sq-red { background:#ef4444; }
.sq-grey { background:#334155; }
footer { visibility:hidden; }
</style>
""", unsafe_allow_html=True)


def squares(run, horizon=None):
    out = []
    for x in run[:horizon or 5]:
        f = x.get("fdr", 3)
        cls = ("sq-green" if f <= 1.99 else "sq-olive" if f <= 2.99 else
               "sq-orange" if f <= 3.99 else "sq-red")
        out.append(f'<span class="sq {cls}" title="GW{x.get("gw")} '
                   f'vs {x.get("opp","?")} ({x.get("ha","")}) FDR {f}">'
                   f'</span>')
    return " ".join(out) if out else '<span class="sq sq-grey"></span>'


def chip(label, cls):
    return f'<span class="chip chip-{cls}">{label}</span>'


# ---------------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------------
defaults = {"team_id": "", "data": None, "horizon": "Next GW only",
            "defcon": False}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

HORIZONS = {"Next GW only": 1, "Next 3 GWs": 3, "Next 5 GWs": 5}

# ---------------------------------------------------------------
# SIDEBAR — Connect + Intelligence Toggles + Navigation
# ---------------------------------------------------------------
with st.sidebar:
    st.markdown("## ⚽ FPL Toolz")
    st.caption("V2.0 Command Center — the engine is silent, "
               "the answers are loud.")
    st.markdown("---")

    st.markdown("### 1 · Connect")
    tid = st.text_input("FPL Team ID", value=st.session_state.team_id,
                        placeholder="e.g. 3842846")
    if st.button("Connect & Run Engine", use_container_width=True,
                 type="primary"):
        if tid.strip().isdigit():
            st.session_state.team_id = tid.strip()
            ui_engine.clear_cache()
            with st.spinner("Fetching live data and running the engine…"):
                st.session_state.data = ui_engine.run_engine(
                    int(tid.strip()),
                    HORIZONS[st.session_state.horizon],
                    st.session_state.defcon)
        else:
            st.error("Team ID must be numeric (from your FPL entry URL).")

    st.markdown("---")
    st.markdown("### 2 · Intelligence Toggles")
    st.session_state.horizon = st.radio(
        "Optimise for", list(HORIZONS.keys()),
        index=list(HORIZONS.keys()).index(st.session_state.horizon),
        help="Horizon window used for projections, transfer scans and the "
             "ideal XI. Lineup and captaincy always weigh the next GW "
             "fixture most heavily.")
    st.session_state.defcon = st.toggle(
        "Prioritise DefCon defenders", value=st.session_state.defcon,
        help="Boosts defenders by live defensive-contribution rank: "
             "+10% above the defender median, +20% in the top quartile. "
             "Use when goals look scarce and clean sheets + tackles "
             "are the points source.")
    if st.session_state.data is not None:
        if st.button("Re-run with these settings", use_container_width=True):
            with st.spinner("Re-running the engine…"):
                st.session_state.data = ui_engine.run_engine(
                    int(st.session_state.team_id),
                    HORIZONS[st.session_state.horizon],
                    st.session_state.defcon)

    st.markdown("---")
    st.markdown("### 3 · Navigate")
    page = st.radio("Go to", ["Weekly Dashboard", "Advanced Analytics",
                              "Post-GW Review", "Squad Sync (blind window)"])

# ---------------------------------------------------------------
# HEADER
# ---------------------------------------------------------------
data = st.session_state.data
if data is None:
    st.markdown("<span class='big-font'>⚽ FPL Toolz — Command Center</span>",
                unsafe_allow_html=True)
    st.caption("Paste your FPL Team ID in the sidebar and press "
               "**Connect & Run Engine**. "
               "Everything else is automatic — squad, fixtures, form, "
               "projections.")
    st.info("New around here? Your Team ID is the number in your FPL entry "
            "URL: fantasy.premierleague.com/entry/<b>3842846</b>/history — "
            "that number is all this app ever asks for.", icon="🔎")
    st.stop()

if data.get("error"):
    st.error(data["error"])
    st.stop()

gw, tz = data["gw"], timezone.utc
deadline_txt = "—"
if data.get("deadline_epoch"):
    secs = data["deadline_epoch"] - int(time.time())
    if secs > 0:
        d, r = divmod(secs, 86400)
        h, r = divmod(r, 3600)
        m, _ = divmod(r, 60)
        deadline_txt = (f"{d}d {h}h {m}m" if d else f"{h}h {m}m")
    else:
        deadline_txt = "PASSED — GW live"

c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
with c1:
    st.markdown(f"<span class='big-font'>👋 {data['team_name']}</span>",
                unsafe_allow_html=True)
    src_style = {"api_locked": "blue", "seed": "amber",
                 "api_previous": "red", "seed_stale": "red"}
    st.markdown(
        chip(f"SQUAD: {data['squad_source'].replace('_', ' ').upper()}",
             src_style.get(data["squad_source"], "amber")) +
        " " + chip(f"ITB £{data['bank'] or 0:.1f}m", "blue") + " " +
        chip(f"FTs BANKED: {data['fts']}", "blue"),
        unsafe_allow_html=True)
with c2:
    st.metric("Gameweek", f"GW{gw}")
with c3:
    st.metric("Deadline", deadline_txt)
with c4:
    st.metric("Projected XI", f"{data['xi_proj']:.0f} pts")

with st.expander(data["squad_note"], expanded=False):
    st.caption(data["squad_note"])

# ---------------------------------------------------------------
# URGENT BANNER (price alerts, injury crisis, active chip)
# ---------------------------------------------------------------
alerts = []
for a in data.get("price_alerts", []):
    if a["type"] == "fall":
        pct = f" ({a['pct']:+.1f}% projected)" if a.get("pct") is not None else ""
        alerts.append(f"💸 **{a['player']} is trending to FALL{pct}** — "
                      "decide before tonight's price change.")
flagged = [r for r in data["squad"] if r["reliability"] == "INJURY FLAG"]
if len(flagged) >= 3:
    alerts.append(f"🚨 **{len(flagged)} players are flagged** "
                  f"({', '.join(r['name'] for r in flagged)}) — this is "
                  "chip-repair territory. See the Chip Strategy tab.")
if data.get("wc_active"):
    alerts.append("🃏 **WILDCARD IS ACTIVE** — unlimited transfers until "
                  "the deadline. Free transfers are preserved; shape the "
                  "squad freely, then lock your XI and bench order.")
for w in data.get("sub_warnings", []):
    alerts.append(f"⚠️ {w}")

if alerts:
    with st.container(border=True):
        for a in alerts:
            st.markdown(a)

# ===============================================================
# WEEKLY DASHBOARD — the three answers
# ===============================================================
if page == "Weekly Dashboard":
    cap, tr = st.columns([1, 1], gap="large")

    # ---------- ANSWER 1: CAPTAIN ----------
    with cap:
        st.markdown("### 🏆 The Captain")
        captain = data["captain"]
        with st.container(border=True):
            if captain:
                vcls = ("green" if "STRONG" in captain["verdict"] else
                        "amber" if captain["verdict"] in ("SOLID", "LEAN")
                        else "red")
                vbadge = chip(captain["verdict"], vcls)
                st.markdown(f"<span class='big-font'>"
                            f"{captain['name']}</span> {vbadge}",
                            unsafe_allow_html=True)
                st.caption(f"{captain['team']} · vs {captain['fixture']} · "
                           f"£{captain['price']:.1f}m")
                st.metric("Captain score", f"{captain['score']:.1f} / 10",
                          f"proj {captain['proj']:.1f} pts "
                          f"(x2 = {captain['proj'] * 2:.1f})")
                f = captain["factors"]
                st.markdown(
                    f"**Why:** fixture {f['fixture']:.1f}/10 "
                    f"(Smart FDR {f['smart_fdr']}) · form "
                    f"{f['form']:.1f}/10 · underlying "
                    f"{f['underlying']:.1f}/10 · role {f['role']:.0f}/10 · "
                    f"ownership {f['ownership']:.1f}/10")
                st.markdown(
                    f"**Weights:** fixture 35% · form 25% · underlying 20% "
                    f"· role 10% · ownership 10%")
                if data.get("vice"):
                    st.info(f"**Vice:** {data['vice']['name']} "
                            f"({data['vice']['score']:.1f}) — the armband "
                            "passes here if the captain does not play.")
                st.caption(f"FPL's own model (ep_next) projects "
                           f"{captain['name']}: "
                           f"{captain.get('ep_next', 'n/a')} pts — "
                           "shown for calibration, never used for ranking.")

        st.markdown("#### Captain board")
        for c in data["captain_board"][1:]:
            st.markdown(f"- **{c['name']}** — {c['score']:.1f} "
                        f"({c['verdict']}) · vs {c['fixture']} · "
                        f"proj {c['proj']:.1f}")

    # ---------- ANSWER 2: TRANSFER ----------
    with tr:
        st.markdown("### 🔄 The Transfer")
        t = data["transfer"]
        with st.container(border=True):
            vmap = {"TRANSFER": "green", "SAVE": "amber",
                    "HIT": "red", "WILDCARD ACTIVE": "blue"}
            st.markdown(chip(t["verdict"], vmap.get(t["verdict"], "amber")),
                        unsafe_allow_html=True)
            if t.get("sell") and t.get("buys"):
                sell, best = t["sell"], t["buys"][0]
                st.markdown(f"<span class='big-font'>Sell "
                            f"{sell['name']} → Buy {best['name']}"
                            f"</span>", unsafe_allow_html=True)
                gain = round(best["proj"] - sell["proj"], 1)
                st.metric("Horizon gain", f"{gain:+.1f} pts",
                          f"{best['price'] - sell['price']:+.1f}m price",
                          delta_color="normal")
                cA, cB = st.columns(2)
                with cA:
                    st.markdown(f"**{sell['name']} run:** "
                                f"{squares(sell['run'])}", unsafe_allow_html=True)
                    st.caption(f"proj {sell['proj']:.1f} pts/GW · "
                               f"£{sell['price']:.1f}m")
                with cB:
                    st.markdown(f"**{best['name']} run:** "
                                f"{squares(best['run'])}", unsafe_allow_html=True)
                    st.caption(f"proj {best['proj']:.1f} pts/GW · "
                               f"£{best['price']:.1f}m · "
                               f"{best['sel']:.0f}% owned")
                st.markdown(
                    f"**Plain English:** value floor = a player projected "
                    f"under {ui_engine.VALUE_FLOOR:.1f} pts/GW. "
                    f"{sell['name']} sits at {sell['proj']:.1f}. "
                    f"The move must clear a {ui_engine.SWAP_EDGE:.0f}-pt "
                    f"edge to beat saving the transfer.")
                if t.get("sell_note"):
                    st.caption("⚖️ " + t["sell_note"])
                st.code(f"Transfer: {sell['name']} -> {best['name']} | "
                        f"Captain: {data['captain']['name']} | "
                        f"VC: {data['vice']['name'] if data.get('vice') else '-'}",
                        language="text")
                st.caption("↑ Copy this into the FPL app search / "
                           "your league chat.")
            else:
                st.markdown(f"**{t['verdict']}** — {t['reason']}")
            st.caption(t["reason"])

    # ---------- ANSWER 3: LINEUP + BENCH ----------
    st.markdown("---")
    st.markdown("### ⚽ The Lineup")
    lx, lb = st.columns([2, 1], gap="large")
    with lx:
        with st.container(border=True):
            st.metric("Projected team score", f"{data['xi_proj']:.0f} pts",
                      f"bench adds {data['bench_proj']:.0f}")
            rows_by_pos = {"GK": [], "DEF": [], "MID": [], "FWD": []}
            for r in data["xi"]:
                rows_by_pos[r["pos_name"]].append(r)
            for pos in ("GK", "DEF", "MID", "FWD"):
                if rows_by_pos[pos]:
                    line = " · ".join(
                        f"{r['name']} ({r['proj']:.1f})"
                        for r in rows_by_pos[pos])
                    st.markdown(f"**{pos}:** {line}")
            cap_id = data["captain"]["name"] if data["captain"] else ""
            if cap_id:
                st.success(f"**Captain: {cap_id}** — set it on the site "
                           "before the deadline.")
    with lb:
        with st.container(border=True):
            st.markdown("**Bench order (auto-sub ready)**")
            for i, r in enumerate(data["bench"], 1):
                rcls = ("green" if r["reliability"] == "Reliable"
                        else "red")
                st.markdown(
                    f"{i}. {chip(r['pos_name'], 'blue')} "
                    f"**{r['name']}** {chip(r['reliability'], rcls)}",
                    unsafe_allow_html=True)
                st.caption(f"proj {r['proj']:.1f} · starts "
                           f"{r['start_rate'] * 100:.0f}% of games · "
                           f"{r['play_prob']:.0f}% fit")
            st.markdown("**How auto-subs work:** your bench is used in "
                        "order 1→4; the GK sub only covers the GK slot; "
                        "an outfield sub only enters if the formation "
                        "stays legal. The order above is optimised for "
                        "exactly that.")
        with st.expander("🧪 What if a starter doesn't play? "
                         "(auto-sub stress test)"):
            cap_id = data["captain"].get("id") if data["captain"] else None
            vice_id = None
            for r in data["squad"]:
                if data.get("vice") and r["name"] == data["vice"]["name"]:
                    vice_id = r["id"]
            for t in auto_sub.stress_test(data["xi"], data["bench"],
                                          cap_id, vice_id):
                arm = f" · {t['armband']}" if t["armband"] else ""
                st.markdown(f"- **{t['if_missing']}** out → "
                            f"**{t['sub_in']}**{arm}")
            st.caption("Simulated with FPL's actual rules: bench order, "
                       "GK-for-GK only, formation legality, armband to "
                       "the vice.")

    st.caption("⚠️ Disclaimer: FPL Toolz analyses and recommends — you "
               "make every decision on the official site. Not affiliated "
               "with the Premier League or FPL.")

# ===============================================================
# ADVANCED ANALYTICS
# ===============================================================
elif page == "Advanced Analytics":
    tb1, tb2, tb3, tb4, tb5, tb6 = st.tabs(
        ["📈 5-GW Horizon", "🌟 Ideal XI", "🃏 Chip Strategy",
         "🔀 Fixture Swings", "🤝 H2H", "💰 Squad Value"])

    with tb1:
        st.markdown("#### Every squad player over the horizon")
        for r in sorted(data["squad"], key=lambda x: x["avg_fdr"]):
            st.markdown(
                f"{chip(r['pos_name'], 'blue')} **{r['name']}** "
                f"({r['team']}) — run: {squares(r['run'])} "
                f"· avg FDR {r['avg_fdr']:.1f} · proj {r['proj']:.1f}/GW",
                unsafe_allow_html=True)
        st.caption("G = easy · g = favourable · o = tough · R = brutal. "
                   "Fixture swings (green/red turns) are flagged in their "
                   "own tab 2–3 weeks ahead so you can buy the turn, "
                   "not the highlight.")

    with tb2:
        st.markdown("#### Global template XI (the dream team + your gap)")
        players, teams, events = ui_engine.fetch_bootstrap()
        fixtures = ui_engine.fetch_fixtures()
        form = ui_engine.team_form(gw, fixtures)
        ideal = ui_engine.ideal_xi(
            data, players=players, teams=teams, fixtures=fixtures,
            form=form, horizon=HORIZONS[st.session_state.horizon],
            use_defcon=st.session_state.defcon)
        st.session_state["ideal"] = ideal
        options = ["(none)"] + [
            f"{r['name']} ({r['team']}, £{r['price']:.1f}m, "
            f"proj {r['proj']:.1f})"
            for pos in ("GK", "DEF", "MID", "FWD")
            for r in ideal["xi"][pos] if not r["owned"]]
        swap = st.selectbox(
            "Custom add — force a market player into the template "
            "(instant re-projection):", options, index=0)
        swap_id = None
        if swap != "(none)":
            name_part = swap.split(" (")[0]
            players_by_name = {}
            for pos in ("GK", "DEF", "MID", "FWD"):
                for r in ideal["xi"][pos]:
                    players_by_name[r["name"]] = r["id"]
            # any player in the pool, not just template members
            for pid, p in players.items():
                if p["web_name"] == name_part:
                    swap_id = pid
                    break
            ideal = ui_engine.ideal_xi(
                data, players=players, teams=teams, fixtures=fixtures,
                form=form, horizon=HORIZONS[st.session_state.horizon],
                use_defcon=st.session_state.defcon, swap_in=swap_id)
            st.session_state["ideal"] = ideal
            st.info(f"Template re-projected with **{name_part}** forced in "
                    "— replaced the weakest slot at the same position.")
        colA, colB = st.columns([3, 2])
        with colA:
            for pos in ("GK", "DEF", "MID", "FWD"):
                for r in ideal["xi"][pos]:
                    own = "✅" if r["owned"] else "⬜"
                    st.markdown(
                        f"{own} **{r['name']}** ({r['team']}) — "
                        f"proj {r['proj']:.1f} · run "
                        f"{squares(r['run'])}", unsafe_allow_html=True)
        with colB:
            st.metric("Template cost", f"£{ideal['cost']:.1f}m")
            st.markdown("**Transfer roadmap — players you're missing:**")
            for m in ideal["missing"]:
                st.markdown(f"- {m['pos_name']} **{m['name']}** "
                            f"({m['team']}) £{m['price']:.1f}m · "
                            f"proj {m['proj']:.1f}")

    with tb3:
        chips = data["chips"]
        st.markdown("#### Chip ledger & plan")
        if chips.get("active"):
            st.success(f"**ACTIVE THIS GW:** "
                       f"{ui_engine.CHIP_LABEL.get(chips['active'], chips['active'])}")
        played = chips.get("played", {})
        if played:
            st.markdown("**Played:** " + " · ".join(
                f"GW{gw_}: {ui_engine.CHIP_LABEL.get(c, c)}"
                for gw_, c in sorted(played.items(), key=lambda kv: int(kv[0]))))
        else:
            st.markdown("**Played:** none yet (Set 1)")
        st.markdown("**Remaining (Set 1):** " + (", ".join(
            ui_engine.CHIP_LABEL.get(c, c) for c in
            chips["remaining_set1"]) if chips["remaining_set1"] else "—"))
        st.info(f"Set 2 chips unlock from GW{chips['set2_available_from']} "
                "(2026/27 two-set rules). Set 1 unused chips die at the "
                "GW19 deadline.")
        plan = chips.get("plan", {})
        if plan:
            st.markdown("**The plan**")
            for k, v in plan.items():
                st.markdown(f"- **{ui_engine.CHIP_LABEL.get(k, k)}**: {v}")
        if chips.get("notes"):
            st.caption(chips["notes"])
        st.caption("The ledger lives in chips_used.json — update it the "
                   "moment you play a chip (30 seconds, 4 times a season). "
                   "The API's own chip feed only confirms after a GW "
                   "completes, so the file is the fast truth.")

    with tb4:
        st.markdown("#### Fixture swing radar (next 6 GWs)")
        if data.get("fixture_swings"):
            for s in data["fixture_swings"]:
                cls = ("green" if "GREEN" in s["type"] else
                       "red" if "RED" in s["type"] else "amber")
                st.markdown(f"{chip(s['type'], cls)} {s['message']}",
                            unsafe_allow_html=True)
        else:
            st.caption("No sharp turns detected in the current window.")
        st.caption("Buy the green turn before it arrives; sell the red "
                   "turn before it bites. Blanks are Free-Hit fuel.")

    with tb5:
        st.markdown("#### Head-to-head history in play")
        rows = h2h_context_table(None)
        if rows:
            for r in rows:
                derby = " · DERBY (volatility)" if r["derby"] else ""
                st.markdown(f"- **{r['matchup']}** — last 5: "
                            f"{r['wins']} · avg goals {r['avg_total_goals']}"
                            f" · clean sheets {r['clean_sheets']}{derby}")
        else:
            st.caption("h2h.csv is empty. Add rows (last-5 records per "
                       "fixture) and the engine folds matchup history into "
                       "Smart FDR automatically — range ±1.5, derbies "
                       "penalised, missing data ignored.")
        st.caption("H2H = the betting-platform factor: style mismatches, "
                   "derby intensity, historical dominance — the matchup "
                   "context form alone can't see.")

    with tb6:
        v = data.get("value")
        if v:
            st.metric("Squad cost (15)", f"£{v['squad_cost']:.1f}m")
            c1v, c2v = st.columns(2)
            with c1v:
                st.metric("Price drift this GW", f"{v['this_gw_price_drift']:+.1f}m")
            with c2v:
                st.metric("Drift since GW1", f"{v['season_price_drift']:+.1f}m")
            st.markdown("#### Team value, last 8 GWs")
            for t in v["history_trend"]:
                st.markdown(f"- GW{t['gw']}: value £{t['value']}m · "
                            f"bank £{t['bank']}m · {t['points']} pts "
                            f"(bench {t['bench_pts']})")
            st.caption("Build value in the first half; spend it in the "
                       "DGW-heavy second half.")

# ===============================================================
# POST-GW REVIEW (the ML data hook)
# ===============================================================
elif page == "Post-GW Review":
    st.markdown("### 🧮 Post-GW Review — close the loop")
    st.caption("3 seconds of your time: enter what you actually scored. "
               "Every entry trains the V3 ML engine (projection vs actual "
               "is the exact training row).")
    hist = data.get("history", [])
    if hist:
        st.markdown("#### Recent gameweeks")
        for h in reversed(hist):
            rank = h.get("rank")
            rank_txt = f"{rank:,}" if isinstance(rank, int) else "—"
            st.markdown(f"- GW{h['event']}: **{h['points']} pts** · "
                        f"rank {rank_txt} · bench wasted "
                        f"{h.get('points_on_bench', 0)} · transfers "
                        f"{h.get('event_transfers', 0)}")
    proj = data.get("xi_proj")
    col1, col2 = st.columns(2)
    with col1:
        actual = st.number_input("Your actual GW score (last completed GW)",
                                 min_value=0, max_value=250, step=1)
        gw_in = st.number_input("Gameweek", min_value=1, max_value=38,
                                value=max(1, gw - 1))
        if st.button("Log result", type="primary"):
            ok = ui_engine.log_actual_result(int(st.session_state.team_id),
                                             int(gw_in), float(actual))
            if ok:
                st.success(f"Logged: GW{gw_in} actual {actual:.0f} pts. "
                           "This is the ML training row.")
                st.balloons()
            else:
                st.warning("Could not write ml_training_data.csv (read-only "
                           "or cloud). The row lives in this session only.")
    with col2:
        st.metric("Last engine projection", f"{proj:.0f} pts")
        if actual and proj:
            st.metric("Delta vs projection", f"{actual - proj:+.0f} pts")
    acc = data.get("ml")
    if acc:
        st.info(f"**Model accuracy so far:** {acc['weeks']} weeks logged · "
                f"mean absolute error {acc['mean_abs_pct_error']}%")
    else:
        st.caption("No accuracy history yet — it starts accruing from the "
                   "first logged result.")

# ===============================================================
# SQUAD SYNC (pre-deadline blind window workbench)
# ===============================================================
elif page == "Squad Sync (blind window)":
    st.markdown("### 🗒️ Squad Sync — the pre-deadline workbench")
    st.caption("The official API only publishes squads AFTER the deadline. "
               "Before it, paste your intended 15 here (one name per line) "
               "and every analysis runs on your real plan — not last "
               "week's team. Names or FPL IDs both work.")
    txt = st.text_area("Your intended 15",
                       value="\n".join(r["name"] for r in data["squad"]),
                       height=220)
    itb = st.number_input("Bank (£m)", min_value=0.0, max_value=20.0,
                          value=float(data["bank"] or 0.0), step=0.1)
    active_chip = st.selectbox("Active chip (if playing one)",
                               ["none", "wildcard", "freehit", "3xc",
                                "bboost"])
    if st.button("Resolve & save seed", type="primary"):
        entries = [l.strip() for l in txt.splitlines() if l.strip()]
        ids, raw = [], []
        players, teams, events = ui_engine.fetch_bootstrap()
        names = [e for e in entries if not e.isdigit()]
        resolved, misses = ui_engine.resolve_names(names, players, teams)
        by_name = {r[1].lower(): r[0] for r in resolved}
        for e in entries:
            if e.isdigit():
                ids.append(int(e))
            else:
                pid = by_name.get(e.lower().replace(" ", ""))
                if pid:
                    ids.append(pid)
        if misses:
            st.error("Could not resolve: " + ", ".join(misses) +
                     " — check spelling (use the FPL web name).")
        if len(ids) == 15 and not misses:
            ok = ui_engine.save_seed(
                gw, ids, itb=float(itb),
                active_chip=None if active_chip == "none" else active_chip,
                label="ui_sync")
            if ok:
                st.success("Seed saved to v2_squad.json — re-run the engine "
                           "from the sidebar to analyse this squad.")
                ui_engine.clear_cache()
            else:
                st.warning("Read-only folder (cloud?) — seed kept in "
                           "session only.")
        elif len(ids) != 15:
            st.error(f"That is {len(ids)} players — exactly 15 required.")

st.markdown("---")
st.caption("FPL Toolz V2.0 · Command Center · the engine is silent, the "
           "answers are loud · not affiliated with the Premier League or "
           "FPL — you make every decision on the official site.")
