# h2h_adjuster.py — Head-to-Head History Brain (V2)
# ============================================================
# Applies historical matchup modifiers (last 5 H2H games) to Smart FDR.
# Manual h2h.csv — update once per season or after every 5 H2H meetings.
#
# Modifier rules (SPEC V2 §4.6, frozen):
#   Win dominance   : opponent-of-record lost >= 3 of last 5 meetings
#                     -> their attackers get easier fixtures (-0.5 FDR)
#   High-scoring H2H: avg total goals >= 3.0  -> attackers -0.5 FDR
#   Low-scoring H2H : avg total goals <  1.5  -> defenders -0.5 FDR
#   Clean sheets    : team kept >= 2 CS in last 5   -> their defenders -0.5
#   Derby           : all players +0.5 FDR (volatility penalty)
#   Total clamp     : -1.5 .. +1.5
# Missing data => 0.0 (graceful).
# ============================================================

import csv
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
H2H_FILE = os.path.join(_HERE, "h2h.csv")

_CACHE = {"loaded": False, "rows": []}

# Fixtures commonly tagged as derbies (extend in h2h.csv via derby=TRUE)
DERBY_PAIRS = {
    frozenset(x) for x in [
        ("ARS", "TOT"), ("ARS", "CHE"), ("CHE", "TOT"),          # London
        ("LIV", "EVE"), ("MUN", "LIV"), ("MUN", "CITY"),         # NW
        ("BHA", "CRY"), ("NEW", "SUN"), ("AVL", "WOL"),
        ("FOR", "NFO"), ("LEE", "MUN"), ("SHU", "LEE"),
    ]
}


def _load():
    if _CACHE["loaded"]:
        return _CACHE["rows"]
    _CACHE["loaded"] = True
    rows = []
    try:
        with open(H2H_FILE, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                rows.append(row)
    except Exception:
        rows = []
    _CACHE["rows"] = rows
    return rows


def _num(row, key):
    try:
        return float(row.get(key) or 0)
    except Exception:
        return 0.0


def h2h_modifier_for(team_h, team_a, position):
    """Return (fdr_delta in -1.5..1.5, reason_string) for a player of
    `position` (1 GK, 2 DEF, 3 MID, 4 FWD) in fixture team_h vs team_a.
    NOTE: team ids may be 0 when the caller has no fixture context."""
    if not team_h or not team_a:
        return 0.0, ""
    rows = _load()
    best = None
    for row in rows:
        pair = {row.get("team_h", "").strip().upper(),
                row.get("team_a", "").strip().upper()}
        if {str(team_h), str(team_a)} & pair and len(pair) == 2:
            # match on team short names if ids were passed as names
            best = row
            break
    if best is None:
        return 0.0, ""

    is_defender = position in (1, 2)
    delta = 0.0
    reasons = []

    wins_h = _num(best, "last_5_h2h_wins_h")
    wins_a = _num(best, "last_5_h2h_wins_a")
    if max(wins_h, wins_a) >= 3:
        # the dominant side attacks a beaten opponent: easier for attackers
        if not is_defender:
            delta -= 0.5
            reasons.append("dominant H2H side (easier for attackers)")

    avg_total = _num(best, "avg_total_goals")
    if avg_total >= 3.0 and not is_defender:
        delta -= 0.5
        reasons.append(f"high-scoring H2H ({avg_total:.1f} goals/game)")
    if avg_total < 1.5 and avg_total > 0 and is_defender:
        delta -= 0.5
        reasons.append(f"low-scoring H2H ({avg_total:.1f} goals/game)")

    cs_h = _num(best, "clean_sheets_h")
    cs_a = _num(best, "clean_sheets_a")
    if is_defender and max(cs_h, cs_a) >= 2:
        delta -= 0.5
        reasons.append("clean-sheet dominance in H2H")

    derby = (best.get("derby", "").strip().upper() in ("TRUE", "1", "YES"))
    if derby:
        delta += 0.5
        reasons.append("derby volatility penalty")

    delta = max(-1.5, min(1.5, delta))
    return round(delta, 2), "; ".join(reasons)


def h2h_context_table(teams_by_short):
    """Rows for the UI's H2H tab: which upcoming fixtures have H2H data."""
    out = []
    for row in _load():
        out.append({
            "matchup": f"{row.get('team_h','')} vs {row.get('team_a','')}",
            "wins": f"{row.get('last_5_h2h_wins_h','?')}-{row.get('last_5_h2h_draws','?')}-{row.get('last_5_h2h_wins_a','?')}",
            "avg_total_goals": row.get("avg_total_goals", ""),
            "clean_sheets": f"{row.get('clean_sheets_h','?')}/{row.get('clean_sheets_a','?')}",
            "derby": row.get("derby", "").strip().upper() in ("TRUE", "1", "YES"),
        })
    return out
