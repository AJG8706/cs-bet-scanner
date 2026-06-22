#!/usr/bin/env python3
"""
Crypto Sensei ORDER — CS Bet Scanner
Scans The Odds API for football matches qualifying under Methods 1, 2, and 3.
Writes results/latest.json for the Cowork skill to read and report.

Setup:
    export ODDS_API_KEY=your_key_here
    pip install requests
    python scanner.py

Free tier: 500 requests/month (~180 scans/month at 6 scans/day leaves headroom).
"""

import os
import json
import requests
from datetime import datetime, timezone, timedelta
from statistics import median

# ── CONFIG ────────────────────────────────────────────────────────────────

API_KEY = os.environ.get("ODDS_API_KEY", "")
BASE_URL = "https://api.the-odds-api.com/v4"

# ── METHOD 2 — SAFER (Primary) ────────────────────────────────────────────
# Over 1.5 Goals: both criteria must be met simultaneously.
M2_OVER_MIN = 1.25
M2_OVER_MAX = 1.28
M2_UNDER_MIN = 3.00

# Near-miss: may qualify on user's bookmaker given the ±0.01 tolerance rule
M2_NEAR_OVER_MAX = 1.32    # Over 1.5 up to 1.32 is a near miss
M2_NEAR_UNDER_MIN = 2.80   # Under 1.5 as low as 2.80 is a near miss

# ── METHOD 1 — STANDARD (Secondary) ──────────────────────────────────────
# Home Win: home AND away must fit the SAME bracket row.
# Format: (home_min, home_max, away_min)
M1_BRACKETS = [
    (1.10, 1.15, 9.90),
    (1.25, 1.30, 8.20),
    (1.32, 1.37, 7.70),
    (1.42, 1.50, 6.70),
]

# ── METHOD 3 — EXPERIMENTAL ───────────────────────────────────────────────
# Single match, home odds ≥ 8.00 → 3 simultaneous tickets
# (Home Win / Draw / Away Win by exactly 1 goal)
M3_HOME_MIN = 8.00

# ── TICKET TARGETS ────────────────────────────────────────────────────────
TICKET_ODDS_MIN = 2.00
TICKET_ODDS_MAX = 2.30
MIN_PICKS = 2
MAX_PICKS = 3

# ── COMPETITION FILTER ────────────────────────────────────────────────────
# Skip any sport_key containing these substrings (domestic/knockout cups only)
CUP_KEYWORDS = [
    "fa_cup", "copa", "coupe", "carabao", "league_cup",
    "shield", "trophy", "supercup", "efl_trophy", "womens",
    "w_league", "women",
]
# soccer_fifa_world_cup is intentionally NOT in the blacklist (group stage allowed)


# ─────────────────────────────────────────────────────────────────────────
# API helpers
# ─────────────────────────────────────────────────────────────────────────

def _log_quota(response):
    used = response.headers.get("x-requests-used", "?")
    remaining = response.headers.get("x-requests-remaining", "?")
    return f"(used {used}, remaining {remaining})"


def get_active_soccer_sports():
    """Return list of active soccer sport_keys, cups excluded."""
    url = f"{BASE_URL}/sports"
    try:
        resp = requests.get(url, params={"apiKey": API_KEY, "all": "false"}, timeout=15)
        if resp.status_code != 200:
            print(f"[WARN] /sports returned {resp.status_code} — using fallback list")
            return _fallback_leagues()

        keys = []
        for sport in resp.json():
            key = sport.get("key", "")
            if not key.startswith("soccer_"):
                continue
            if any(kw in key for kw in CUP_KEYWORDS):
                print(f"  [SKIP cup] {key}")
                continue
            keys.append(key)

        print(f"Active soccer competitions: {len(keys)}")
        return keys

    except Exception as e:
        print(f"[WARN] Sports list error: {e}")
        return _fallback_leagues()


def _fallback_leagues():
    """Hard-coded fallback if the /sports endpoint fails."""
    return [
        "soccer_epl",
        "soccer_spain_la_liga",
        "soccer_italy_serie_a",
        "soccer_germany_bundesliga",
        "soccer_france_ligue_one",
        "soccer_uefa_champs_league",
        "soccer_fifa_world_cup",
        "soccer_usa_mls",
        "soccer_brazil_campeonato",
        "soccer_mexico_ligamx",
        "soccer_turkey_super_league",
        "soccer_netherlands_eredivisie",
        "soccer_portugal_primeira_liga",
    ]


def get_odds_for_sport(sport_key):
    """Fetch upcoming match odds (h2h + totals) for a sport."""
    url = f"{BASE_URL}/sports/{sport_key}/odds"
    params = {
        "apiKey": API_KEY,
        "regions": "eu,uk",        # European decimal odds
        "markets": "h2h,totals",
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            quota = _log_quota(resp)
            print(f"  {sport_key}: {len(resp.json())} matches {quota}")
            return resp.json()
        elif resp.status_code == 422:
            return []   # Sport valid but no upcoming matches
        else:
            print(f"  {sport_key}: HTTP {resp.status_code}")
            return []
    except Exception as e:
        print(f"  {sport_key}: error — {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────
# Odds extraction helpers
# ─────────────────────────────────────────────────────────────────────────

def extract_totals(match, target_line=1.5):
    """Return (over_prices, under_prices) lists at the target line."""
    overs, unders = [], []
    for bk in match.get("bookmakers", []):
        for mkt in bk.get("markets", []):
            if mkt["key"] != "totals":
                continue
            for outcome in mkt.get("outcomes", []):
                if abs(outcome.get("point", 0) - target_line) > 0.01:
                    continue
                if outcome["name"] == "Over":
                    overs.append(outcome["price"])
                elif outcome["name"] == "Under":
                    unders.append(outcome["price"])
    return overs, unders


def extract_h2h(match):
    """Return (home_prices, draw_prices, away_prices) lists."""
    home, draw, away = [], [], []
    ht = match.get("home_team", "")
    at = match.get("away_team", "")
    for bk in match.get("bookmakers", []):
        for mkt in bk.get("markets", []):
            if mkt["key"] != "h2h":
                continue
            for outcome in mkt.get("outcomes", []):
                n = outcome["name"]
                p = outcome["price"]
                if n == ht:
                    home.append(p)
                elif n == at:
                    away.append(p)
                elif n == "Draw":
                    draw.append(p)
    return home, draw, away


def med(prices):
    return round(median(prices), 3) if prices else None


# ─────────────────────────────────────────────────────────────────────────
# Method checkers
# ─────────────────────────────────────────────────────────────────────────

def check_method2(match):
    """
    Method 2 — SAFER: Over 1.5 Goals
    Uses median odds across all bookmakers (±0.01 tolerance between books is fine).
    Returns a dict with qualify/near_miss flags, or None if no 1.5 line available.
    """
    overs, unders = extract_totals(match, 1.5)
    if not overs or not unders:
        return None

    over_med = med(overs)
    under_med = med(unders)

    qualifies = M2_OVER_MIN <= over_med <= M2_OVER_MAX and under_med >= M2_UNDER_MIN
    near_miss = (
        not qualifies
        and M2_OVER_MIN <= over_med <= M2_NEAR_OVER_MAX
        and under_med >= M2_NEAR_UNDER_MIN
    )

    return {
        "over_1_5": over_med,
        "under_1_5": under_med,
        "bookmaker_count": len(overs),
        "qualifies": qualifies,
        "near_miss": near_miss,
    }


def check_method1(match):
    """
    Method 1 — Standard: Home Win
    Both home AND away median odds must match the same bracket row.
    Returns a dict with qualify flag, or None if no h2h odds available.
    """
    home_p, draw_p, away_p = extract_h2h(match)
    if not home_p or not away_p:
        return None

    home_med = med(home_p)
    away_med = med(away_p)
    draw_med = med(draw_p)

    matched_bracket = None
    for h_min, h_max, a_min in M1_BRACKETS:
        if h_min <= home_med <= h_max and away_med >= a_min:
            matched_bracket = f"{h_min}–{h_max}"
            break

    return {
        "home_odds": home_med,
        "draw_odds": draw_med,
        "away_odds": away_med,
        "bracket": matched_bracket,
        "qualifies": matched_bracket is not None,
    }


def check_method3(match):
    """
    Method 3 — Experimental: home odds ≥ 8.00
    Reports as a 3-ticket opportunity. NOT included in the standard ticket.
    User must verify Away-by-1-goal margin odds (3.00+) on their bookmaker.
    """
    home_p, draw_p, away_p = extract_h2h(match)
    if not home_p:
        return None

    home_med = med(home_p)
    if home_med < M3_HOME_MIN:
        return None

    return {
        "home_odds": home_med,
        "draw_odds": med(draw_p),
        "away_odds": med(away_p),
        "qualifies": True,
        "action": (
            "Place 3 simultaneous tickets: "
            "(1) Home Win, (2) Draw, (3) Away Win by exactly 1 goal. "
            "Verify Away-by-1-goal margin odds at 3.00+ on your bookmaker before placing."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────
# Ticket builder
# ─────────────────────────────────────────────────────────────────────────

def build_ticket(qualifiers_m2, qualifiers_m1):
    """
    Construct the best available ticket:
    - Prefer 2–3 Method 2 (Over 1.5) picks
    - Backfill with Method 1 (Home Win) if fewer than 2 M2 qualifiers
    - Combined odds must reach 2.00–2.30
    - Never force a ticket below 2.00
    """
    picks = []

    # Sort M2 by over odds ascending (tightest qualification = most reliable)
    for match in sorted(qualifiers_m2, key=lambda x: x["m2"]["over_1_5"]):
        if len(picks) >= MAX_PICKS:
            break
        picks.append({
            "match": match["match_name"],
            "sport": match["sport"],
            "method": 2,
            "bet": "Over 1.5 Goals",
            "odds": match["m2"]["over_1_5"],
            "kickoff": match["commence_time"],
        })

    # Backfill with Method 1 if needed
    if len(picks) < MIN_PICKS:
        for match in qualifiers_m1:
            if len(picks) >= MAX_PICKS:
                break
            picks.append({
                "match": match["match_name"],
                "sport": match["sport"],
                "method": 1,
                "bet": "Home Win",
                "odds": match["m1"]["home_odds"],
                "kickoff": match["commence_time"],
            })

    if not picks:
        return None

    # Calculate combined odds
    combined = 1.0
    for p in picks:
        combined *= p["odds"]
    combined = round(combined, 3)

    in_range = TICKET_ODDS_MIN <= combined <= TICKET_ODDS_MAX

    note = None
    if not in_range:
        if combined < TICKET_ODDS_MIN:
            note = (
                f"Combined odds {combined} below minimum {TICKET_ODDS_MIN}. "
                "Do not place — wait for more qualifying matches."
            )
        else:
            note = (
                f"Combined odds {combined} above target range. "
                "Consider removing the weakest pick."
            )

    return {
        "picks": picks,
        "combined_odds": combined,
        "in_range": in_range,
        "note": note,
    }


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────

def main():
    if not API_KEY:
        print("ERROR: ODDS_API_KEY environment variable is not set.")
        raise SystemExit(1)

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=24)

    print(f"\n{'='*60}")
    print(f"CS BET SCANNER  |  {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")
    print(f"Window: next 24 hours  ({now.strftime('%H:%M')} – {cutoff.strftime('%H:%M UTC')})")

    # ── 1. Get active soccer sports ───────────────────────────────────────
    print("\nFetching active soccer competitions...")
    sport_keys = get_active_soccer_sports()

    # ── 2. Scan each sport ────────────────────────────────────────────────
    q_m2, q_m1, q_m3, near_misses = [], [], [], []
    matches_checked = 0

    print("\nScanning odds...")
    for sport_key in sport_keys:
        matches = get_odds_for_sport(sport_key)

        for match in matches:
            # Parse kickoff
            try:
                commence = datetime.fromisoformat(
                    match["commence_time"].replace("Z", "+00:00")
                )
            except Exception:
                continue

            # Only next 24 hours, not already started
            if commence <= now or commence > cutoff:
                continue

            matches_checked += 1
            match_name = f"{match['home_team']} vs {match['away_team']}"
            base = {
                "match_name": match_name,
                "sport": sport_key,
                "commence_time": match["commence_time"],
                "match_id": match.get("id", ""),
            }

            m2 = check_method2(match)
            m1 = check_method1(match)
            m3 = check_method3(match)

            if m2:
                if m2["qualifies"]:
                    q_m2.append({**base, "m2": m2})
                elif m2["near_miss"]:
                    near_misses.append({**base, "method": 2, "data": m2})

            if m1 and m1["qualifies"]:
                q_m1.append({**base, "m1": m1})

            if m3:
                q_m3.append({**base, "m3": m3})

    # ── 3. Build ticket ───────────────────────────────────────────────────
    ticket = build_ticket(q_m2, q_m1)

    # ── 4. Write results ──────────────────────────────────────────────────
    results = {
        "scan_time": now.isoformat(),
        "scan_window_hours": 24,
        "matches_checked": matches_checked,
        "method2_qualifiers": q_m2,
        "method1_qualifiers": q_m1,
        "method3_opportunities": q_m3,
        "near_misses": near_misses,
        "recommended_ticket": ticket,
        "bankroll_reference": {
            "sequence": [1, 3, 5, 10, 20, 40, 80],
            "note": "Multiply base stake by this value after each consecutive loss. Return to 1x after any win.",
            "recommended_bankroll": "160x base stake minimum",
        },
    }

    os.makedirs("results", exist_ok=True)
    with open("results/latest.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    # ── 5. Summary ────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("SCAN COMPLETE")
    print(f"  Matches checked  : {matches_checked}")
    print(f"  Method 2 (M2)    : {len(q_m2)} qualifier(s)")
    print(f"  Method 1 (M1)    : {len(q_m1)} qualifier(s)")
    print(f"  Method 3 (M3)    : {len(q_m3)} opportunity(ies)")
    print(f"  Near misses      : {len(near_misses)}")

    if ticket and ticket["in_range"]:
        print(f"\n  ✅ TICKET READY — {len(ticket['picks'])} picks, combined odds {ticket['combined_odds']}")
        for p in ticket["picks"]:
            print(f"     → {p['match']}  |  {p['bet']}  @  {p['odds']}")
    elif ticket:
        print(f"\n  ⚠️  NO VALID TICKET — {ticket.get('note', 'combined odds out of range')}")
    else:
        print("\n  ❌  No qualifiers — check back at next scan")

    print(f"\n  Results → results/latest.json")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
