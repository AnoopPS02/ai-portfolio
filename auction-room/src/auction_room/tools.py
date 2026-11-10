"""Tools the model can call.

A tool is two things:
  1. a normal Python function that does the work (runs SQL here), and
  2. a JSON schema that describes it to the model: name, what it does, its arguments.
The model never runs anything. It only replies "please call get_player_stats with
{name: ..., season: ...}". Your code runs the function and sends the result back.
"""


def _search(con, pattern: str):
    return con.execute(
        "SELECT player_id, name FROM players WHERE name ILIKE ? ORDER BY name",
        [pattern],
    ).fetchall()


def _find(con, name: str):
    """Try the name as typed, then looser patterns for full names like 'Virat Kohli'."""
    matches = _search(con, f"%{name}%")                 # 1. as typed: 'Dhoni', 'MS Dhoni'
    words = name.split()
    if matches or len(words) < 2:
        return matches

    first, surname = words[0], words[-1]
    matches = _search(con, f"{first[0]}% {surname}")    # 2. 'Virat Kohli' -> 'V% Kohli'
    if matches:
        return matches

    return _search(con, f"%{surname}%")                 # 3. surname only; may return several


def _season_rows(con, view: str, player_id: str, season):
    # `view` is always one of our own fixed names, never user text, so the f-string is safe.
    # Values that come from the model (player_id, season) still go in as ? parameters.
    sql = f"SELECT * EXCLUDE (player_id, player_name) FROM {view} WHERE player_id = ?"
    params = [player_id]
    if season is not None:
        sql += " AND season = ?"
        params.append(season)
    return con.execute(sql + " ORDER BY season", params).df()


def get_player_stats(con, name: str, season=None) -> str:
    """Season-level IPL batting and bowling for one player, as text for the model."""
    if season is not None:
        season = int(season)   # models sometimes send "2016" as a string; don't trust the type

    matches = _find(con, name)

    # TODO 2: handle the two cases where there isn't exactly one player.
    #   - 0 matches  -> return a short sentence the MODEL can act on
    #   - 2+ matches -> return the matching names so the model can ask the user which one
    #   There is no input() here: a tool can't talk to the user. It talks to the model,
    #   and the model decides what to say. Return text, don't print it.

    if len(matches) == 0:
        return f"No IPL player found matching '{name}'."
    elif len(matches) > 1:
        names = ', '.join(name for _, name in matches[:10])  # build "RG Sharma, Ishant Sharma, MM Sharma" from the tuples
        return f"Several players match '{name}': {names}(and {len(matches) - 10} more). Ask the user which one they mean, or for a fuller name."

    player_id, player_name = matches[0]
    batting = _season_rows(con, "batting_season", player_id, season)
    bowling = _season_rows(con, "bowling_season", player_id, season)

    header = f"PLAYER: {player_name} | " + (f"SEASON: {season}" if season else "ALL SEASONS")
    parts = [header]
    parts.append("BATTING\n" + batting.to_string(index=False) if not batting.empty
                 else "BATTING: no batting recorded for this filter.")
    parts.append("BOWLING\n" + bowling.to_string(index=False) if not bowling.empty
                 else "BOWLING: no bowling recorded for this filter.")
    return "\n\n".join(parts)


# ---------- the description the model reads ----------
# The model decides WHETHER to call a tool and WHAT to pass purely from this text,
# so the descriptions are prompt engineering, not documentation.
GET_PLAYER_STATS = {
    "type": "function",
    "function": {
        "name": "get_player_stats",
        "description": (
            "Returns season-by-season IPL batting and bowling stats for one player: "
            "runs, balls faced, strike rate, average, fours, sixes, powerplay balls per boundary, "
            "wickets, economy, and middle/death-over wickets and economy. "
            "Use it for any question about a player's IPL numbers or whether they played in a season. "
            "It has no match-level data (no highest score, no single-match figures) "
            "and nothing about teams, titles, venues, prices or personal details."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "Player name as the user said it. Partial names like 'Dhoni' or 'Kohli' are fine."
                        "Some players names are abbreviated like if the user asks for Virat Kohli stats then it is similar to V Kohli"
                    ),
                },
                "season": {
                    "type": "integer",
                    "description": (
                        "IPL season year, e.g. 2016. Leave it out when the user doesn't name a year; "
                        "the tool then returns every season the player has played."
                    ),
                },
            },
            "required": ["name"],
        },
    },
}

TOOLS = [GET_PLAYER_STATS]                        # what the model is shown
REGISTRY = {"get_player_stats": get_player_stats}  # name -> the function your code runs