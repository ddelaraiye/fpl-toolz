import re
import time
from datetime import datetime, timezone, timedelta

import streamlit as st
import streamlit.components.v1 as components

import ui_engine
import auto_sub  # part of the engine bundle (bench/auto-sub logic)

try:
    from h2h_adjuster import h2h_context_table
except Exception:            # cloud build without h2h.csv must not kill the app
    h2h_context_table = None

st.set_page_config(page_title="FPL Toolz — Command Center",
                   page_icon="⚽", layout="wide",
                   initial_sidebar_state="expanded")

# ================================================================
#  BROADCAST DESIGN SYSTEM v2 — softened
#  (#120016 base / #00FF87 neon / Anton + Plus Jakarta Sans)
#  Flat panels -> rounded glass panels, soft shadows, hover motion
# ================================================================
st.markdown("""
<style>
@import url("https://fonts.googleapis.com/css2?family=Anton&family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap");

/* ---------- base ---------- */
.stApp {
  background-color: #120016;
  background-image:
    radial-gradient(1000px 480px at 50% -200px, rgba(0,255,135,0.07), transparent 62%),
    radial-gradient(800px 400px at 100% 0%, rgba(148,124,255,0.05), transparent 60%);
  color: rgba(255,255,255,0.92);
  font-family: "Plus Jakarta Sans", Inter, system-ui, sans-serif;
}
.stApp, .stApp p, .stApp span, .stApp li, .stApp label {
  color: rgba(255,255,255,0.92);
}
.stApp .stCaption, [data-testid="stCaptionContainer"],
.stApp small { color: rgba(255,255,255,0.55) !important; }
hr { border: 0; border-top: 1px solid rgba(255,255,255,0.08); }
#MainMenu, footer { visibility: hidden; }
[data-testid="stMainBlockContainer"] {
  padding-top: 1.1rem !important; padding-bottom: 2.4rem !important;
  max-width: 1240px;
}

.big-font {
  font-family: Anton, Impact, sans-serif;
  font-size: 30px; font-weight: 400; letter-spacing: 0.5px;
  text-transform: uppercase; color: #ffffff; line-height: 1.08;
}

/* ---------- ticker ---------- */
.ticker {
  display: flex; align-items: center; flex-wrap: wrap; gap: 10px;
  background: rgba(11, 0, 14, 0.7);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 999px;
  padding: 8px 18px; margin: 0 0 14px 0;
  font-size: 12.5px; font-weight: 600; letter-spacing: 0.4px;
  color: rgba(255,255,255,0.75);
}
.ticker .live-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #00ff87; box-shadow: 0 0 12px rgba(0,255,135,0.9);
  animation: pulse 1.6s ease-in-out infinite;
}
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.45; } }
.ticker b { color: #00ff87; }
.ticker .tk-brand {
  font-family: Anton, Impact, sans-serif; font-size: 14px;
  letter-spacing: 1.5px; color: #fff;
}
.ticker .tk-sep { color: rgba(255,255,255,0.22); }
.ticker .tk-fill { flex: 1; }
.ticker .tk-cta { color: #00ff87; font-weight: 800; }

/* ---------- stat board (glass panel) ---------- */
.board {
  display: flex; flex-wrap: wrap;
  background:
    linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.015)),
    rgba(11, 0, 14, 0.55);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 18px;
  box-shadow: 0 12px 32px rgba(0,0,0,0.35);
  overflow: hidden;
}
.board .cell {
  flex: 1 1 150px; padding: 16px 20px;
  border-right: 1px solid rgba(255,255,255,0.06);
}
.board .cell:last-child { border-right: none; }
.board .k {
  font-size: 10px; font-weight: 800; letter-spacing: 2px;
  text-transform: uppercase; color: rgba(255,255,255,0.48);
}
.board .v {
  font-family: Anton, Impact, sans-serif; font-size: 32px;
  color: #ffffff; margin-top: 4px; line-height: 1;
}
.board .v.green { color: #00ff87; text-shadow: 0 0 22px rgba(0,255,135,0.35); }
.board .s { font-size: 11.5px; color: rgba(255,255,255,0.5); margin-top: 4px; }

/* ---------- section labels ---------- */
.sec { display: flex; align-items: center; gap: 10px; margin: 26px 0 12px; }
.sec .dash {
  width: 20px; height: 3px; border-radius: 2px;
  background: linear-gradient(90deg, #00ff87, rgba(0,255,135,0.2));
  flex: 0 0 auto;
}
.sec .txt {
  font-size: 12.5px; font-weight: 800; letter-spacing: 2px;
  text-transform: uppercase; color: rgba(255,255,255,0.92);
}

/* ---------- player cards (soft glass, hover lift) ---------- */
.player-card {
  background:
    linear-gradient(180deg, rgba(255,255,255,0.055), rgba(255,255,255,0.02)),
    rgba(11, 0, 14, 0.55);
  border: 1px solid rgba(255,255,255,0.09);
  border-radius: 14px;
  box-shadow: 0 8px 22px rgba(0,0,0,0.3);
  padding: 13px 8px 11px; text-align: center;
  transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease;
}
.player-card:hover {
  transform: translateY(-3px);
  border-color: rgba(0,255,135,0.45);
  box-shadow: 0 14px 30px rgba(0,0,0,0.42), 0 0 0 1px rgba(0,255,135,0.15);
}
.player-card.captain { border-color: rgba(0,255,135,0.5); }
.player-name {
  font-weight: 800; font-size: 13.5px; color: #fff;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.player-sub { color: rgba(255,255,255,0.5); font-size: 11px; margin-top: 2px; }
.player-pts {
  font-family: Anton, Impact, sans-serif; color: #00ff87;
  font-size: 21px; margin-top: 6px; line-height: 1;
}
.player-pts em { font-style: normal; font-size: 10px; color: rgba(255,255,255,0.45); }
.cap-badge {
  display: inline-block; background: #00ff87; color: #37003c;
  font-weight: 800; font-size: 9.5px; padding: 1px 6px;
  border-radius: 999px; margin-left: 4px; vertical-align: middle;
}
.pitch-label {
  text-align: center; color: rgba(255,255,255,0.38); margin: 16px 0 8px;
  font-size: 10.5px; font-weight: 800; letter-spacing: 2.5px;
}

/* ---------- chips & fixture squares ---------- */
.chip {
  display: inline-block; padding: 2px 10px; border-radius: 999px;
  font-size: .72em; font-weight: 800; letter-spacing: 0.4px;
}
.chip-green  { background: rgba(0,255,135,0.12);  color: #00ff87; }
.chip-red    { background: rgba(255,77,109,0.14); color: #ff7a93; }
.chip-amber  { background: rgba(255,184,77,0.14); color: #ffc46b; }
.chip-blue   { background: rgba(148,124,255,0.16); color: #b3a4ff; }
.sq {
  display: inline-block; width: 15px; height: 15px;
  border-radius: 4px; margin-right: 3px; vertical-align: middle;
  box-shadow: inset 0 -4px 6px rgba(0,0,0,0.25);
}
.sq-green { background: #00e07a; } .sq-olive { background: #a3c93a; }
.sq-orange { background: #ffb14d; } .sq-red { background: #ff4d6d; }
.sq-grey { background: #332038; }

/* ---------- fixtures strip (NEXT UP) ---------- */
.fx-strip {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
}
.fx-day {
  background: rgba(0,255,135,0.1); color: #00ff87;
  font-weight: 800; font-size: 10.5px; letter-spacing: 1.5px;
  padding: 4px 10px; border-radius: 999px;
}
.fx-match {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.09);
  border-radius: 10px; padding: 5px 12px;
  font-size: 12.5px; font-weight: 700; color: rgba(255,255,255,0.88);
}
.fx-match .t { color: rgba(255,255,255,0.55); font-weight: 600; }

/* ---------- trajectory bars ---------- */
.traj { display: flex; align-items: flex-end; gap: 7px; height: 84px; }
.traj .bar {
  flex: 1; border-radius: 6px 6px 2px 2px;
  background: linear-gradient(180deg, #00ff87, rgba(0,255,135,0.25));
  box-shadow: 0 4px 14px rgba(0,255,135,0.15);
  position: relative; min-height: 4px;
}
.traj .bar span {
  position: absolute; top: -18px; left: 0; right: 0; text-align: center;
  font-family: Anton, sans-serif; font-size: 11px; color: #fff;
}
.traj .bar em {
  position: absolute; bottom: -18px; left: 0; right: 0; text-align: center;
  font-style: normal; font-size: 9.5px; color: rgba(255,255,255,0.45);
  font-weight: 700;
}

/* ---------- buttons ---------- */
.stButton > button {
  border-radius: 999px; font-weight: 800; letter-spacing: 0.4px;
  border: 1px solid rgba(255,255,255,0.18) !important;
  background: rgba(255,255,255,0.04); color: #ffffff !important;
  transition: all .15s ease;
}
.stButton > button[kind="primary"], .stButton > button[data-testid="stBaseButton-primary"] {
  background: linear-gradient(135deg, #00ff87, #00d47a) !important;
  color: #37003c !important;
  border: none !important;
  box-shadow: 0 6px 18px rgba(0,255,135,0.25);
}
.stButton > button:hover {
  border-color: rgba(0,255,135,0.55) !important; filter: brightness(1.08);
}

/* ---------- metrics / tabs / containers / expanders ---------- */
div[data-testid="stMetric"] {
  background:
    linear-gradient(180deg, rgba(255,255,255,0.045), rgba(255,255,255,0.01)),
    rgba(11, 0, 14, 0.5);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 14px; padding: 12px 16px;
}
div[data-testid="stMetricValue"] {
  font-family: Anton, Impact, sans-serif; font-size: 24px; color: #fff;
}
div[data-testid="stMetricLabel"] p {
  font-size: 10px; font-weight: 800; letter-spacing: 1.8px;
  text-transform: uppercase; color: rgba(255,255,255,0.5);
}
div[data-testid="stMetricDelta"] { font-size: 11px; }

.stTabs [data-baseweb="tab-list"] {
  border-bottom: 1px solid rgba(255,255,255,0.1); gap: 2px;
}
.stTabs [data-baseweb="tab"] {
  background-color: transparent !important; font-weight: 800;
  font-size: 11.5px; letter-spacing: 1.2px; text-transform: uppercase;
  color: rgba(255,255,255,0.55) !important; padding: 10px 14px;
  border-radius: 8px 8px 0 0;
}
.stTabs [data-baseweb="tab-highlight"] { height: 3px; background: #00ff87; }
.stTabs [aria-selected="true"] { color: #00ff87 !important; }

div[data-testid="stVerticalBlockBorderWrapper"] {
  background:
    linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01)),
    rgba(11, 0, 14, 0.5);
  border: 1px solid rgba(255,255,255,0.08) !important;
  border-radius: 18px !important;
  box-shadow: 0 10px 28px rgba(0,0,0,0.3);
}
[data-testid="stExpander"] {
  background: rgba(11, 0, 14, 0.5);
  border: 1px solid rgba(255,255,255,0.08) !important; border-radius: 14px;
}
[data-testid="stExpander"] summary, [data-testid="stExpander"] details {
  color: #fff;
}
[data-testid="stAlert"] { border-radius: 14px; }
[data-testid="stCodeBlock"] { border-radius: 12px; }

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] {
  background: #0b000e;
  border-right: 1px solid rgba(255,255,255,0.07);
}
[data-testid="stSidebar"] .stButton > button { width: 100%; }
[data-testid="stSidebar"] [role="radiogroup"] label {
  font-weight: 800; font-size: 12px; letter-spacing: 1.2px;
  text-transform: uppercase; color: rgba(255,255,255,0.72);
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover { color: #00ff87; }

/* ---------- inputs ---------- */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
  background: rgba(0, 0, 0, 0.35) !important; color: #fff !important;
  border: 1px solid rgba(255,255,255,0.14) !important; border-radius: 12px;
}
div[data-baseweb="select"] > div {
  background: rgba(0, 0, 0, 0.35) !important;
  border: 1px solid rgba(255,255,255,0.14) !important;
  border-radius: 12px;
}
div[data-baseweb="select"] > div > div { color: #fff; }
ul[role="listbox"] { background: #1a0120 !important; }
</style>
""", unsafe_allow_html=True)


def squares(run, horizon=None):
    out = []
    for x in (run or [])[:horizon or 5]:
        f = x.get("fdr", 3)
        cls = ("sq-green" if f <= 1.99 else "sq-olive" if f <= 2.99 else
               "sq-orange" if f <= 3.99 else "sq-red")
        out.append(f'<span class="sq {cls}" title="GW{x.get("gw")} '
                   f'vs {x.get("opp","?")} ({x.get("ha","")}) FDR {f}">'
                   f'</span>')
    return " ".join(out) if out else '<span class="sq sq-grey"></span>'


def chip(label, cls):
    return f'<span class="chip chip-{cls}">{label}</span>'


def sec(label):
    return (f"<div class='sec'><span class='dash'></span>"
            f"<span class='txt'>{label}</span></div>")


def player_card(r, captain_name=None):
    cap = bool(captain_name and r["name"] == captain_name)
    badge = "<span class='cap-badge'>C</span>" if cap else ""
    team = r.get("team")
    sub = " · ".join(x for x in (team,
                                 f"£{r['price']:.1f}m" if r.get("price")
                                 is not None else None) if x)
    run_html = squares(r.get("run"))
    return (f"<div class='player-card{' captain' if cap else ''}'>"
            f"<div class='player-name'>{r['name']}{badge}</div>"
            f"<div class='player-sub'>{sub}</div>"
            f"<div class='player-pts'>{r['proj']:.1f}<em> pts</em></div>"
            f"<div style='margin-top:5px;'>{run_html}</div>"
            f"</div>")


def board(cells):
    """cells: list of (key, value, value_cls, sub) — Game Bloc stat board."""
    html = ["<div class='board'>"]
    for k, v, cls, sub in cells:
        sub_html = f"<div class='s'>{sub}</div>" if sub else ""
        html.append(f"<div class='cell'><div class='k'>{k}</div>"
                    f"<div class='v {cls}'>{v}</div>{sub_html}</div>")
    html.append("</div>")
    return "".join(html)


def countdown_bar(deadline_epoch, gw):
    """Real ticking countdown (JS inside an iframe component)."""
    if not deadline_epoch:
        return
    urgent = "rgba(255,77,109,"   # <3h red
    soon = "rgba(255,184,77,"     # <24h amber
    calm = "rgba(0,255,135,"      # green
    html = f"""
    <style>
      html, body {{ margin:0; padding:0; background:transparent;
                    font-family:"Plus Jakarta Sans",Inter,sans-serif; }}
      .wrap {{ display:flex; align-items:center; justify-content:center;
               gap:10px; background:rgba(11,0,14,0.7);
               border:1px solid rgba(255,255,255,0.08);
               border-radius:14px; padding:9px 16px;
               box-shadow:0 8px 22px rgba(0,0,0,0.3); }}
      .lbl {{ font-size:10px; font-weight:800; letter-spacing:2px;
              color:rgba(255,255,255,0.5); text-transform:uppercase; }}
      .cd {{ display:flex; gap:6px; }}
      .seg {{ min-width:52px; text-align:center;
              background:rgba(255,255,255,0.05);
              border:1px solid {calm}0.25); border-radius:10px;
              padding:4px 8px; }}
      .seg .n {{ font-family:Anton,Impact,sans-serif; font-size:20px;
                 color:#00ff87; line-height:1; }}
      .seg .u {{ font-size:8.5px; font-weight:800; letter-spacing:1.5px;
                 color:rgba(255,255,255,0.5); margin-top:2px;
                 text-transform:uppercase; }}
      .live {{ font-family:Anton,Impact,sans-serif; font-size:20px;
               color:#00ff87; text-shadow:0 0 16px rgba(0,255,135,0.6); }}
      .sep {{ font-size:8.5px; font-weight:800; color:rgba(255,255,255,0.4);
              letter-spacing:2px; }}
    </style>
    <div class="wrap" id="wrap">
      <span class="lbl">GW{gw} Deadline</span>
      <div class="cd" id="cd"></div>
    </div>
    <script>
      const target = {int(deadline_epoch)} * 1000;
      const pad = n => String(n).padStart(2, "0");
      function seg(n, u) {{
        return `<div class="seg"><div class="n">${{n}}</div>
                <div class="u">${{u}}</div></div>`;
      }}
      function tick() {{
        const el = document.getElementById("cd");
        const wrap = document.getElementById("wrap");
        let s = Math.floor((target - Date.now()) / 1000);
        if (s <= 0) {{
          el.innerHTML = `<span class="live">GW{gw} LIVE NOW</span>`;
          return;
        }}
        const d = Math.floor(s / 86400); s -= d * 86400;
        const h = Math.floor(s / 3600);  s -= h * 3600;
        const m = Math.floor(s / 60);
        const sec = s - m * 60;
        el.innerHTML = (d ? seg(d, "days") : "") + seg(h, "hrs") +
                       seg(m, "min") + seg(sec, "sec");
        if (s < 3 * 3600) wrap.style.borderColor = "{urgent}0.5)";
        else if (s < 24 * 3600) wrap.style.borderColor = "{soon}0.45)";
        setTimeout(tick, 1000);
      }}
      tick();
    </script>
    """
    components.html(html, height=52)


def fixtures_strip():
    """NEXT UP — upcoming matches as compact kick-off chips (safe/guarded)."""
    try:
        fixtures = ui_engine.fetch_fixtures()
        players, teams, events = ui_engine.fetch_bootstrap()
        if not fixtures or not teams:
            return None
        now = datetime.now(timezone.utc)
        rows = []
        for f in fixtures:
            if f.get("started") or f.get("finished"):
                continue
            ko = f.get("kickoff_time")
            if not ko:
                continue
            try:
                dt = datetime.fromisoformat(ko.replace("Z", "+00:00"))
            except Exception:
                continue
            if dt < now - timedelta(hours=3):
                continue
            th = (teams.get(f.get("team_h"), {}) or {}).get("short_name", "?")
            ta = (teams.get(f.get("team_a"), {}) or {}).get("short_name", "?")
            rows.append((dt, th, ta))
            if len(rows) >= 8:
                break
        if not rows:
            return None
        # group by date
        groups = []
        for dt, th, ta in rows:
            if groups and groups[-1][0].date() == dt.date():
                groups[-1][1].append((dt, th, ta))
            else:
                groups.append([dt, [(dt, th, ta)]])
        html = ["<div class='fx-strip'>"]
        for gdt, matches in groups:
            day = ("TODAY" if gdt.date() == now.date()
                   else gdt.strftime("%a %d %b").upper())
            html.append(f"<span class='fx-day'>{day}</span>")
            for dt, th, ta in matches:
                html.append(f"<span class='fx-match'>{th} "
                            f"<span class='t'>{dt.strftime('%H:%M')}</span> "
                            f"{ta}</span>")
        html.append("</div>")
        return "".join(html)
    except Exception:
        return None


def trajectory_bars(hist):
    """Last-8-GW points as glowing bars (The Chase, personal edition)."""
    rows = (hist or [])[-8:]
    if len(rows) < 2:
        return None
    mx = max(h.get("points", 0) for h in rows) or 1
    html = ["<div class='traj' style='margin-top:26px;'>"]
    for h in rows:
        pts = h.get("points", 0)
        hgt = max(6, int(pts / mx * 78))
        html.append(f"<div class='bar' style='height:{hgt}px;'>"
                    f"<span>{pts}</span><em>GW{h.get('event', '?')}</em>"
                    f"</div>")
    html.append("</div>")
    return "".join(html)


# ---------------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------------
PAGES = ["Weekly Dashboard", "Advanced Analytics", "Post-GW Review",
         "Squad Sync"]
MENU_LABELS = {"Weekly Dashboard": "🏠 Dashboard",
               "Advanced Analytics": "📊 Analytics",
               "Post-GW Review": "🧮 Review",
               "Squad Sync": "🗒️ Sync"}

defaults = {"team_id": "", "data": None, "horizon": "Next GW only",
            "defcon": False, "override_seed": None,
            "page": PAGES[0]}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v
# Stale-session guard: if the browser tab still holds values from an
# older app version, reset them instead of crashing the widgets below.
if st.session_state.page not in PAGES:
    st.session_state.page = PAGES[0]

HORIZONS = {"Next GW only": 1, "Next 3 GWs": 3, "Next 5 GWs": 5}
if st.session_state.horizon not in HORIZONS:
    st.session_state.horizon = "Next GW only"

# ---------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------
with st.sidebar:
    st.markdown("## ⚽ FPL TOOLZ")
    st.caption("V2.1.2 Command Center — the engine is silent, "
               "the answers are loud.")
    st.markdown("---")

    st.markdown("### 1 · Connect")
    with st.expander("❓ Where do I find my Team ID?"):
        st.markdown("""
        1. Go to [fantasy.premierleague.com](https://fantasy.premierleague.com/)
        2. Click **'Points'** (or your team name) in the top menu.
        3. Look at the URL. It looks like this:
           `fantasy.premierleague.com/entry/`**`1234567`**`/event/9`
        4. That number is your Team ID.

        *Tip: just paste the whole URL into the box below — the number
        is extracted for you automatically.*
        """)

    user_input = st.text_input("Team ID or URL",
                               value=st.session_state.team_id,
                               placeholder="e.g. 1234567 or your entry URL")
    if st.button("Connect & Run Engine", use_container_width=True,
                 type="primary"):
        parsed_id = None
        m = re.search(r"/entry/(\d+)", user_input or "")   # pasted URL
        if m:
            parsed_id = m.group(1)
        else:
            m = re.search(r"\d+", user_input or "")        # bare number
            if m:
                parsed_id = m.group()
        if parsed_id:
            st.session_state.team_id = parsed_id
            ui_engine.clear_cache()
            with st.spinner("Fetching live data and running the engine…"):
                st.session_state.data = ui_engine.run_engine(
                    int(parsed_id),
                    HORIZONS[st.session_state.horizon],
                    st.session_state.defcon,
                    override_seed=st.session_state.override_seed)
        elif user_input:
            st.error("Couldn't find a Team ID in that. Paste the number "
                     "or your FPL entry URL.")
        else:
            st.warning("Enter your Team ID (or paste your FPL URL) first.")

    st.markdown("---")
    st.markdown("### 2 · Intelligence Toggles")
    st.session_state.horizon = st.radio(
        "Optimise for", list(HORIZONS.keys()),
        index=list(HORIZONS.keys()).index(st.session_state.horizon))
    st.session_state.defcon = st.toggle(
        "Prioritise DefCon defenders", value=st.session_state.defcon)

    if st.session_state.data is not None and st.session_state.team_id:
        if st.button("Re-run with these settings", use_container_width=True):
            with st.spinner("Re-running the engine…"):
                st.session_state.data = ui_engine.run_engine(
                    int(st.session_state.team_id),
                    HORIZONS[st.session_state.horizon],
                    st.session_state.defcon,
                    override_seed=st.session_state.override_seed)

    st.markdown("---")
    st.markdown("### 3 · Navigate")
    # Apply any pending page redirect BEFORE the radio is instantiated —
    # Streamlit forbids writing st.session_state.page once the widget
    # with that key exists. The menu-bar buttons queue "_nav_go" instead.
    if "_nav_go" in st.session_state:
        st.session_state.page = st.session_state.pop("_nav_go")
    st.radio("Go to", PAGES, key="page")

# ---------------------------------------------------------------
# TOP MENU BAR (Game Bloc-style quick nav)
# ---------------------------------------------------------------
page = st.session_state.page
m1, m2, m3, m4 = st.columns(4)
for col, pg in zip((m1, m2, m3, m4), PAGES):
    with col:
        if st.button(MENU_LABELS[pg], use_container_width=True,
                     type="primary" if pg == page else "secondary"):
            # Don't write st.session_state.page here — the sidebar radio
            # owns that key. Queue the redirect instead; the sidebar
            # applies it on the next run, before the radio re-renders.
            st.session_state["_nav_go"] = pg
            st.rerun()

# ---------------------------------------------------------------
# WELCOME SCREEN — broadcast hero
# ---------------------------------------------------------------
data = st.session_state.data
if data is None:
    st.markdown("<div class='ticker'><span class='live-dot'></span>"
                "<span class='tk-brand'>FPL TOOLZ</span>"
                "<span class='tk-sep'>·</span><span>STANDBY</span>"
                "<span class='tk-fill'></span>"
                "<span class='tk-cta'>AWAITING TEAM ID</span></div>",
                unsafe_allow_html=True)
    st.markdown(
        "<span class='big-font' style='font-size:44px;'>"
        "THE ENGINE IS SILENT.</span><br>"
        "<span class='big-font' style='font-size:44px;color:#00ff87;'>"
        "THE ANSWERS ARE LOUD.</span>",
        unsafe_allow_html=True)
    st.caption("Captain · Transfers · Lineup — computed from the official "
               "FPL API every week, with the maths shown. No account, "
               "no password.")
    st.markdown(board([
        ("Gameweek", "LIVE", "green", "official FPL data"),
        ("Decisions", "3", "", "captain · transfer · lineup"),
        ("Setup", "1 ID", "", "paste & press Connect"),
        ("Cost", "FREE", "green", "public endpoints only"),
    ]), unsafe_allow_html=True)
    st.markdown(sec("HOW TO START"), unsafe_allow_html=True)
    s1, s2, s3 = st.columns(3)
    with s1:
        st.markdown("<div class='player-card'><div class='player-name'>"
                    "1 · PASTE YOUR TEAM ID</div><div class='player-sub'>"
                    "In the sidebar — the number (or whole URL) from your "
                    "FPL 'Points' page.</div></div>", unsafe_allow_html=True)
    with s2:
        st.markdown("<div class='player-card'><div class='player-name'>"
                    "2 · PRESS CONNECT</div><div class='player-sub'>"
                    "The engine pulls live prices, fixtures and form, then "
                    "builds your squad.</div></div>", unsafe_allow_html=True)
    with s3:
        st.markdown("<div class='player-card'><div class='player-name'>"
                    "3 · READ YOUR ANSWERS</div><div class='player-sub'>"
                    "Every verdict arrives with the numbers behind it — "
                    "never just a name.</div></div>", unsafe_allow_html=True)
    st.markdown(sec("WHAT YOU GET EVERY WEEK"), unsafe_allow_html=True)
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        st.markdown("🏆 **THE CAPTAIN** — 5-factor score with the full "
                    "breakdown, not just a name.")
    with f2:
        st.markdown("🔄 **THE TRANSFER** — ranked targets with horizon "
                    "gains, or a clear SAVE.")
    with f3:
        st.markdown("⚽ **THE LINEUP** — visual pitch, bench order and "
                    "auto-sub stress test.")
    with f4:
        st.markdown("🃏 **CHIPS & PLAN** — wildcard top buys, chip ledger "
                    "and the GW roadmap.")
    st.info("The app runs entirely on **public FPL endpoints** — nothing "
            "to install beyond pressing Connect.")
    st.stop()

if data.get("error"):
    st.error(data["error"])
    st.stop()

# ---------------------------------------------------------------
# TICKER + COUNTDOWN + STAT BOARD (header)
# ---------------------------------------------------------------
gw = data["gw"]
deadline_txt = "—"
if data.get("deadline_epoch"):
    secs = data["deadline_epoch"] - int(time.time())
    if secs > 0:
        d, r = divmod(secs, 86400)
        h, r = divmod(r, 3600)
        m, _ = divmod(r, 60)
        deadline_txt = (f"{d}d {h}h {m}m" if d else f"{h}h {m}m")
    else:
        deadline_txt = "PASSED — GW LIVE"

captain_name = (data.get("captain") or {}).get("name")
ticker_status = f"<b>GW{gw} LIVE</b>" if deadline_txt.startswith("PASSED") \
    else f"GW{gw} · DEADLINE <b>{deadline_txt}</b>"
ticker_cta = f"CAPTAIN → {captain_name}" if captain_name else "SET YOUR CAPTAIN"
st.markdown(
    f"<div class='ticker'><span class='live-dot'></span>"
    f"<span class='tk-brand'>FPL TOOLZ</span>"
    f"<span class='tk-sep'>·</span><span>{ticker_status}</span>"
    f"<span class='tk-sep'>·</span>"
    f"<span>SQUAD: {data['squad_source'].replace('_', ' ').upper()}</span>"
    f"<span class='tk-fill'></span>"
    f"<span class='tk-cta'>{ticker_cta}</span></div>",
    unsafe_allow_html=True)

st.markdown(f"<span class='big-font'>👋 {data['team_name']}</span>",
            unsafe_allow_html=True)
st.markdown(board([
    ("Gameweek", f"GW{gw}", "", deadline_txt),
    ("Projected XI", f"{data['xi_proj']:.0f}", "green",
     f"bench adds {data['bench_proj']:.0f}"),
    ("In The Bank", f"£{data['bank'] or 0:.1f}m", "",
     "available for transfers"),
    ("Free Transfers", f"{data['fts']}", "",
     "banked for this GW"),
    ("Squad Source", data['squad_source'].replace('_', ' ').upper(), "",
     "how the 15 were resolved"),
]), unsafe_allow_html=True)
countdown_bar(data.get("deadline_epoch"), gw)
if data.get("squad_source") in ("api_previous", "seed_stale"):
    st.caption(f"⚠️ Deadline for GW{gw} hasn't passed yet — the API only "
               f"publishes squads after it. Use **Squad Sync** to plan "
               "your intended 15.")

# ---------------------------------------------------------------
# URGENT BANNER
# ---------------------------------------------------------------
alerts = []
for a in data.get("price_alerts", []):
    if a.get("type") == "fall":
        pct = (f" ({a['pct']:+.1f}% projected)"
               if a.get("pct") is not None else "")
        alerts.append(f"💸 **{a['player']} is trending to FALL{pct}** — "
                      "decide before tonight's price change.")
flagged = [r for r in data["squad"] if r.get("reliability") == "INJURY FLAG"]
if len(flagged) >= 3:
    alerts.append(f"🚨 **{len(flagged)} players are flagged** "
                  f"({', '.join(r['name'] for r in flagged)}) — this is "
                  "chip-repair territory.")
if data.get("wc_active"):
    alerts.append("🃏 **WILDCARD IS ACTIVE** — unlimited transfers until "
                  "the deadline.")
for w in data.get("sub_warnings", []):
    alerts.append(f"⚠️ {w}")

if alerts:
    with st.container(border=True):
        for a in alerts:
            st.markdown(a)

# ===============================================================
# WEEKLY DASHBOARD
# ===============================================================
if page == "Weekly Dashboard":

    # NEXT UP — fixtures strip
    fx = fixtures_strip()
    if fx:
        st.markdown(sec("NEXT UP — KICK-OFFS (GMT)"), unsafe_allow_html=True)
        st.markdown(fx, unsafe_allow_html=True)

    cap, tr = st.columns([1, 1], gap="large")

    # ANSWER 1: CAPTAIN
    with cap:
        st.markdown(sec("THE CAPTAIN"), unsafe_allow_html=True)
        captain = data.get("captain")
        if captain:
            with st.container(border=True):
                vcls = ("green" if "STRONG" in captain["verdict"] else
                        "amber" if captain["verdict"] in ("SOLID", "LEAN")
                        else "red")
                st.markdown(
                    f"<span class='big-font'>{captain['name']}</span> "
                    f"{chip(captain['verdict'], vcls)}",
                    unsafe_allow_html=True)
                st.caption(f"{captain['team']} · vs {captain['fixture']} · "
                           f"£{captain['price']:.1f}m")
                st.metric("Captain score", f"{captain['score']:.1f} / 10",
                          f"proj {captain['proj']:.1f} pts "
                          f"(x2 = {captain['proj'] * 2:.1f})")
                f = captain.get("factors", {})
                why = [f"fixture {f.get('fixture', 0):.1f}/10" +
                       (f" (Smart FDR {f['smart_fdr']})"
                        if f.get("smart_fdr") is not None else ""),
                       f"form {f.get('form', 0):.1f}/10",
                       f"underlying {f.get('underlying', 0):.1f}/10",
                       f"role {f.get('role', 0):.0f}/10"]
                if f.get("ownership") is not None:
                    why.append(f"ownership {f['ownership']:.1f}/10")
                st.markdown("**Why:** " + " · ".join(why))
                if data.get("vice"):
                    st.info(f"**Vice:** {data['vice']['name']} "
                            f"({data['vice']['score']:.1f})")

    # ANSWER 2: TRANSFER (wildcard-aware)
    with tr:
        st.markdown(sec("THE TRANSFER"), unsafe_allow_html=True)
        t = data["transfer"]
        with st.container(border=True):
            vmap = {"TRANSFER": "green", "SAVE": "amber", "HIT": "red",
                    "WILDCARD ACTIVE": "blue"}
            st.markdown(chip(t["verdict"], vmap.get(t["verdict"], "amber")),
                        unsafe_allow_html=True)

            if t.get("sell") and t.get("buys") and not data.get("wc_active"):
                sell = t["sell"]
                labels = [f"{b['name']}  ·  gain {b['proj'] - sell['proj']:+.1f}"
                          for b in t["buys"]]
                idx = st.selectbox("Target (ranked — flip through them all)",
                                   range(len(t["buys"])),
                                   format_func=lambda i: labels[i], index=0)
                best = t["buys"][idx]

                st.markdown(f"<span class='big-font'>Sell {sell['name']} → "
                            f"Buy {best['name']}</span>",
                            unsafe_allow_html=True)
                gain = round(best["proj"] - sell["proj"], 1)
                st.metric("Horizon gain", f"{gain:+.1f} pts",
                          f"{best['price'] - sell['price']:+.1f}m price")

                cA, cB = st.columns(2)
                with cA:
                    st.markdown(f"**{sell['name']} run:** "
                                f"{squares(sell['run'])}",
                                unsafe_allow_html=True)
                    st.caption(f"proj {sell['proj']:.1f} pts/GW · "
                               f"£{sell['price']:.1f}m")
                with cB:
                    st.markdown(f"**{best['name']} run:** "
                                f"{squares(best['run'])}",
                                unsafe_allow_html=True)
                    st.caption(f"proj {best['proj']:.1f} pts/GW · "
                               f"£{best['price']:.1f}m · "
                               f"{best.get('sel', 0):.0f}% owned")

                vf = getattr(ui_engine, "VALUE_FLOOR", 3.0)
                se = getattr(ui_engine, "SWAP_EDGE", 4.0)
                st.markdown(
                    f"**Plain English:** the value floor is {vf:.1f} pts/GW — "
                    f"{sell['name']} sits at {sell['proj']:.1f}. A move must "
                    f"clear a {se:.0f}-pt edge to beat saving the transfer.")
                st.code(f"Transfer: {sell['name']} -> {best['name']} | "
                        f"Captain: {data['captain']['name']}",
                        language="text")

            elif data.get("wc_active") and t.get("buys"):
                if t.get("reason"):
                    st.info(t["reason"])
                st.markdown(sec("TOP MARKET BUYS RIGHT NOW"),
                            unsafe_allow_html=True)
                for b in t["buys"]:
                    team = b.get("team", "")
                    team_txt = f" ({team})" if team else ""
                    sel = (f" · {b['sel']:.0f}% owned"
                           if b.get("sel") is not None else "")
                    st.markdown(
                        f"**{b['name']}**{team_txt} — proj {b['proj']:.1f}/GW"
                        f" · £{b['price']:.1f}m{sel}")
                    st.markdown(squares(b.get("run")),
                                unsafe_allow_html=True)
                st.caption("Playing a wildcard: pick your buys on the FPL "
                           "site, then sync the new 15 in Squad Sync to "
                           "score the full squad.")
            else:
                st.markdown(f"**{t['verdict']}** — {t['reason']}")

    # ANSWER 3: LINEUP — VISUAL PITCH
    st.markdown(sec("THE LINEUP"), unsafe_allow_html=True)
    with st.container(border=True):
        st.metric("Projected team score", f"{data['xi_proj']:.0f} pts",
                  f"bench adds {data['bench_proj']:.0f}")
        rows_by_pos = {"GK": [], "DEF": [], "MID": [], "FWD": []}
        for r in data["xi"]:
            rows_by_pos[r["pos_name"]].append(r)
        labels = {"GK": "GOALKEEPER", "DEF": "DEFENDERS",
                  "MID": "MIDFIELDERS", "FWD": "FORWARDS"}
        for pos in ("FWD", "MID", "DEF", "GK"):
            if rows_by_pos[pos]:
                st.markdown(f"<div class='pitch-label'>{labels[pos]}</div>",
                            unsafe_allow_html=True)
                cols = st.columns(len(rows_by_pos[pos]))
                for i, r in enumerate(rows_by_pos[pos]):
                    with cols[i]:
                        st.markdown(player_card(r, captain_name),
                                    unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(sec("THE BENCH — AUTO-SUB READY"), unsafe_allow_html=True)
    with st.container(border=True):
        bench = data["bench"]
        cols = st.columns(max(4, len(bench)) if bench else 4)
        for i, r in enumerate(bench[:4]):
            with cols[i]:
                rcls = "green" if r.get("reliability") == "Reliable" else "red"
                st.markdown(f"{i + 1}. {chip(r['pos_name'], 'blue')} "
                            f"**{r['name']}** "
                            f"{chip(r.get('reliability', '?'), rcls)}",
                            unsafe_allow_html=True)
                bits = [f"proj {r['proj']:.1f}"]
                if r.get("start_rate") is not None:
                    bits.append(f"starts {r['start_rate'] * 100:.0f}%")
                if r.get("play_prob") is not None:
                    bits.append(f"{r['play_prob']:.0f}% fit")
                st.caption(" · ".join(bits))

    # TRAJECTORY — your last 8 GWs (The Chase, personal edition)
    traj = trajectory_bars(data.get("history"))
    if traj:
        st.markdown(sec("YOUR TRAJECTORY — LAST 8 GWS"), unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown(traj, unsafe_allow_html=True)

    # AUTO-SUB STRESS TEST
    with st.expander("🧪 WHAT IF A STARTER DOESN'T PLAY? — auto-sub stress test"):
        xi_labels = [f"{r['name']} ({r['pos_name']})" for r in data["xi"]]
        i = st.selectbox("Starter ruled out", range(len(data["xi"])),
                         format_func=lambda j: xi_labels[j])
        target = data["xi"][i]
        rest = [r for r in data["xi"] if r is not target]

        def _legal(rows):
            c = {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0}
            for r in rows:
                c[r["pos_name"]] += 1
            return (c["GK"] == 1 and 3 <= c["DEF"] <= 5 and
                    2 <= c["MID"] <= 5 and 1 <= c["FWD"] <= 3)

        sub_in, sub_order = None, None
        for order, cand in enumerate(data["bench"], 1):
            if _legal(rest + [cand]):
                sub_in, sub_order = cand, order
                break

        captain_out = bool(data.get("captain")) and \
            target["name"] == data["captain"]["name"]
        vice = data.get("vice")

        loss = target["proj"] * (2 if captain_out else 1)
        gain = sub_in["proj"] if sub_in else 0.0
        arm_bonus = vice["proj"] if (captain_out and vice) else 0.0
        new_proj = data["xi_proj"] - loss + gain + arm_bonus

        if captain_out and vice:
            st.info(f"**{target['name']} is your captain** — the armband "
                    f"passes to **{vice['name']}** (points ×2).")
        if sub_in:
            st.success(f"Auto-sub: **{sub_in['name']}** comes in "
                       f"(bench order #{sub_order}) for "
                       f"**{target['name']}**.")
        else:
            st.error("No legal auto-sub exists on your bench — you would "
                     "field only 10 men. Fix the bench order!")
        st.metric("Projected XI if it happens", f"{new_proj:.0f} pts",
                  f"{new_proj - data['xi_proj']:+.0f} vs current")

# ===============================================================
# ADVANCED ANALYTICS
# ===============================================================
elif page == "Advanced Analytics":
    tb1, tb2, tb3, tb4, tb5, tb6 = st.tabs(
        ["📈 5-GW HORIZON", "🌟 IDEAL XI", "🃏 CHIP STRATEGY",
         "🔀 FIXTURE SWINGS", "🤝 H2H", "💰 SQUAD VALUE"])

    with tb1:
        st.markdown("#### Every squad player over the horizon")
        for r in sorted(data["squad"], key=lambda x: x["avg_fdr"]):
            st.markdown(
                f"{chip(r['pos_name'], 'blue')} **{r['name']}** "
                f"({r['team']}) — run: {squares(r['run'])} · "
                f"avg FDR {r['avg_fdr']:.1f} · proj {r['proj']:.1f}/GW",
                unsafe_allow_html=True)

    with tb2:
        st.markdown("#### Global template XI (the dream team + your gap)")
        players, teams, events = ui_engine.fetch_bootstrap()
        fixtures = ui_engine.fetch_fixtures()
        form = ui_engine.team_form(gw, fixtures)
        ideal = ui_engine.ideal_xi(data, players=players, teams=teams,
                                   fixtures=fixtures, form=form,
                                   horizon=HORIZONS[st.session_state.horizon],
                                   use_defcon=st.session_state.defcon)
        options = ["(none)"] + [
            f"{r['name']} ({r['team']}, £{r['price']:.1f}m, proj {r['proj']:.1f})"
            for pos in ("GK", "DEF", "MID", "FWD")
            for r in ideal["xi"][pos] if not r["owned"]]
        swap = st.selectbox("Custom add — force a market player into "
                            "the template:", options, index=0)
        if swap != "(none)":
            name_part = swap.split(" (")[0]
            swap_id = None
            for pos in ("GK", "DEF", "MID", "FWD"):
                for r in ideal["xi"][pos]:
                    if r["name"] == name_part and not r["owned"] \
                            and r.get("id") is not None:
                        swap_id = r["id"]
                        break
                if swap_id:
                    break
            if swap_id is None:
                for pid, p in players.items():
                    if p["web_name"] == name_part:
                        swap_id = pid
                        break
            ideal = ui_engine.ideal_xi(data, players=players, teams=teams,
                                       fixtures=fixtures, form=form,
                                       horizon=HORIZONS[st.session_state.horizon],
                                       use_defcon=st.session_state.defcon,
                                       swap_in=swap_id)
        colA, colB = st.columns([3, 2])
        with colA:
            for pos in ("GK", "DEF", "MID", "FWD"):
                for r in ideal["xi"][pos]:
                    st.markdown(
                        f"{'✅' if r['owned'] else '⬜'} **{r['name']}** "
                        f"({r['team']}) — proj {r['proj']:.1f} · "
                        f"run {squares(r['run'])}", unsafe_allow_html=True)
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
                for gw_, c in sorted(played.items(),
                                     key=lambda kv: int(kv[0]))))
        else:
            st.markdown("**Played:** none yet (Set 1)")
        st.markdown("**Remaining (Set 1):** " +
                    (", ".join(ui_engine.CHIP_LABEL.get(c, c)
                               for c in chips["remaining_set1"])
                     if chips["remaining_set1"] else "—"))
        plan = chips.get("plan", {})
        if plan:
            st.markdown("**The plan**")
            for k, v in plan.items():
                st.markdown(f"- **{ui_engine.CHIP_LABEL.get(k, k)}**: {v}")

    with tb4:
        st.markdown("#### Fixture swing radar (next 6 GWs)")
        swings = data.get("fixture_swings") or []
        if swings:
            for s in swings:
                cls = ("green" if "GREEN" in s["type"] else
                       "red" if "RED" in s["type"] else "amber")
                st.markdown(f"{chip(s['type'], cls)} {s['message']}",
                            unsafe_allow_html=True)
        else:
            st.info("No sharp turns detected in the current window.")

    with tb5:
        st.markdown("#### Head-to-head history in play")
        rows = None
        if h2h_context_table is not None:
            try:
                rows = h2h_context_table(None)
            except Exception:
                rows = None
        if rows:
            for r in rows:
                derby = " · DERBY" if r.get("derby") else ""
                st.markdown(f"- **{r['matchup']}** — last 5: {r['wins']} · "
                            f"avg goals {r['avg_total_goals']}{derby}")
        else:
            st.info("No H2H data available yet. Add matchups to h2h.csv "
                    "(local build) to light this tab up.")

    with tb6:
        v = data.get("value")
        if v:
            st.metric("Squad cost (15)", f"£{v['squad_cost']:.1f}m")
            c1v, c2v = st.columns(2)
            with c1v:
                st.metric("Price drift this GW",
                          f"{v['this_gw_price_drift']:+.1f}m")
            with c2v:
                st.metric("Drift since GW1",
                          f"{v['season_price_drift']:+.1f}m")
            trend = v.get("history_trend") or []
            if trend:
                st.markdown("#### Team value, last 8 GWs")
                for t in trend:
                    pts = (f" · {t['points']} pts"
                           if t.get("points") is not None else "")
                    st.markdown(f"- GW{t['gw']}: value £{t['value']}m · "
                                f"bank £{t['bank']}m{pts}")

# ===============================================================
# POST-GW REVIEW
# ===============================================================
elif page == "Post-GW Review":
    st.markdown(sec("POST-GW REVIEW — CLOSE THE LOOP"), unsafe_allow_html=True)
    hist = data.get("history", []) or []
    if hist:
        st.markdown(board([
            ("Last GW", f"{hist[-1]['points']}", "green", "pts on the board"),
            ("Avg (last 5)",
             f"{sum(h['points'] for h in hist[-5:]) / len(hist[-5:]):.0f}",
             "", "pts per GW"),
            ("Best GW", f"{max(h['points'] for h in hist[-8:])}", "",
             "recent ceiling"),
        ]), unsafe_allow_html=True)
        traj = trajectory_bars(hist)
        if traj:
            with st.container(border=True):
                st.markdown(traj, unsafe_allow_html=True)
        st.markdown("#### Recent gameweeks")
        for h in reversed(hist[-8:]):
            rank = h.get("rank")
            rank_txt = f"{rank:,}" if isinstance(rank, int) else "—"
            st.markdown(f"- GW{h['event']}: **{h['points']} pts** · "
                        f"rank {rank_txt} · "
                        f"bench {h.get('points_on_bench', 0)}")
    proj = data.get("xi_proj")
    col1, col2 = st.columns(2)
    with col1:
        actual = st.number_input("Your actual GW score", min_value=0,
                                 max_value=250, step=1)
        gw_in = st.number_input("Gameweek", min_value=1, max_value=38,
                                value=max(1, gw - 1))
        if st.button("Log result", type="primary"):
            if st.session_state.team_id:
                if ui_engine.log_actual_result(
                        int(st.session_state.team_id), int(gw_in),
                        float(actual)):
                    st.success("Logged to ML training data!")
            else:
                st.warning("Connect your Team ID first.")
    with col2:
        if proj:
            st.metric("Last engine projection", f"{proj:.0f} pts")
            if actual:
                st.metric("Delta vs projection", f"{actual - proj:+.0f} pts")
    acc = data.get("ml")
    if acc:
        st.info(f"**Model accuracy:** {acc['weeks']} weeks · "
                f"mean error {acc['mean_abs_pct_error']}%")

# ===============================================================
# SQUAD SYNC (multiselect + captain/vice)
# ===============================================================
elif page == "Squad Sync":
    st.markdown(sec("SQUAD SYNC — THE PRE-DEADLINE WORKBENCH"),
                unsafe_allow_html=True)
    st.caption("The official API only publishes squads AFTER the deadline. "
               "Select your intended 15 here — saved to this browser "
               "session and analysed instantly (also written to disk on "
               "your local machine).")

    players, teams, events = ui_engine.fetch_bootstrap()

    # web_names are NOT unique in FPL (several Silvas, etc.) — handle it.
    name_to_ids = {}
    for pid, p in players.items():
        name_to_ids.setdefault(p["web_name"], []).append(pid)
    all_names = sorted(name_to_ids)

    def _resolve(name):
        ids = name_to_ids.get(name, [])
        if len(ids) == 1:
            return ids[0], False
        if len(ids) > 1:
            return max(ids, key=lambda x:
                       players[x].get("total_points", 0)), True
        return None, False

    current_names = [r["name"] for r in data["squad"]]
    safe_default = [n for n in current_names if n in name_to_ids]

    selected_names = st.multiselect("Select your 15 players",
                                    options=all_names,
                                    default=safe_default,
                                    max_selections=15)
    col1, col2 = st.columns(2)
    with col1:
        itb = st.number_input("Bank (£m)", min_value=0.0, max_value=20.0,
                              value=float(data["bank"] or 0.0), step=0.1)
    with col2:
        active_chip = st.selectbox("Active chip (if playing one)",
                                   ["none", "wildcard", "freehit", "3xc",
                                    "bboost"])

    # CAPTAIN / VICE — your call, not the engine's guess
    cap_name_sel, vice_name_sel = None, None
    if selected_names:
        eng_cap = (data.get("captain") or {}).get("name")
        default_cap_idx = (selected_names.index(eng_cap)
                           if eng_cap in selected_names else 0)
        c1, c2 = st.columns(2)
        with c1:
            cap_name_sel = st.selectbox("Captain", selected_names,
                                        index=default_cap_idx)
        with c2:
            vice_options = ([n for n in selected_names if n != cap_name_sel]
                            or selected_names)
            eng_vice = (data.get("vice") or {}).get("name")
            default_vice_idx = (vice_options.index(eng_vice)
                                if eng_vice in vice_options else 0)
            vice_name_sel = st.selectbox("Vice-Captain", vice_options,
                                         index=default_vice_idx)

    if st.button("Save squad & Re-run Engine", type="primary"):
        if len(selected_names) != 15:
            st.error(f"You have selected {len(selected_names)} players — "
                     "exactly 15 required.")
        else:
            ambiguous, new_ids = [], []
            for name in selected_names:
                pid, amb = _resolve(name)
                if pid is None:
                    continue
                new_ids.append(pid)
                if amb:
                    ambiguous.append(name)
            if len(new_ids) != 15:
                st.error("Some names could not be resolved. "
                         "Remove and re-add them.")
            else:
                captain_id, _ = (_resolve(cap_name_sel)
                                 if cap_name_sel
                                 else ((data.get("captain") or {}).get("id"),
                                       False))
                vice_id, _ = (_resolve(vice_name_sel)
                              if vice_name_sel else (None, False))
                st.session_state.override_seed = {
                    "source": "seed",
                    "note": "Pre-deadline workbench squad (Synced via UI).",
                    "picks": new_ids,
                    "bank": float(itb),
                    "captain_id": captain_id,
                    "vice_id": vice_id,
                    "active_chip": (None if active_chip == "none"
                                    else active_chip),
                }
                try:
                    ui_engine.save_seed(
                        gw, new_ids, itb=float(itb),
                        active_chip=(None if active_chip == "none"
                                     else active_chip))
                except Exception:
                    pass  # cloud disk is read-only — session state holds it
                msg = ("Squad saved! Re-running the engine…"
                       f" Captain: **{cap_name_sel}** · "
                       f"Vice: **{vice_name_sel}**.")
                if ambiguous:
                    msg += (" (Duplicate league names resolved to the "
                            "highest-scoring player.)")
                st.success(msg)
                ui_engine.clear_cache()
                st.rerun()

st.markdown("---")
st.caption("FPL TOOLZ V2.1.2 · BROADCAST SOFT · the engine is silent, "
           "the answers are loud")
