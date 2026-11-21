"""Scout report v0: the model fills a typed PlayerScoutReport, we check it, and retry on failure.

Three layers of "is this output OK?":
  1. format=schema  -> Ollama forces valid JSON in roughly the right shape
  2. Pydantic       -> the RULES: allowed roles, 1-3 strengths, summary length...
  3. your own check -> the TRUTH: does every cited season exist in this player's stats?
Each layer catches things the one before it can't.

Run:  uv run python scout_report.py Virat Kohli
"""
import sys
from typing import Literal

import duckdb
from pydantic import BaseModel, Field, ValidationError, field_validator

from auction_room.llm import chat
from auction_room.tools import _find, get_player_stats

DB = "data/auction_room.duckdb"
MAX_ATTEMPTS = 3

# Literal = "only these exact strings are allowed". Anything else fails validation.
# TODO 1a: list the roles an IPL scout would use (8-10 of them), e.g. "opening batter", "death bowler"...
Role = Literal["batsmen","bowler","opening batter", "death bowler", "powerplay specialist bowler", "pinch hitter", "batting allrounder", "bowling allrounder", "mystery spinner",
                "middle-overs accelerator", "finisher", "wicketkeeper-batsman"]

PriceBand = Literal["base price (under 1 cr)", "1-5 cr", "5-10 cr", "10-15 cr", "15+ cr"]


class Evidence(BaseModel):
    """One strength or risk, tied to a number. Use this as your example for TODO 1b."""
    point: str = Field(description="One short sentence, e.g. 'Scores fast in the powerplay'")
    season: int = Field(description="The season the number comes from, e.g. 2016")
    stat: str = Field(description="The exact number from the stats, e.g. 'strike rate 152.0'")


class PlayerScoutReport(BaseModel):
    player_name: str
    # TODO 1b: add the fields
    #   role        -> one Role
    #   strengths   -> a list of Evidence, at least 1 and at most 3   (Field(min_length=..., max_length=...))
    #   risks       -> same rules as strengths
    #   price_band  -> one PriceBand
    #   summary     -> a string, at most 300 characters
    # (No "confidence" field: you saw last week that a model rating itself means nothing.)
    role: Role
    strengths: list[Evidence] = Field(min_length=1, max_length=3)
    risks: list[Evidence] = Field(min_length=1, max_length=3)
    price_band: PriceBand
    #summary: str = Field(max_length=300, description="2 sentences, under 300 characters")
    summary: str = Field(description="Exactly 2 short sentences.")

    @field_validator("summary")
    @classmethod
    def summary_not_too_long(cls, v: str) -> str:
        """Over 300 characters? Trim to the last full sentence. Code repairs it, no retry needed."""
        v = v.strip()
        if len(v) <= 300:
            return v                                   # short enough: keep as is

        cut = v[:300]
        if cut.endswith("."):
            return cut                                 # a sentence happened to end exactly at 300
        if ". " in cut:
            return cut.rsplit(". ", 1)[0] + "."        # back to the last real sentence end
        return cut.rsplit(" ", 1)[0] + "…"

def seasons_played(con, player_id: str) -> set[int]:
    rows = con.execute(
        """SELECT season FROM batting_season WHERE player_id = ?
           UNION SELECT season FROM bowling_season WHERE player_id = ?""",
        [player_id, player_id],
    ).fetchall()
    return {r[0] for r in rows}


def grounding_problems(report: PlayerScoutReport, seasons: set[int]) -> list[str]:
    """Layer 3: Pydantic can check that season is an int. Only you can check it's a REAL season."""
    problems = []
    # TODO 2: loop over every Evidence in strengths AND risks.
    #   If its season isn't in `seasons`, add a sentence the model can act on, e.g.
    #   "Season 2011 ('Scores fast in the powerplay') is not in this player's stats."
    for each in (report.strengths + report.risks):
        if each.season not in seasons:
            problems.append(f"Season {each.season} ({each.point}) is not in the player's stats")

    return problems


SYSTEM_PROMPT = """You are an IPL scout preparing for the 2027 auction.
Write a scout report using ONLY the stats provided.
- risks must come from the player’s last 4 seasons
- Every strength and risk must cite a season and an exact number from the stats.
- Prefer recent seasons; a player's form from 10 years ago matters less.
- Decide first whether the player is mainly a batter or mainly a bowler, from where his workload is.
- "batting allrounder" only for batters who also bowled at least 50 legal balls per season recently.
- A player whose bowling workload is much larger than his batting is a bowler: use a bowling role.
- "finisher" only if death_balls_faced is at least 10 and death_strike_rate is at least 130 in recent seasons
- price_band is your judgment; there is no auction price data in the stats.
- Reply with JSON matching the schema, nothing else."""


def scout_report(con, player_id: str, player_name: str) -> PlayerScoutReport:
    # No tool calling here: we already know exactly which data is needed, so we just fetch it.
    stats = get_player_stats(con, player_name)
    seasons = seasons_played(con, player_id)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Scout report for {player_name}.\n\n{stats}"},
    ]
    schema = PlayerScoutReport.model_json_schema()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        r = chat(messages, schema=schema)
        raw = r.message.content          # a JSON string

        # TODO 3: validate, check grounding, and give feedback on failure.
        #   a. try:  report = PlayerScoutReport.model_validate_json(raw)
        #   b.       problems = grounding_problems(report, seasons)
        #            no problems -> print(f"[attempt {attempt}] valid") and return report
        #            problems    -> feedback = a sentence listing them
        #   c. except ValidationError as e:
        #            feedback = a sentence with the errors (str(e) works; e.errors() is tidier)
        #   d. print(f"[attempt {attempt}] rejected: {feedback}")
        #   e. append the model's bad JSON as an "assistant" message, then your feedback
        #      as a "user" message asking for corrected JSON. Then the loop tries again.
        try:
            report = PlayerScoutReport.model_validate_json(raw)
            problems = grounding_problems(report, seasons)
            if not problems:
                print(f"[attempt {attempt}] valid")
                return report
            else:
                feedback = "Fix these problems: " + " ".join(problems)
        except ValidationError as e:
            feedback = str(e)
        print(f"[attempt {attempt}] rejected: {feedback}")
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": feedback})


    raise RuntimeError(f"No valid report after {MAX_ATTEMPTS} attempts")

# ---------- as an agent tool ----------

def get_scout_report(con, name: str) -> str:
    """Tool wrapper: one player's validated scout report, as JSON text for the model."""
    matches = _find(con, name)
    # TODO A: 0 matches or 2+ matches -> return a sentence the model can act on.
    #         You've written exactly this in get_player_stats; reuse the same idea.

    if len(matches) == 0:
        return f"No IPL player found matching '{name}'."
    if len(matches) > 1:
        names = ", ".join(player_name for _, player_name in matches[:10])
        more = f" (and {len(matches) - 10} more)" if len(matches) > 10 else ""
        return f"Several players match '{name}': {names}{more}. Ask the user which one they mean, or for a fuller name."

    player_id, player_name = matches[0]
    try:
        report = scout_report(con, player_id, player_name)
    except RuntimeError as e:          # all retries failed inside scout_report
        return f"Could not produce a valid scout report for {player_name}: {e}"
    return report.model_dump_json()    # the validated object, back to text for the model


GET_SCOUT_REPORT = {
    "type": "function",
    "function": {
        "name": "get_scout_report",
        # TODO B: the 3-part description. Make sure it says:
        #   - what it returns (role, strengths and risks with evidence, price band, summary)
        #   - use it ONLY when the user asks to scout / evaluate / assess a player for the auction
        #   - it is slow (it runs its own model call), so don't use it for simple stat questions
        "description": (
            "Returns role, strengths and risks with evidence, price band, summary for one player."
            "use it ONLY when the user asks to scout / evaluate / assess a player for the auction."
            "it is slow (it runs its own model call), so don't use it for simple stat questions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                # TODO C: one property, `name`, same style as get_player_stats
                "name":{
                    "type": "string",
                    "description": (
                        "Player name as the user said it. Partial names like 'Dhoni' or 'Kohli' are fine."
                        "Some players names are abbreviated like if the user asks for Virat Kohli stats then it is similar to V Kohli"
                    ),
                }
            },
            "required": ["name"],   # TODO C
        },
    },
}


def main():
    name = " ".join(sys.argv[1:]) or input("Player? › ").strip()
    con = duckdb.connect(DB, read_only=True)
    matches = _find(con, name)
    if len(matches) != 1:
        print("Matches:", ", ".join(n for _, n in matches[:10]) or "none", "- be more specific.")
        return
    player_id, player_name = matches[0]
    report = scout_report(con, player_id, player_name)
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()