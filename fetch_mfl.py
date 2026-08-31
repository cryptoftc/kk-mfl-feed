#!/usr/bin/env python3
"""
Pull Kelly Kapowski league data from the MyFantasyLeague export API and write
it to data/*.json for Claude's scheduled reports to read.

Runs in GitHub Actions. Credentials come from repo secrets, never from the repo.
"""
import json
import os
import pathlib
import sys
import time
import urllib.parse
import urllib.request

YEAR = os.environ.get("MFL_YEAR", "2026")
LEAGUE_ID = os.environ.get("MFL_LEAGUE_ID", "53478")
API_KEY = os.environ.get("MFL_API_KEY", "").strip()
WEEK = os.environ.get("MFL_WEEK", "").strip()

BASE = f"https://api.myfantasyleague.com/{YEAR}/export"
OUT = pathlib.Path("data")
OUT.mkdir(exist_ok=True)

# User-Agent matters: MFL asks that API clients identify themselves.
UA = "kk-mfl-feed/1.0 (personal league data sync)"

# name -> query params. L and APIKEY are added automatically where needed.
ENDPOINTS = {
    "league":        {"TYPE": "league"},
    "rosters":       {"TYPE": "rosters"},
    "free_agents":   {"TYPE": "freeAgents"},
    "injuries":      {"TYPE": "injuries", "_no_league": True},
    "standings":     {"TYPE": "leagueStandings"},
    "player_scores": {"TYPE": "playerScores", "COUNT": "300"},
    "nfl_schedule":  {"TYPE": "nflSchedule", "_no_league": True},
    "players":       {"TYPE": "players", "DETAILS": "1"},
    "transactions":  {"TYPE": "transactions"},
    "future_picks":  {"TYPE": "futureDraftPicks"},
}


def fetch(name, params):
    q = {k: v for k, v in params.items() if not k.startswith("_")}
    if not params.get("_no_league"):
        q["L"] = LEAGUE_ID
    if API_KEY:
        q["APIKEY"] = API_KEY
    if WEEK:
        q.setdefault("W", WEEK)
    q["JSON"] = "1"

    url = f"{BASE}?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8", errors="replace")

    data = json.loads(raw)

    # MFL reports errors inside a 200 response, so check the body.
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"MFL returned an error: {data['error']}")

    path = OUT / f"{name}.json"
    path.write_text(json.dumps(data, indent=1, sort_keys=True))
    return path.stat().st_size


def main():
    if not API_KEY:
        print("WARNING: MFL_API_KEY is empty. Private endpoints will likely fail.", file=sys.stderr)

    results, failures = {}, {}
    for name, params in ENDPOINTS.items():
        try:
            size = fetch(name, params)
            results[name] = size
            print(f"ok    {name:14s} {size:>9,} bytes")
        except Exception as e:
            failures[name] = str(e)
            print(f"FAIL  {name:14s} {e}", file=sys.stderr)
        time.sleep(2)  # be polite; MFL rate-limits aggressive clients

    manifest = {
        "fetched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "year": YEAR,
        "league_id": LEAGUE_ID,
        "week_requested": WEEK or "current",
        "ok": results,
        "failed": failures,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"\n{len(results)} ok, {len(failures)} failed")

    # Don't fail the run on partial success - a stale endpoint shouldn't block the rest.
    if not results:
        sys.exit(1)


if __name__ == "__main__":
    main()
