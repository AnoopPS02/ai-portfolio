"""Team-needs tool: what does a franchise still need going into the auction?

Everything here is DETERMINISTIC: SQL + Python rules, no LLM. The model only calls the
tool and explains the result. Slots, purse and role counts are facts and arithmetic,
and models are bad at both, so code does them.

Put this file in src/auction_room/ and register the tool in tools.py (see the bottom).
"""

RECENT_FROM = 2025          # "recent" = these seasons onward
SQUAD_MAX, OVERSEAS_MAX = 25, 8
TEAMS = ["CSK", "DC", "GT", "KKR", "LSG", "MI", "PBKS", "RCB", "RR", "SRH"]

# One row per retained player of a team, with recent phase workloads (0 = none / uncapped)
SQUAD_SQL = """
WITH recent AS (
    SELECT d.*
    FROM deliveries d JOIN matches m USING (match_id)
    WHERE m.season >= ? AND NOT d.is_super_over
),
bat AS (
    SELECT batter_id AS player_id,
           SUM(is_ball_faced::INT) FILTER (WHERE phase = 'powerplay')  AS pp_balls_faced,
           SUM(is_ball_faced::INT) FILTER (WHERE phase = 'death') AS death_balls_faced
    FROM recent
    GROUP BY ALL
),
bowl AS (
    SELECT bowler_id AS player_id,
           SUM(is_legal_ball::INT) AS balls_bowled,
           SUM(is_legal_ball::INT) FILTER (WHERE phase = 'death') AS death_balls_bowled
    FROM recent
    GROUP BY ALL
)
SELECT r.player, r.overseas,
       COALESCE(b.pp_balls_faced, 0)     AS pp_balls_faced,
       COALESCE(b.death_balls_faced, 0)  AS death_balls_faced,
       COALESCE(w.balls_bowled, 0)       AS balls_bowled,
       COALESCE(w.death_balls_bowled, 0) AS death_balls_bowled
FROM retained r
LEFT JOIN bat  b USING (player_id)
LEFT JOIN bowl w USING (player_id)
WHERE r.team = ?
ORDER BY r.player
"""

# How many of each role a balanced squad wants. Your call: tweak these.
TARGETS = {"powerplay batter": 3, "finisher": 2, "death bowler": 3, "frontline bowler": 6}


def roles_of(p) -> list[str]:
    """Roles a player covers, from his recent workload. `p` is one row (p.pp_balls_faced etc.)."""
    roles = []
    # TODO 2: your cricket rules, one `if` per role in TARGETS, e.g.
    #   faced at least ___ powerplay balls since 2025      -> "powerplay batter"
    #   faced at least ___ death-over balls                -> "finisher"
    #   bowled at least ___ legal death-over balls         -> "death bowler"
    #   bowled at least ___ legal balls in total           -> "frontline bowler"
    # Scale check: one full IPL season of 4 overs a game is about 14 x 24 = 336 balls.
    if p.pp_balls_faced >= 120:
        roles.append("powerplay batter")
    if p.death_balls_faced >= 60:
        roles.append("finisher")
    if p.death_balls_bowled >= 60:
        roles.append("death bowler")
    if p.balls_bowled >= 200:
        roles.append("frontline bowler")
    return roles


def get_team_needs(con, team: str) -> str:
    team = team.upper().strip()
    if team not in TEAMS:
        return f"Unknown team '{team}'. Use one of: {', '.join(TEAMS)}."

    squad = con.execute(SQUAD_SQL, [RECENT_FROM, team]).df()
    purse = con.execute("SELECT purse_left_cr FROM purse WHERE team = ?", [team]).fetchone()[0]

    counts = {role: 0 for role in TARGETS}
    lines = []
    for p in squad.itertuples():
        roles = roles_of(p)
        for r in roles:
            counts[r] += 1
        tag = " (overseas)" if p.overseas else ""
        #lines.append(f"- {p.player}{tag}: {', '.join(roles) or 'no recent IPL workload'}")
        workload = (f"pp faced {p.pp_balls_faced}, death faced {p.death_balls_faced}, "
                    f"bowled {p.balls_bowled}, death bowled {p.death_balls_bowled}")
        no_data = p.pp_balls_faced + p.death_balls_faced + p.balls_bowled == 0
        label = ", ".join(roles) or ("no recent IPL workload" if no_data else "no role at these thresholds")
        lines.append(f"- {p.player}{tag}: {label} ({workload})")

    overseas = int(squad["overseas"].sum())
    gaps = [f"{role}: needs {want - counts[role]} more (has {counts[role]}, target {want})"
            for role, want in TARGETS.items() if counts[role] < want]

    return "\n".join([
        f"TEAM: {team} | purse left: Rs {purse:.2f} cr",
        f"Squad: {len(squad)}/{SQUAD_MAX} (slots left: {SQUAD_MAX - len(squad)}) | "
        f"overseas: {overseas}/{OVERSEAS_MAX} (overseas slots left: {OVERSEAS_MAX - overseas})",
        f"Roles judged from IPL seasons {RECENT_FROM} onward; uncapped players have no workload yet.",
        "ROLE GAPS: " + ("; ".join(gaps) if gaps else "none"),
        "SQUAD:",
        *lines,
    ])


# TODO 3: the schema the model reads. One argument, `team`.
#   New idea: "enum": TEAMS  -> the model may only send one of these exact strings.
#   Say in the description what the tool returns and when to use it (look at the return text above).
GET_TEAM_NEEDS = {
    "type": "function",
    "function": {
        "name": "get_team_needs",
        "description": (
            "Returns players for one IPL franchise ahead of the 2027 auction. "
            "Use it for questions about death specialist or a powerplay specialist. "
            "Use it for questions like how many slots left or how many overseas slots left to fill."
            "Use it for identifying which player roles does team is lacking."
            "Use it for how much purse the team has left."
            "It does not have roles judged previous to 2025 and no auction prices and it has only players retained."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "team": {
                    "type": "string",
                    "enum": TEAMS,
                    "description": (
                        "IPL Team name, e.g, CSK as in Chennai super kings, RCB as in Bengaluru"
                    ),
                }
            },
            "required": [],
        },
    },
}

# ---- then in tools.py ----
#from auction_room.team_needs import GET_TEAM_NEEDS, get_team_needs
#TOOLS = [GET_PLAYER_STATS, GET_TEAM_NEEDS]
#REGISTRY = {"get_player_stats": get_player_stats, "get_team_needs": get_team_needs}