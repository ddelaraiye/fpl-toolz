import time
import re
from datetime import datetime
import streamlit as st
import pandas as pd
import ui_engine
import auto_sub

try:
    from h2h_adjuster import h2h_context_table
except Exception:
    def h2h_context_table(x): return []

st.set_page_config(page_title="FPL Toolz | Broadcast", page_icon="⚽", layout="wide", initial_sidebar_state="expanded")

# --- BROADCAST EDITION CSS ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Anton&family=Plus+Jakarta+Sans:wght@400;600;800&display=swap');

/* Base & Background */
.stApp {
    background-color: #120016;
    background-image: radial-gradient(circle at 50% 0%, rgba(0, 255, 135, 0.05) 0%, transparent 50%);
    font-family: 'Plus Jakarta Sans', sans-serif;
    color: #FFFFFF;
}

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* Typography */
h1, h2, h3, .anton-text { 
    font-family: 'Anton', sans-serif !important; 
    text-transform: uppercase; 
    letter-spacing: 1px; 
    font-weight: 400;
}
.stat-number { font-family: 'Anton', sans-serif; font-size: 42px; line-height: 1; color: #00FF87; }
.stat-label { font-family: 'Plus Jakarta Sans', sans-serif; font-size: 11px; font-weight: 800; letter-spacing: 2px; color: #A1A1AA; text-transform: uppercase; }

/* Panels (Flat, no rounded corners, green top border) */
.broadcast-panel {
    background: rgba(0, 0, 0, 0.3);
    border-top: 3px solid #00FF87;
    border-radius: 0px;
    padding: 20px;
    margin-bottom: 20px;
}
.section-label {
    font-family: 'Plus Jakarta Sans', sans-serif; font-size: 14px; font-weight: 800;
    letter-spacing: 3px; text-transform: uppercase; color: #FFFFFF;
    margin-bottom: 15px; display: flex; align-items: center; gap: 10px;
}
.section-label::before { content: "—"; color: #00FF87; font-weight: 900; }

/* Player Pitch Cards */
.pitch-card {
    background: rgba(0, 0, 0, 0.4);
    border-top: 3px solid #00FF87;
    border-radius: 0;
    padding: 12px 8px;
    text-align: center;
}
.pitch-card-name { font-weight: 800; font-size: 14px; color: #FFFFFF; }
.pitch-card-team { font-size: 11px; color: #A1A1AA; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
.pitch-card-pts { font-family: 'Anton', sans-serif; color: #00FF87; font-size: 20px; }
.captain-badge { background: #00FF87; color: #37003C; font-weight: 900; font-size: 10px; padding: 2px 6px; border-radius: 2px; margin-left: 4px; }

/* Pill Badges */
.pill {
    display: inline-block; padding: 4px 12px; border-radius: 999px;
    font-size: 0.75rem; font-weight: 800; letter-spacing: 0.5px; text-transform: uppercase;
}
.pill-green { background: #00FF87; color: #37003C; }
.pill-red { background: #FF3B30; color: #FFFFFF; }
.pill-blue { background: #007AFF; color: #FFFFFF; }
.pill-grey { background: #3F3F46; color: #FFFFFF; }

/* Broadcast Ticker */
.ticker-wrap { width: 100%; overflow: hidden; background-color: #0B000E; border-bottom: 1px solid #3F3F46; padding: 8px 0; margin-bottom: 20px; }
.ticker { display: inline-block; white-space: nowrap; padding-left: 100%; animation: ticker 25s linear infinite; font-family: 'Anton', sans-serif; font-size: 16px; color: #00FF87; text-transform: uppercase; }
.ticker-item { padding: 0 30px; display: inline-block; }
@keyframes ticker { 0% { transform: translate3d(0, 0, 0); } 100% { transform: translate3d(-100%, 0, 0); } }

/* Buttons & Inputs Override */
.stButton > button {
    background-color: #00FF87 !important; color: #37003C !important;
    border-radius: 999px !important; border: none !important;
    font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 800 !important;
    text-transform: uppercase; letter-spacing: 1px; padding: 10px 20px !important;
    transition: transform 0.1s; width: 100%;
}
.stButton > button:active { transform: scale(0.98); }
div[data-baseweb="select"] { background-color: #0B000E; border-radius: 0; border: 1px solid #3F3F46; }
div[data-baseweb="select"] > div { background-color: transparent; color: white; }
.stTextInput > div > div > input { background-color: #0B000E; color: white; border-radius: 0; border: 1px solid #3F3F46; }
.stTabs [data-baseweb="tab-list"] { gap: 20px; border-bottom: 1px solid #3F3F46; }
.stTabs [data-baseweb="tab"] { color: #A1A1AA; font-family: 'Plus Jakarta Sans'; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; border-radius: 0; padding-bottom: 10px; }
.stTabs [aria-selected="true"] { color: #00FF87 !important; border-bottom: 3px solid #00FF87 !important; }
[data-testid="stSidebar"] { background-color: #0B000E; border-right: 1px solid #3F3F46; }

/* Squares */
.sq { display:inline-flex; align-items:center; justify-content:center; width: 20px; height: 20px; border-radius: 2px; margin-right: 4px; font-size: 11px; font-weight: 900; color: #000; font-family: 'Plus Jakarta Sans'; }
.sq-green { background:#00FF87; } .sq-olive { background:#A3E635; }
.sq-orange { background:#FBBF24; } .sq-red { background:#FF3B30; color: #FFF; }
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
        out.append(f'<span class="sq {cls}" title="GW{x.get("gw")} vs {x.get("opp","?")}">{txt}</span>')
    return " ".join(out) if out else '<span class="sq sq-grey">-</span>'

def pill(label, cls): return f'<span class="pill pill-{cls}">{label}</span>'

# --- SESSION STATE & QUERY PARAMS ---
qp = st.query_params
if "team_id" in qp: st.session_state.team_id = qp["team_id"]
if "seed" in qp and qp["seed"]:
    try:
        seed_ids = [int(i) for i in qp["seed"].split(",")]
        if len(seed_ids) == 15:
            st.session_state.override_seed = {
                "source": "seed", "note": "Pre-deadline workbench squad.",
                "picks": seed_ids, "bank": float(qp.get("bank", 0)),
                "captain_id": int(qp.get("cap", 0)) if qp.get("cap") else None,
                "vice_id": None, "active_chip": qp.get("chip", None)
            }
    except: pass

defaults = {"team_id": "", "data": None, "horizon": "Next GW only", "defcon": False, "override_seed": None}
for k, v in defaults.items():
    if k not in st.session_state: st.session_state[k] = v
HORIZONS = {"Next GW only": 1, "Next 3 GWs": 3, "Next 5 GWs": 5}

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("<h2 style='color:#00FF87;'>⚽ FPL TOOLZ</h2>", unsafe_allow_html=True)
    st.markdown("<p class='stat-label'>BROADCAST EDITION V2.1</p>", unsafe_allow_html=True)
    st.markdown("---")
    
    with st.expander("❓ WHERE IS MY TEAM ID?"):
        st.markdown("""
        1. Go to [fantasy.premierleague.com](https://fantasy.premierleague.com/)
        2. Click **'Points'** or your team name.
        3. In the URL, find the number: `/entry/`**`123456`**`/event/9`
        """)
        
    user_input = st.text_input("TEAM ID OR URL", value=st.session_state.team_id, placeholder="e.g. 123456")
    
    if st.button("CONNECT & RUN", type="primary"):
        if user_input:
            match = re.search(r'\d+', user_input)
            if match:
                parsed_id = match.group()
                st.session_state.team_id = parsed_id
                st.query_params["team_id"] = parsed_id
                ui_engine.clear_cache()
                with st.spinner("FETCHING LIVE DATA..."):
                    try:
                        st.session_state.data = ui_engine.run_engine(
                            int(parsed_id), HORIZONS[st.session_state.horizon], 
                            st.session_state.defcon, override_seed=st.session_state.override_seed
                        )
                    except Exception as e:
                        st.error(str(e))
            else:
                st.error("INVALID TEAM ID.")

    if st.session_state.override_seed:
        if st.button("❌ CLEAR SYNC", type="secondary"):
            st.session_state.override_seed = None
            st.query_params.pop("seed", None)
            ui_engine.clear_cache()
            st.rerun()

    st.markdown("---")
    st.session_state.horizon = st.radio("HORIZON", list(HORIZONS.keys()), index=list(HORIZONS.keys()).index(st.session_state.horizon))
    st.session_state.defcon = st.toggle("DEFCON BOOST", value=st.session_state.defcon)
    
    if st.session_state.data is not None:
        if st.button("RE-RUN ENGINE"):
            with st.spinner("RE-RUNNING..."):
                st.session_state.data = ui_engine.run_engine(
                    int(st.session_state.team_id), HORIZONS[st.session_state.horizon], 
                    st.session_state.defcon, override_seed=st.session_state.override_seed
                )

    st.markdown("---")
    page = st.radio("NAVIGATION", ["Dashboard", "Advanced Analytics", "Squad Sync", "Post-GW Review"])

# --- MAIN CONTENT ---
data = st.session_state.data
if data is None:
    st.markdown("<h1 style='text-align:center; margin-top:100px; font-size:60px;'>THE ENGINE IS SILENT.<br><span style='color:#00FF87;'>THE ANSWERS ARE LOUD.</span></h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:#A1A1AA; font-family:Plus Jakarta Sans;'>Paste your FPL Team ID in the sidebar to begin the broadcast.</p>", unsafe_allow_html=True)
    st.stop()

if data.get("error"):
    st.error(data["error"])
    st.stop()

fetch_time = datetime.now().strftime("%H:%M:%S")

# --- BROADCAST TICKER ---
deadline_txt = "PASSED"
if data.get("deadline_epoch"):
    secs = data["deadline_epoch"] - int(time.time())
    if secs > 0:
        d, r = divmod(secs, 86400); h, r = divmod(r, 3600); m, _ = divmod(r, 60)
        deadline_txt = f"{d}D {h}H {m}M" if d else f"{h}H {m}M"

st.markdown(f"""
<div class="ticker-wrap">
    <div class="ticker">
        <span class="ticker-item">● {data['team_name'].upper()}</span>
        <span class="ticker-item">● GW{data['gw']}</span>
        <span class="ticker-item">● DEADLINE: {deadline_txt}</span>
        <span class="ticker-item">● SQUAD SOURCE: {data['squad_source'].replace('_', ' ').upper()}</span>
        <span class="ticker-item" style="color: #FFF;">● CAPTAIN: {data['captain']['name'].upper() if data['captain'] else 'TBD'}</span>
    </div>
</div>
""", unsafe_allow_html=True)

# --- STAT BOARDS HEADER ---
c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.markdown(f"<div class='stat-label'>GAMEWEEK</div><div class='stat-number'>{data['gw']}</div>", unsafe_allow_html=True)
with c2:
    st.markdown(f"<div class='stat-label'>PROJECTED XI</div><div class='stat-number'>{data['xi_proj']:.0f}</div>", unsafe_allow_html=True)
with c3:
    st.markdown(f"<div class='stat-label'>IN THE BANK</div><div class='stat-number'>£{data['bank'] or 0:.1f}M</div>", unsafe_allow_html=True)
with c4:
    st.markdown(f"<div class='stat-label'>FREE TRANSFERS</div><div class='stat-number'>{data['fts']}</div>", unsafe_allow_html=True)
with c5:
    st.markdown(f"<div class='stat-label'>SQUAD SOURCE</div><div class='stat-number' style='font-size:24px; margin-top:8px;'>{data['squad_source'].upper()}</div>", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#3F3F46; margin: 20px 0;'>", unsafe_allow_html=True)

# ===============================================================
# DASHBOARD TAB
# ===============================================================
if page == "Dashboard":
    
    # 1. THE ACTION PLAN
    st.markdown("<div class='section-label'>THE WEEKLY CHECKLIST</div>", unsafe_allow_html=True)
    st.markdown('<div class="broadcast-panel" style="padding: 15px;">', unsafe_allow_html=True)
    ac1, ac2, ac3 = st.columns(3)
    with ac1:
        st.markdown("<p class='stat-label'>1. CAPTAIN</p>", unsafe_allow_html=True)
        if data.get("captain"): st.markdown(f"<span class='anton-text' style='font-size:24px; color:#00FF87;'>{data['captain']['name']}</span>", unsafe_allow_html=True)
    with ac2:
        st.markdown("<p class='stat-label'>2. TRANSFER</p>", unsafe_allow_html=True)
        if data["transfer"]["verdict"] == "TRANSFER":
            st.markdown(f"<span class='anton-text' style='font-size:24px; color:#FBBF24;'>SELL {data['transfer']['sell']['name']}</span>", unsafe_allow_html=True)
        else: st.markdown(f"<span class='anton-text' style='font-size:24px; color:#A1A1AA;'>SAVE FT</span>", unsafe_allow_html=True)
    with ac3:
        st.markdown("<p class='stat-label'>3. LINEUP</p>", unsafe_allow_html=True)
        st.markdown(f"<span class='anton-text' style='font-size:24px; color:#FFFFFF;'>CONFIRM XI</span>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # 2. CAPTAIN & TRANSFER
    cap_col, tr_col = st.columns(2, gap="large")

    with cap_col:
        st.markdown("<div class='section-label'>THE CAPTAIN</div>", unsafe_allow_html=True)
        captain = data["captain"]
        if captain:
            st.markdown('<div class="broadcast-panel">', unsafe_allow_html=True)
            vcls = "green" if "STRONG" in captain["verdict"] else "amber"
            st.markdown(f"<div class='anton-text' style='font-size:38px;'>{captain['name']} {pill(captain['verdict'], vcls)}</div>", unsafe_allow_html=True)
            st.markdown(f"<p style='color:#A1A1AA; margin-bottom:15px;'>{captain['team']} · vs {captain['fixture']} · £{captain['price']:.1f}M</p>", unsafe_allow_html=True)
            
            st.markdown(f"<div class='stat-label'>SCORE</div><div class='stat-number'>{captain['score']:.1f} / 10</div>", unsafe_allow_html=True)
            st.markdown(f"<p style='color:#00FF87; font-size:14px; margin-top:5px;'>PROJ: {captain['proj']:.1f} PTS (x2 = {captain['proj'] * 2:.1f})</p>", unsafe_allow_html=True)
            
            f = captain["factors"]
            st.markdown(f"<p style='color:#A1A1AA; font-size:13px; margin-top:15px; border-top: 1px solid #3F3F46; padding-top:10px;'><b>WHY:</b> FIX {f['fixture']:.1f} · FORM {f['form']:.1f} · UNDER {f['underlying']:.1f} · ROLE {f['role']:.0f}</p>", unsafe_allow_html=True)
            if data.get("vice"): st.markdown(f"<p style='color:#A1A1AA; font-size:13px;'><b>VICE:</b> {data['vice']['name']}</p>", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    with tr_col:
        st.markdown("<div class='section-label'>THE TRANSFER</div>", unsafe_allow_html=True)
        t = data["transfer"]
        st.markdown('<div class="broadcast-panel">', unsafe_allow_html=True)
        vmap = {"TRANSFER": "green", "SAVE": "amber", "HIT": "red", "WILDCARD ACTIVE": "blue"}
        st.markdown(pill(t["verdict"], vmap.get(t["verdict"], "amber")), unsafe_allow_html=True)
        
        if t.get("sell") and t.get("buys") and not data.get("wc_active"):
            sell = t["sell"]
            buy_options = [b["name"] for b in t["buys"]]
            selected_buy = st.selectbox("SELECT TARGET", buy_options, index=0)
            best = next(b for b in t["buys"] if b["name"] == selected_buy)
            
            st.markdown(f"<div class='anton-text' style='font-size:32px; margin-top:15px;'>SELL {sell['name']} → BUY {best['name']}</div>", unsafe_allow_html=True)
            gain = round(best["proj"] - sell["proj"], 1)
            
            cA, cB = st.columns(2)
            with cA: st.markdown(f"<div class='stat-label'>HORIZON GAIN</div><div class='stat-number' style='color:#00FF87;'>+{gain:.1f}</div>", unsafe_allow_html=True)
            with cB: st.markdown(f"<div class='stat-label'>PRICE DELTA</div><div class='stat-number' style='color:#FFF;'>{best['price'] - sell['price']:+.1f}M</div>", unsafe_allow_html=True)
            
            st.markdown(f"<div style='margin-top:15px;'><span class='stat-label'>SELL RUN</span><br>{squares(sell['run'])}</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='margin-top:10px;'><span class='stat-label'>BUY RUN</span><br>{squares(best['run'])}</div>", unsafe_allow_html=True)
        elif data.get("wc_active"):
            st.markdown(f"<p style='color:#A1A1AA; margin-top:10px;'>{t['reason']}</p>", unsafe_allow_html=True)
            for b in t["buys"][:3]:
                st.markdown(f"<p style='color:#00FF87; font-size:18px; margin-top:10px;'><b>{b['name']}</b> ({b['team']}) — {b['proj']:.1f} PTS</p>", unsafe_allow_html=True)
        else:
            st.markdown(f"<p style='color:#A1A1AA; margin-top:10px;'>{t['reason']}</p>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # 3. VISUAL PITCH
    st.markdown("<div class='section-label'>THE LINEUP</div>", unsafe_allow_html=True)
    st.markdown('<div class="broadcast-panel">', unsafe_allow_html=True)
    st.markdown(f"<div class='stat-label'>PROJECTED TEAM SCORE</div><div class='stat-number'>{data['xi_proj']:.0f} PTS</div>", unsafe_allow_html=True)
    st.markdown(f"<p style='color:#00FF87; font-size:12px;'>BENCH ADDS {data['bench_proj']:.0f}</p>", unsafe_allow_html=True)
    
    rows_by_pos = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    for r in data["xi"]: rows_by_pos[r["pos_name"]].append(r)
    
    for pos in ("FWD", "MID", "DEF", "GK"):
        if rows_by_pos[pos]:
            st.markdown(f"<div style='text-align:center; color:#64748B; font-family:Anton; font-size:14px; letter-spacing:2px; margin-top:20px;'>{pos}</div>", unsafe_allow_html=True)
            cols = st.columns(len(rows_by_pos[pos]))
            for idx, r in enumerate(rows_by_pos[pos]):
                with cols[idx]:
                    is_cap = "<span class='captain-badge'>C</span>" if r["name"] == data["captain"]["name"] else ""
                    st.markdown(f"""
                    <div class='pitch-card'>
                        <div class='pitch-card-name'>{r['name']}{is_cap}</div>
                        <div class='pitch-card-team'>{r['team']}</div>
                        <div class='pitch-card-pts'>{r['proj']:.1f}</div>
                    </div>
                    """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # 4. BENCH
    st.markdown("<div class='section-label'>THE BENCH</div>", unsafe_allow_html=True)
    st.markdown('<div class="broadcast-panel">', unsafe_allow_html=True)
    cols = st.columns(4)
    for i, r in enumerate(data["bench"]):
        with cols[i]:
            st.markdown(f"<p class='stat-label'>SUB {i+1}</p>", unsafe_allow_html=True)
            st.markdown(f"<div class='anton-text' style='font-size:16px;'>{r['name']}</div>", unsafe_allow_html=True)
            st.markdown(f"<p style='color:#A1A1AA; font-size:12px;'>{r['proj']:.1f} PTS · {r['play_prob']:.0f}% FIT</p>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ===============================================================
# ADVANCED ANALYTICS TAB
# ===============================================================
elif page == "Advanced Analytics":
    st.markdown("<div class='section-label'>ADVANCED ANALYTICS</div>", unsafe_allow_html=True)
    tb1, tb2, tb3, tb4 = st.tabs(["5-GW HORIZON", "IDEAL XI", "CHIPS", "HISTORY"])
    
    with tb1:
        st.markdown('<div class="broadcast-panel">', unsafe_allow_html=True)
        for r in sorted(data["squad"], key=lambda x: x["avg_fdr"]):
            st.markdown(f"{pill(r['pos_name'], 'grey')} <span class='anton-text' style='font-size:18px;'>{r['name']}</span> ({r['team']}) — {squares(r['run'])} · AVG FDR {r['avg_fdr']:.1f}", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
    with tb2:
        st.markdown('<div class="broadcast-panel">', unsafe_allow_html=True)
        players, teams, events = ui_engine.fetch_bootstrap()
        fixtures = ui_engine.fetch_fixtures()
        form = ui_engine.team_form(data["gw"], fixtures)
        ideal = ui_engine.ideal_xi(data, players=players, teams=teams, fixtures=fixtures, form=form, horizon=HORIZONS[st.session_state.horizon])
        st.markdown(f"<div class='stat-label'>TEMPLATE COST</div><div class='stat-number'>£{ideal['cost']:.1f}M</div>", unsafe_allow_html=True)
        for pos in ("GK", "DEF", "MID", "FWD"):
            for r in ideal["xi"][pos]:
                st.markdown(f"{'✅' if r['owned'] else '⬜'} <span class='anton-text' style='font-size:18px;'>{r['name']}</span> — {r['proj']:.1f} PTS", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
    with tb3:
        st.markdown('<div class="broadcast-panel">', unsafe_allow_html=True)
        chips = data["chips"]
        if chips.get("active"): st.markdown(pill(f"ACTIVE: {chips['active'].upper()}", "green"), unsafe_allow_html=True)
        for k, v in chips.get("plan", {}).items(): st.markdown(f"- <b>{k.upper()}</b>: {v}", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
    with tb4:
        st.markdown('<div class="broadcast-panel">', unsafe_allow_html=True)
        hist = data.get("history", [])
        if hist:
            df = pd.DataFrame(hist)
            st.line_chart(df.set_index("event")["points"], color="#00FF87")
        st.markdown('</div>', unsafe_allow_html=True)

# ===============================================================
# SQUAD SYNC TAB
# ===============================================================
elif page == "Squad Sync":
    st.markdown("<div class='section-label'>SQUAD SYNC (BLIND WINDOW)</div>", unsafe_allow_html=True)
    with st.container():
        st.markdown('<div class="broadcast-panel">', unsafe_allow_html=True)
        players, teams, events = ui_engine.fetch_bootstrap()
        all_names = sorted([p["web_name"] for p in players.values()])
        selected_names = st.multiselect("SELECT 15 PLAYERS", options=all_names, default=[r["name"] for r in data["squad"]], max_selections=15)
        
        c1, c2 = st.columns(2)
        with c1: itb = st.number_input("BANK (£M)", value=float(data["bank"] or 0.0), step=0.1)
        with c2: active_chip = st.selectbox("ACTIVE CHIP", ["none", "wildcard", "freehit", "3xc", "bboost"])
        
        if len(selected_names) > 0:
            cc1, cc2 = st.columns(2)
            with cc1: cap_name = st.selectbox("CAPTAIN", selected_names, index=0)
            with cc2: vice_name = st.selectbox("VICE-CAPTAIN", selected_names, index=1 if len(selected_names) > 1 else 0)

        if st.button("SAVE SQUAD & RE-RUN", type="primary"):
            if len(selected_names) == 15:
                by_name = {p["web_name"].lower(): pid for pid, p in players.items()}
                new_ids = [by_name[n.lower()] for n in selected_names if n.lower() in by_name]
                if len(new_ids) == 15:
                    st.query_params["seed"] = ",".join(map(str, new_ids))
                    st.session_state.override_seed = {"source": "seed", "note": "Synced via UI", "picks": new_ids, "bank": itb, "captain_id": by_name.get(cap_name.lower()), "vice_id": by_name.get(vice_name.lower()), "active_chip": active_chip}
                    ui_engine.clear_cache()
                    st.rerun()
            else:
                st.error("SELECT EXACTLY 15 PLAYERS.")
        st.markdown('</div>', unsafe_allow_html=True)

# ===============================================================
# POST-GW REVIEW TAB
# ===============================================================
elif page == "Post-GW Review":
    st.markdown("<div class='section-label'>POST-GW REVIEW</div>", unsafe_allow_html=True)
    st.markdown('<div class="broadcast-panel">', unsafe_allow_html=True)
    
    hist = data.get("history", [])
    if hist:
        last_pts = hist[-1].get("points", 0)
        avg_5 = sum(h.get("points", 0) for h in hist[-5:]) / len(hist[-5:]) if hist else 0
        best_gw = max(h.get("points", 0) for h in hist)
        
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown(f"<div class='stat-label'>LAST GW</div><div class='stat-number'>{last_pts}</div>", unsafe_allow_html=True)
        with c2: st.markdown(f"<div class='stat-label'>5-GW AVG</div><div class='stat-number'>{avg_5:.1f}</div>", unsafe_allow_html=True)
        with c3: st.markdown(f"<div class='stat-label'>BEST GW</div><div class='stat-number'>{best_gw}</div>", unsafe_allow_html=True)
        st.markdown("<hr style='border-color:#3F3F46; margin: 20px 0;'>", unsafe_allow_html=True)

    proj = data.get("xi_proj")
    col1, col2 = st.columns(2)
    with col1:
        actual = st.number_input("ACTUAL GW SCORE", min_value=0, max_value=250, step=1)
        gw_in = st.number_input("GAMEWEEK", min_value=1, max_value=38, value=max(1, data["gw"] - 1))
        if st.button("LOG RESULT", type="primary"):
            if ui_engine.log_actual_result(int(st.session_state.team_id), int(gw_in), float(actual)): 
                st.success("LOGGED TO ML TRAINING DATA!")
    with col2:
        st.markdown(f"<div class='stat-label'>ENGINE PROJECTION</div><div class='stat-number'>{proj:.0f}</div>", unsafe_allow_html=True)
        if actual and proj: 
            delta = actual - proj
            color = "#00FF87" if delta >= 0 else "#FF3B30"
            st.markdown(f"<div class='stat-label'>DELTA</div><div class='stat-number' style='color:{color};'>{delta:+.0f}</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("---")
st.markdown(f"<p style='text-align:center; color:#3F3F46; font-size:11px; letter-spacing:1px;'>FPL TOOLZ V2.1 BROADCAST · DATA FETCHED AT {fetch_time} · NOT AFFILIATED WITH THE PREMIER LEAGUE</p>", unsafe_allow_html=True)