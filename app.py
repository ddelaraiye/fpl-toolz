import time
import re
from datetime import datetime, timezone
import streamlit as st
import ui_engine
import auto_sub

try:
    from h2h_adjuster import h2h_context_table
except Exception:
    def h2h_context_table(x): return []

st.set_page_config(page_title="FPL Toolz — Command Center", page_icon="⚽", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.big-font { font-size:26px !important; font-weight:800; letter-spacing:-.5px; }
.answer-card { background:#0f1724; padding:18px 20px; border-radius:14px; border:1px solid #22304a; }
.chip { display:inline-block; padding:2px 10px; border-radius:999px; font-size:.78em; font-weight:700; }
.chip-green { background:#123b2a; color:#5dd6a3; }
.chip-red { background:#3b1512; color:#ff8a7a; }
.chip-amber { background:#3b2f12; color:#ffcf7a; }
.chip-blue { background:#12293b; color:#7ac2ff; }
/* P1 Fix: Text inside squares for colorblind accessibility */
.sq { display:inline-flex; align-items:center; justify-content:center; width:16px; height:16px; border-radius:3px; margin-right:4px; font-size:10px; font-weight:bold; color: #000; }
.sq-green { background:#22c55e; color: #fff; } .sq-olive { background:#84cc16; color: #fff; }
.sq-orange { background:#f59e0b; } .sq-red { background:#ef4444; color: #fff; }
.sq-grey { background:#334155; color:#fff; }
footer { visibility:hidden; }
</style>
""", unsafe_allow_html=True)

def squares(run, horizon=None):
    out = []
    for x in run[:horizon or 5]:
        f = x.get("fdr", 3)
        if f <= 1.99: cls, txt = "sq-green", "E"
        elif f <= 2.99: cls, txt = "sq-olive", "F"
        elif f <= 3.99: cls, txt = "sq-orange", "T"
        else: cls, txt = "sq-red", "B"
        out.append(f'<span class="sq {cls}" title="GW{x.get("gw")} vs {x.get("opp","?")} ({x.get("ha","")}) FDR {f}">{txt}</span>')
    return " ".join(out) if out else '<span class="sq sq-grey">-</span>'

def chip(label, cls): return f'<span class="chip chip-{cls}">{label}</span>'

# P0 FIX: Query Params (Survives F5)
qp = st.query_params
if "team_id" in qp: st.session_state.team_id = qp["team_id"]
if "seed" in qp and qp["seed"]:
    try:
        seed_ids = [int(i) for i in qp["seed"].split(",")]
        if len(seed_ids) == 15:
            st.session_state.override_seed = {
                "source": "seed", "note": "Pre-deadline workbench squad (Synced via URL).",
                "picks": seed_ids, "bank": float(qp.get("bank", 0)),
                "captain_id": int(qp.get("cap", 0)) if qp.get("cap") else None,
                "vice_id": None, "active_chip": qp.get("chip", None)
            }
    except: pass

defaults = {"team_id": "", "data": None, "horizon": "Next GW only", "defcon": False, "override_seed": None}
for k, v in defaults.items():
    if k not in st.session_state: st.session_state[k] = v
HORIZONS = {"Next GW only": 1, "Next 3 GWs": 3, "Next 5 GWs": 5}

with st.sidebar:
    st.markdown("## ⚽ FPL Toolz")
    st.caption("V2.1 Command Center")
    st.markdown("---")
    
    with st.expander("❓ Where do I find my Team ID?"):
        st.markdown("""
        1. Go to [fantasy.premierleague.com](https://fantasy.premierleague.com/)
        2. Click on **'Points'** (or your team name).
        3. Look at the URL: `fantasy.premierleague.com/entry/`**`1234567`**`/event/9`
        4. The number is your Team ID. Copy/paste the whole URL if you want!
        """)
        
    user_input = st.text_input("Team ID or URL", value=st.session_state.team_id, placeholder="e.g. 123456 or paste URL")
    
    if st.button("Connect & Run Engine", use_container_width=True, type="primary"):
        if user_input:
            match = re.search(r'\d+', user_input)
            if match:
                parsed_id = match.group()
                st.session_state.team_id = parsed_id
                st.query_params["team_id"] = parsed_id
                ui_engine.clear_cache()
                with st.spinner("Fetching live data..."):
                    try:
                        st.session_state.data = ui_engine.run_engine(
                            int(parsed_id), HORIZONS[st.session_state.horizon], 
                            st.session_state.defcon, override_seed=st.session_state.override_seed
                        )
                    except Exception as e:
                        st.error(str(e))
            else:
                st.error("Couldn't find a valid Team ID.")

    if st.session_state.override_seed:
        if st.button("❌ Clear Sync & Use API Squad", use_container_width=True):
            st.session_state.override_seed = None
            st.query_params.pop("seed", None)
            st.query_params.pop("bank", None)
            st.query_params.pop("cap", None)
            st.query_params.pop("chip", None)
            ui_engine.clear_cache()
            st.rerun()

    st.markdown("---")
    st.session_state.horizon = st.radio("Optimise for", list(HORIZONS.keys()), index=list(HORIZONS.keys()).index(st.session_state.horizon))
    st.session_state.defcon = st.toggle("Prioritise DefCon defenders", value=st.session_state.defcon, help="Boosts defenders by live defensive-contribution rank.")
    
    if st.session_state.data is not None:
        if st.button("Re-run with these settings", use_container_width=True):
            with st.spinner("Re-running..."):
                st.session_state.data = ui_engine.run_engine(
                    int(st.session_state.team_id), HORIZONS[st.session_state.horizon], 
                    st.session_state.defcon, override_seed=st.session_state.override_seed
                )

    st.markdown("---")
    page = st.radio("Navigate", ["Weekly Dashboard", "Advanced Analytics", "Post-GW Review", "Squad Sync"])

data = st.session_state.data
if data is None:
    st.markdown("<span class='big-font'>⚽ FPL Toolz — Command Center</span>", unsafe_allow_html=True)
    st.info("Paste your FPL Team ID (or URL) in the sidebar and press **Connect & Run Engine**.")
    st.stop()

if data.get("error"):
    st.error(data["error"])
    st.stop()

fetch_time = datetime.now().strftime("%H:%M:%S")
gw = data["gw"]
deadline_txt = "—"
if data.get("deadline_epoch"):
    secs = data["deadline_epoch"] - int(time.time())
    if secs > 0:
        d, r = divmod(secs, 86400); h, r = divmod(r, 3600); m, _ = divmod(r, 60)
        deadline_txt = f"{d}d {h}h {m}m" if d else f"{h}h {m}m"
    else: deadline_txt = "PASSED"

c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
with c1:
    st.markdown(f"<span class='big-font'>👋 {data['team_name']}</span>", unsafe_allow_html=True)
    src_style = {"api_locked": "blue", "seed": "amber", "api_previous": "red", "seed_stale": "red"}
    st.markdown(chip(f"SQUAD: {data['squad_source'].replace('_', ' ').upper()}", src_style.get(data["squad_source"], "amber")) + " " + chip(f"ITB £{data['bank'] or 0:.1f}m", "blue") + " " + chip(f"FTs BANKED: {data['fts']}", "blue"), unsafe_allow_html=True)
    
    if data["squad_source"] == "api_previous":
        st.caption("⚠️ This is your last locked squad. The FPL API hides your team until the deadline. Use **Squad Sync** to analyze your intended team.")
with c2: st.metric("Gameweek", f"GW{gw}")
with c3: st.metric("Deadline", deadline_txt, help="Time remaining until the FPL deadline.")
with c4: st.metric("Projected XI", f"{data['xi_proj']:.0f} pts", help="Projected points based on the V1 formula registry.")

if page == "Weekly Dashboard":
    
    st.markdown("### 📋 Your Action Plan")
    with st.container(border=True):
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown(f"**1. Captain**")
            if data.get("captain"): st.success(f"**{data['captain']['name']}**")
        with col_b:
            st.markdown(f"**2. Transfer**")
            if data["transfer"]["verdict"] == "TRANSFER":
                st.warning(f"Sell {data['transfer']['sell']['name']}")
            else: st.info(f"Save FT")
        with col_c:
            st.markdown(f"**3. Lineup**")
            st.info("Confirm XI & Bench")

    cap, tr = st.columns([1, 1], gap="large")

    with cap:
        st.markdown("### 🏆 The Captain")
        captain = data["captain"]
        if captain:
            with st.container(border=True):
                vcls = "green" if "STRONG" in captain["verdict"] else "amber" if captain["verdict"] in ("SOLID", "LEAN") else "red"
                st.markdown(f"<span class='big-font'>{captain['name']}</span> {chip(captain['verdict'], vcls)}", unsafe_allow_html=True)
                st.caption(f"{captain['team']} · vs {captain['fixture']} · £{captain['price']:.1f}m")
                st.metric("Captain score", f"{captain['score']:.1f} / 10", f"proj {captain['proj']:.1f} pts (x2 = {captain['proj'] * 2:.1f})", help="5-factor weighted score.")
                f = captain["factors"]
                st.markdown(f"**Why:** fixture {f['fixture']:.1f}/10 · form {f['form']:.1f}/10 · underlying {f['underlying']:.1f}/10 · role {f['role']:.0f}/10")
                if data.get("vice"): st.info(f"**Vice:** {data['vice']['name']} ({data['vice']['score']:.1f})")

    with tr:
        st.markdown("### 🔄 The Transfer")
        t = data["transfer"]
        with st.container(border=True):
            vmap = {"TRANSFER": "green", "SAVE": "amber", "HIT": "red", "WILDCARD ACTIVE": "blue"}
            st.markdown(chip(t["verdict"], vmap.get(t["verdict"], "amber")), unsafe_allow_html=True)
            
            if t.get("sell") and t.get("buys") and not data.get("wc_active"):
                sell = t["sell"]
                if sell["proj"] < 3.0: st.caption(f"⚖️ Value Floor: Projected under 3.0 pts/GW.")
                
                buy_options = [b["name"] for b in t["buys"]]
                selected_buy_name = st.selectbox("Select target", buy_options, index=0)
                best = next(b for b in t["buys"] if b["name"] == selected_buy_name)
                
                st.markdown(f"<span class='big-font'>Sell {sell['name']} → Buy {best['name']}</span>", unsafe_allow_html=True)
                gain = round(best["proj"] - sell["proj"], 1)
                st.metric("Horizon gain", f"{gain:+.1f} pts", f"{best['price'] - sell['price']:+.1f}m price")
                cA, cB = st.columns(2)
                with cA: st.markdown(f"**{sell['name']}:** {squares(sell['run'])}", unsafe_allow_html=True)
                with cB: st.markdown(f"**{best['name']}:** {squares(best['run'])}", unsafe_allow_html=True)
                st.code(f"Transfer: {sell['name']} -> {best['name']} | Captain: {data['captain']['name']}", language="text")
            
            elif data.get("wc_active") and t.get("buys"):
                st.info(t["reason"])
                for b in t["buys"][:3]:
                    st.markdown(f"**Buy:** {b['name']} ({b['team']}) — proj {b['proj']:.1f} · £{b['price']:.1f}m")
                    st.markdown(f"{squares(b['run'])}", unsafe_allow_html=True)
            else:
                st.markdown(f"**{t['verdict']}** — {t['reason']}")

    st.markdown("---")
    st.markdown("### ⚽ The Lineup")
    lx, lb = st.columns([2, 1], gap="large")
    with lx:
        with st.container(border=True):
            st.metric("Projected team score", f"{data['xi_proj']:.0f} pts", f"bench adds {data['bench_proj']:.0f}")
            rows_by_pos = {"GK": [], "DEF": [], "MID": [], "FWD": []}
            for r in data["xi"]: rows_by_pos[r["pos_name"]].append(r)
            
            for pos in ("FWD", "MID", "DEF", "GK"):
                if rows_by_pos[pos]:
                    st.markdown(f"<div style='text-align: center; color: #888; margin-top: 15px; margin-bottom: 5px;'>{pos}</div>", unsafe_allow_html=True)
                    cols = st.columns(len(rows_by_pos[pos]))
                    for idx, r in enumerate(rows_by_pos[pos]):
                        with cols[idx]:
                            is_cap = " (C)" if r["name"] == data["captain"]["name"] else ""
                            st.markdown(f"""
                            <div style='background-color: #1e293b; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #334155;'>
                                <div style='font-weight: bold; font-size: 14px;'>{r['name']}{is_cap}</div>
                                <div style='color: #94a3b8; font-size: 12px;'>{r['team']}</div>
                                <div style='color: #38bdf8; font-weight: bold; margin-top: 5px;'>{r['proj']:.1f} pts</div>
                            </div>
                            """, unsafe_allow_html=True)

    with lb:
        with st.container(border=True):
            st.markdown("**Bench order**")
            for i, r in enumerate(data["bench"], 1):
                rcls = "green" if r["reliability"] == "Reliable" else "red"
                st.markdown(f"{i}. {chip(r['pos_name'], 'blue')} **{r['name']}** {chip(r['reliability'], rcls)}", unsafe_allow_html=True)
                st.caption(f"proj {r['proj']:.1f} · {r['play_prob']:.0f}% fit")
        with st.expander("🧪 Auto-sub stress test"):
            cap_id = data["captain"].get("id") if data["captain"] else None
            vice_id = next((r["id"] for r in data["squad"] if data.get("vice") and r["name"] == data["vice"]["name"]), None)
            for t in auto_sub.stress_test(data["xi"], data["bench"], cap_id, vice_id):
                arm = f" · {t['armband']}" if t["armband"] else ""
                st.markdown(f"- **{t['if_missing']}** out → **{t['sub_in']}**{arm}")

elif page == "Advanced Analytics":
    tb1, tb2, tb3, tb4, tb5, tb6 = st.tabs(["📈 5-GW Horizon", "🌟 Ideal XI", "🃏 Chip Strategy", "🔀 Fixture Swings", "🤝 H2H", "💰 Squad Value"])
    with tb1:
        for r in sorted(data["squad"], key=lambda x: x["avg_fdr"]):
            st.markdown(f"{chip(r['pos_name'], 'blue')} **{r['name']}** ({r['team']}) — {squares(r['run'])} · avg FDR {r['avg_fdr']:.1f} · proj {r['proj']:.1f}/GW", unsafe_allow_html=True)
    with tb2:
        players, teams, events = ui_engine.fetch_bootstrap()
        fixtures = ui_engine.fetch_fixtures()
        form = ui_engine.team_form(gw, fixtures)
        ideal = ui_engine.ideal_xi(data, players=players, teams=teams, fixtures=fixtures, form=form, horizon=HORIZONS[st.session_state.horizon], use_defcon=st.session_state.defcon)
        options = ["(none)"] + [f"{r['name']} ({r['team']}, £{r['price']:.1f}m)" for pos in ("GK", "DEF", "MID", "FWD") for r in ideal["xi"][pos] if not r["owned"]]
        swap = st.selectbox("Force a market player into the template:", options, index=0)
        if swap != "(none)":
            name_part = swap.split(" (")[0]
            ideal = ui_engine.ideal_xi(data, players=players, teams=teams, fixtures=fixtures, form=form, horizon=HORIZONS[st.session_state.horizon], use_defcon=st.session_state.defcon, swap_in=next((pid for pid, p in players.items() if p["web_name"] == name_part), None))
        colA, colB = st.columns([3, 2])
        with colA:
            for pos in ("GK", "DEF", "MID", "FWD"):
                for r in ideal["xi"][pos]:
                    st.markdown(f"{'✅' if r['owned'] else '⬜'} **{r['name']}** ({r['team']}) — proj {r['proj']:.1f} · {squares(r['run'])}", unsafe_allow_html=True)
        with colB:
            st.metric("Template cost", f"£{ideal['cost']:.1f}m")
            for m in ideal["missing"]: st.markdown(f"- {m['pos_name']} **{m['name']}** ({m['team']}) £{m['price']:.1f}m")
    with tb3:
        chips = data["chips"]
        if chips.get("active"): st.success(f"**ACTIVE THIS GW:** {ui_engine.CHIP_LABEL.get(chips['active'], chips['active'])}")
        if chips.get("played"): st.markdown("**Played:** " + " · ".join(f"GW{gw_}: {ui_engine.CHIP_LABEL.get(c, c)}" for gw_, c in sorted(chips["played"].items(), key=lambda kv: int(kv[0]))))
        st.markdown("**Remaining (Set 1):** " + (", ".join(ui_engine.CHIP_LABEL.get(c, c) for c in chips["remaining_set1"]) if chips["remaining_set1"] else "—"))
        if chips.get("plan"):
            for k, v in chips["plan"].items(): st.markdown(f"- **{ui_engine.CHIP_LABEL.get(k, k)}**: {v}")
    with tb4:
        if data.get("fixture_swings"):
            for s in data["fixture_swings"]:
                cls = "green" if "GREEN" in s["type"] else "red" if "RED" in s["type"] else "amber"
                st.markdown(f"{chip(s['type'], cls)} {s['message']}", unsafe_allow_html=True)
        else: st.info("No sharp turns detected in the current window.")
    with tb5:
        rows = h2h_context_table(None)
        if rows:
            for r in rows: st.markdown(f"- **{r['matchup']}** — last 5: {r['wins']} · avg goals {r['avg_total_goals']}{' · DERBY' if r['derby'] else ''}")
    with tb6:
        v = data.get("value")
        if v:
            st.metric("Squad cost (15)", f"£{v['squad_cost']:.1f}m")
            c1v, c2v = st.columns(2)
            with c1v: st.metric("Price drift this GW", f"{v['this_gw_price_drift']:+.1f}m")
            with c2v: st.metric("Drift since GW1", f"{v['season_price_drift']:+.1f}m")
            for t in v["history_trend"]: st.markdown(f"- GW{t['gw']}: £{t['value']}m · bank £{t['bank']}m")

elif page == "Post-GW Review":
    proj = data.get("xi_proj")
    col1, col2 = st.columns(2)
    with col1:
        actual = st.number_input("Actual GW score", min_value=0, max_value=250, step=1)
        gw_in = st.number_input("Gameweek", min_value=1, max_value=38, value=max(1, gw - 1))
        if st.button("Log result", type="primary"):
            if ui_engine.log_actual_result(int(st.session_state.team_id), int(gw_in), float(actual)): st.success("Logged to ML training data!")
    with col2:
        st.metric("Engine Projection", f"{proj:.0f} pts")
        if actual and proj: st.metric("Delta", f"{actual - proj:+.0f} pts")
    hist = data.get("history", [])
    if hist:
        st.markdown("#### Performance History")
        import pandas as pd
        df = pd.DataFrame(hist)
        df["gw"] = df["event"].astype(str)
        df["points"] = df["points"].astype(float)
        st.line_chart(df.set_index("gw")["points"], use_container_width=True)

elif page == "Squad Sync":
    st.markdown("### 🗒️ Squad Sync (Blind Window)")
    st.caption("Select your 15 players. This saves to your URL and browser session.")
    players, teams, events = ui_engine.fetch_bootstrap()
    all_names = sorted([p["web_name"] for p in players.values()])
    selected_names = st.multiselect("Select 15 players", options=all_names, default=[r["name"] for r in data["squad"]], max_selections=15)
    
    col1, col2 = st.columns(2)
    with col1: itb = st.number_input("Bank (£m)", min_value=0.0, max_value=20.0, value=float(data["bank"] or 0.0), step=0.1)
    with col2: active_chip = st.selectbox("Active chip", ["none", "wildcard", "freehit", "3xc", "bboost"])
    
    if len(selected_names) > 0:
        c1, c2 = st.columns(2)
        with c1: cap_name = st.selectbox("Captain", selected_names, index=0)
        with c2: vice_name = st.selectbox("Vice-Captain", selected_names, index=1 if len(selected_names) > 1 else 0)

    if st.button("Save squad & Re-run Engine", type="primary"):
        if len(selected_names) != 15: st.error(f"Selected {len(selected_names)} players — exactly 15 required.")
        else:
            by_name = {p["web_name"].lower().replace(" ", ""): pid for pid, p in players.items()}
            new_ids = [by_name[name.lower().replace(" ", "")] for name in selected_names if name.lower().replace(" ", "") in by_name]
            if len(new_ids) == 15:
                st.query_params["seed"] = ",".join(map(str, new_ids))
                st.query_params["bank"] = str(itb)
                st.query_params["cap"] = str(by_name.get(cap_name.lower().replace(" ", "")))
                st.query_params["chip"] = active_chip
                st.session_state.override_seed = {"source": "seed", "note": "Pre-deadline workbench squad.", "picks": new_ids, "bank": float(itb), "captain_id": by_name.get(cap_name.lower().replace(" ", "")), "vice_id": by_name.get(vice_name.lower().replace(" ", "")), "active_chip": None if active_chip == "none" else active_chip}
                ui_engine.clear_cache()
                st.rerun()

st.markdown("---")
st.caption(f"FPL Toolz V2.1 · Data fetched at {fetch_time} · The engine is silent, the answers are loud.")