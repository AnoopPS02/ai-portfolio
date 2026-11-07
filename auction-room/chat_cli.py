"""Auction Room CLI v0: a streaming chat grounded in real IPL stats.

Pick a player, then ask questions. The model only sees that player's
season stats from DuckDB, so answers come from data, not memory.
"""
import duckdb

from auction_room.llm import chat

DB = "data/auction_room.duckdb"


def find_player(con, name: str):
    """Return (player_id, player_name) for a name search, or None."""
    # TODO 1: query the players table for names matching `name`
    #   - case-insensitive partial match (you've used ILIKE before)
    #   - pass `name` as a parameter, never by pasting it into the SQL string:
    #       con.execute("... WHERE name ILIKE ?", [f"%{name}%"]).fetchall()
    #   - if 0 rows: return None
    #   - if several rows: print them numbered and let the user pick one with input()
    #   - return (player_id, player_name)
    ...
    rows = con.execute("SELECT * FROM players WHERE name ILIKE ?", [f"%{name}%"]).fetchall()

    if len(rows) == 0:
        return None
    else:
        if len(rows) > 1:
            print(rows)
            userInput = input("Enter the player id searching for: ")

            for id, name in rows:
                if id == userInput:
                    return id, name
        else:
            for id, name in rows:
                return id, name


def stat_card(con, player_id: str) -> str:
    """The player's batting and bowling seasons as plain text for the prompt."""
    batting = con.execute(
        "SELECT * EXCLUDE (player_id) FROM batting_season WHERE player_id = ? ORDER BY season",
        [player_id],
    ).df()
    bowling = con.execute(
        "SELECT * EXCLUDE (player_id) FROM bowling_season WHERE player_id = ? ORDER BY season",
        [player_id],
    ).df()

    parts = []
    if not batting.empty:
        parts.append("BATTING BY SEASON\n" + batting.to_string(index=False))
    if not bowling.empty:
        parts.append("BOWLING: no bowling recorded in the IPL.")
        #parts.append("BOWLING BY SEASON\n" + bowling.to_string(index=False))
    return "\n\n".join(parts) or "No stats found."


# TODO 2: write the system prompt. Tell the model:
#   - who it is (an IPL analyst helping before the auction)
#   - to answer ONLY from the stats provided
#   - to quote the season and the number when it uses a stat
#   - to say plainly when the stats don't answer the question (no guessing)
#   - to keep answers short
#SYSTEM_PROMPT = """
#    The stats are SEASON TOTALS only. You do NOT have individual match scores,
#opponents, or venues. If a question needs those, say: "I only have season
#totals, so I can't answer that yet." Never present an average or strike rate
#as a score.
#""
SYSTEM_PROMPT = """
You are an IPL analyst helping before the auction.

WHAT YOU HAVE: season totals for one player. For batting: runs, balls faced,
strike rate, fours, sixes, dismissals, average, powerplay balls per boundary.
For bowling: balls, runs conceded, wickets, economy, middle/death-over figures.
Answer any question about these directly, quoting the season and the number.

WHAT YOU DON'T HAVE: individual match scores, opponents, venues, salaries.
Only for those, reply: "I only have season totals, so I can't answer that yet."

- If the question needs match-level detail (single-match scores, opponents, venues):
  "I only have season totals, so I can't answer that yet."
- If the season or stat isn't in this player's data:
  say it plainly, e.g. "There's no 2026 record for him in my data."
- If the stats say no bowling recorded: "He hasn't bowled in the IPL."

Examples:
Q: How many runs did he score in 2018?
A: In 2018 he scored 455 runs at a strike rate of 150.7.
Q: What was his top score against Mumbai?
A: I only have season totals, so I can't answer that yet.

Keep answers short. Never present an average or strike rate as a score.
"""


def main():
    con = duckdb.connect(DB, read_only=True)   # read-only: the chat never changes data

    found = None
    while not found:
        found = find_player(con, input("Which player? › ").strip())
        if not found:
            print("No player found, try another name.")
    player_id, player_name = found

    stats = stat_card(con, player_id)
    print(f"Loaded stats for {player_name}. Ask a question (or 'quit').\n")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Stats for {player_name}:\n\n{stats}"},
        {"role": "assistant", "content": f"Got it, I have {player_name}'s stats. What would you like to know?"},
    ]

    while True:
        question = input("You › ").strip()
        if question.lower() in {"quit", "exit", ""}:
            break
        messages.append({"role": "user", "content": question})

        print("AI  › ", end="", flush=True)
        answer = ""
        for chunk in chat(messages, stream=True):
            piece = chunk.message.content or ""
            print(piece, end="", flush=True)   # show each piece as it arrives
            answer += piece
            if chunk.done:                     # last chunk carries the token counts
                print(f"\n[{chunk.prompt_eval_count} tokens in, {chunk.eval_count} out]")
        print()

        # TODO 3: add the model's answer to `messages` so the next question
        #         has the conversation so far (that's all "memory" is)
        messages.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()