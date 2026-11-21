"""Load the IPL 2027 retention lists into DuckDB and link each player to Cricsheet.

Tables created (all rebuilt on every run, so re-running is safe):
  purse     team, purse_left_cr
  retained  team, player, traded_in, overseas, player_id (NULL = no Cricsheet match)

Run:  uv run python load_auction.py
"""
import duckdb
import pandas as pd

from auction_room.tools import _find

DB = "data/auction_room.duckdb"
RETAINED_CSV = "data/raw/auction/retained_2027.csv"
PURSE_CSV = "data/raw/auction/purse_2027.csv"

# Names that _find can't resolve on its own: news spelling -> exact Cricsheet name.
# Start empty. Fill it from the "AMBIGUOUS" and "UNMATCHED" lists this script prints.
# Check the Cricsheet spelling with:  SELECT name FROM players WHERE name ILIKE '%siraj%'
MANUAL = {
    "Rohit Sharma": "RG Sharma",
    "Cameron Green": "CJ Green",
    "Mohd. Arshad Khan": "Arshad Khan",
    "Finn Allen": "FH Allen",
    "Rinku Singh": "RK Singh",
    "Saurabh Dubey": "SR Dubey",
    "Shubham Dubey": "SB Dubey",
    "Mukul Choudhary":"MD Choudhary",
    "Prabhsimran Singh": "P Simran Singh",
    "Vyshak Vijaykumar": "Vijaykumar Vyshak",
    "Jitesh Sharma": "JM Sharma",
    "Rasikh Dar": "Rasikh Salam",
    "Varun Chakaravarthy": "CV Varun",
    "Vaibhav Sooryavanshi": "V Suryavanshi",
    "Smaran Ravichandran": "R Smaran",
    "Prasidh Krishna": "M Prasidh Krishna",
    "Sai Sudharsan": "B Sai Sudharsan",
    "Dasun Shanaka": "MD Shanaka"
}


def resolve(con, name: str):
    """Return (player_id, status) where status is 'matched', 'unmatched' or 'ambiguous'."""
    if name in MANUAL:
        row = con.execute("SELECT player_id FROM players WHERE name = ?", [MANUAL[name]]).fetchone()
        return (row[0], "matched") if row else (None, "unmatched")   # a typo in MANUAL shows up here

    matches = _find(con, name)
    # TODO 2: return the right (player_id, status) for 0, 1 and 2+ matches.
    #   Remember what _find returns: a list of (player_id, name) tuples.
    #   Ambiguous gets no id: a wrong link is worse than no link.

    if not matches:
        return (None, "unmatched")
    elif len(matches) > 1:
        return (None, "ambiguous")
    else:
        if matches[0][1][0] == name[0]:
            return (matches[0][0], "matched")
        else:
            return (None, "unmatched")


def main():
    con = duckdb.connect(DB)

    # TODO 1: rebuild both tables straight from the CSVs.
    #   DuckDB reads CSVs itself:  SELECT * FROM read_csv('path', header = true)
    #   Wrap that in the same CREATE OR REPLACE TABLE ... AS pattern your Cricsheet loader uses.
    #   (The paths are our own constants, so an f-string is fine here.)

    con.execute(f"CREATE OR REPLACE TABLE retained AS SELECT * FROM read_csv('{RETAINED_CSV}', header = true)")
    con.execute(f"CREATE OR REPLACE TABLE purse AS SELECT * FROM read_csv('{PURSE_CSV}', header = true)")

    retained_df = con.execute("SELECT * FROM retained").df()

    ids, problems = [], {"unmatched": [], "ambiguous": [], "check": []}
    for row in retained_df.itertuples():
        player_id, status = resolve(con, row.player)
        ids.append(player_id)
        if status != "matched":
            problems[status].append(f"{row.team}: {row.player}")

    retained_df["player_id"] = ids
    con.execute("CREATE OR REPLACE TABLE retained AS SELECT * FROM retained_df")
    # ^ DuckDB reads the pandas DataFrame by its variable name. It must NOT be called `retained`:
    #   a real table with the same name wins, and the new column would silently disappear.

    print(f"Linked {len(retained_df) - sum(len(v) for v in problems.values())} of {len(retained_df)} players")
    for status, names in problems.items():
        print(f"\n{status.upper()} ({len(names)}):")
        for n in names:
            print("  ", n)

    # TODO 3: sanity checks, printed with .df() or .show():
    #   a. players and overseas players per team (no team over 25 players or 8 overseas)
    #   b. total purse = 297.95 (ROUND it: floating point gives 297.94999...)
    #   c. every link, news name next to Cricsheet name (JOIN players ON player_id), and eyeball it.
    #      A wrong single match is the dangerous case: it looks "matched" but points at another player.
    con.sql("SELECT team, COUNT(*) as players, COUNT(*) FILTER (WHERE overseas is true) AS overseas FROM retained GROUP BY team ORDER BY team").show()
    con.sql("SELECT ROUND(SUM(purse_left_cr),2) FROM purse").show()
    con.sql("SELECT r.player as News_name, p.name as Cricsheet_name, r.team as Team FROM retained as r JOIN players as p ON p.player_id = r.player_id ORDER BY r.team").show(max_rows=100)
    con.close()


if __name__ == "__main__":
    main()