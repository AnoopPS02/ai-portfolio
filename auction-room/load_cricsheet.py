"""Load Cricsheet IPL JSON files into DuckDB.

Extract: read one JSON file per match.
Transform: flatten match -> innings -> overs -> balls into rows.
Load: rebuild the tables in data/auction_room.duckdb (safe to re-run).
"""
import json
from pathlib import Path

import duckdb
import pandas as pd

from auction_room.stats import create_views

RAW = Path("data/raw/ipl_json")
DB = "data/auction_room.duckdb"


def phase_of(over: int) -> str:
    """Cricsheet overs start at 0: 0-5 powerplay, 6-14 middle, 15-19 death."""
    if over <= 5:
        return "powerplay"
    if over <= 14:
        return "middle"
    return "death"


def parse_match(path: Path):
    m = json.loads(path.read_text(encoding="utf-8"))
    info = m["info"]
    match_id = path.stem                        # file name = match id
    ids = info["registry"]["people"]            # player name -> registry id
    team1, team2 = info["teams"]

    # ---------- one row for the matches table ----------
    match_row = {
        "match_id": match_id,
        "season": int(info["dates"][0][:4]),    # year of first date (safer than "2020/21")
        "date": info["dates"][0],
        "venue": info.get("venue"),
        "city": info.get("city"),
        "team1": team1,
        "team2": team2,
        "toss_winner": info["toss"]["winner"],
        "toss_decision": info["toss"]["decision"],
        "winner": info.get("outcome", {}).get("winner"),       # None for no result / tie
        "result": info.get("outcome", {}).get("result"),       # e.g. "no result", "tie"
        "stage": info.get("event", {}).get("stage"),           # e.g. "Final"; None in league games
    }

    # ---------- player rows: everyone who played in this match ----------
    player_rows = [
        {"player_id": ids[name], "name": name}
        for team_players in info["players"].values()
        for name in team_players
    ]

    # ---------- one row per ball bowled ----------
    delivery_rows = []
    for inn_no, inn in enumerate(m["innings"], start=1):
        batting_team = inn["team"]
        bowling_team = team2 if batting_team == team1 else team1
        is_super_over = inn.get("super_over", False)

        for over in inn["overs"]:
            for ball_seq, d in enumerate(over["deliveries"], start=1):
                extras = d.get("extras", {})          # e.g. {"wides": 1}
                wickets = d.get("wickets", [])        # usually empty
                runs = d["runs"]

                row = {
                    "match_id": match_id,
                    "innings_no": inn_no,
                    "batting_team": batting_team,
                    "bowling_team": bowling_team,
                    "over": over["over"],
                    "ball_seq": ball_seq,             # position in the over, incl. wides/no-balls
                    "phase": phase_of(over["over"]),
                    "batter_id": ids[d["batter"]],
                    "bowler_id": ids[d["bowler"]],
                    "non_striker_id": ids[d["non_striker"]],
                    "runs_batter": runs["batter"],
                    "runs_extras": runs["extras"],
                    "runs_total": runs["total"],
                    "extra_type": next(iter(extras), None),   # "wides", "noballs", "byes", "legbyes"...
                    "is_wicket": len(wickets) > 0,
                    "wicket_kind": wickets[0]["kind"] if wickets else None,
                    "player_out_id": ids[wickets[0]["player_out"]] if wickets else None,
                    "is_super_over": is_super_over,
                }

                # ---------- YOUR TURN: the scoring-rule flags ----------
                # Use the table from our chat:
                #   wide    -> not a legal ball, not faced by batter, all runs charged to bowler
                #   no-ball -> not a legal ball, IS faced by batter, charged to bowler
                #   bye/leg-bye -> legal ball, faced, NOT charged to bowler
                # TODO 1: row["is_legal_ball"]    = ...
                # TODO 2: row["is_ball_faced"]    = ...
                # TODO 3: row["runs_conceded"]    = ...   (hint: runs_total minus byes and legbyes)
                # TODO 4: row["is_four"] / row["is_six"] = ...  (skip fours where runs.get("non_boundary"))
                # TODO 5: row["is_bowler_wicket"] = ...   (not: run out, retired hurt, obstructing the field)

                row["is_legal_ball"] = "wides" not in extras and "noballs" not in extras

                row["is_ball_faced"] = "wides" not in extras

                row["runs_conceded"] = runs["total"] - extras.get("byes", 0) - extras.get("legbyes", 0)


                row["is_four"] = runs["batter"] == 4 and not runs.get("non_boundary", False)
                row["is_six"] = runs["batter"] == 6

                NON_BOWLER_KINDS = ("run out", "retired hurt", "retired out", "obstructing the field")
                row["is_bowler_wicket"] = row["is_wicket"] and row["wicket_kind"] not in NON_BOWLER_KINDS
                

                delivery_rows.append(row)

    return match_row, player_rows, delivery_rows


def main():
    files = sorted(RAW.glob("*.json"))
    print(f"Found {len(files)} match files")

    matches, players, deliveries = [], [], []
    for f in files:
        match_row, player_rows, delivery_rows = parse_match(f)
        matches.append(match_row)
        players.extend(player_rows)
        deliveries.extend(delivery_rows)

    matches_df = pd.DataFrame(matches)
    players_df = pd.DataFrame(players).drop_duplicates("player_id")
    deliveries_df = pd.DataFrame(deliveries)

    con = duckdb.connect(DB)
    # CREATE OR REPLACE = rebuild from scratch every run, so duplicates are impossible
    con.execute("CREATE OR REPLACE TABLE matches AS SELECT * FROM matches_df")
    con.execute("CREATE OR REPLACE TABLE players AS SELECT * FROM players_df")
    con.execute("CREATE OR REPLACE TABLE deliveries AS SELECT * FROM deliveries_df")

    create_views(con)
    print("views: batting_season, bowling_season")

    for t in ["matches", "players", "deliveries"]:
        print(t, con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], "rows")
    con.close()


if __name__ == "__main__":
    main()