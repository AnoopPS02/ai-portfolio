"""Season-level stat views built on top of the deliveries table."""

BATTING_SQL = """
CREATE OR REPLACE VIEW batting_season AS
WITH batting AS (
    SELECT
        d.batter_id AS player_id,
        p.name AS player_name,
        m.season,
        SUM(d.runs_batter::INT) AS runs,
        SUM(d.is_ball_faced::INT) AS balls_faced,
        ROUND(100.0 * SUM(d.runs_batter) / NULLIF(SUM(d.is_ball_faced::INT), 0), 1) AS strike_rate,
        SUM(d.is_four::INT) AS number_of_fours,
        SUM(d.is_six::INT) AS number_of_sixes,
        ROUND(SUM(d.is_ball_faced::INT) FILTER (WHERE d.phase = 'powerplay') * 1.0
            / NULLIF(SUM(d.is_four::INT + d.is_six::INT) FILTER (WHERE d.phase = 'powerplay'), 0),2)
            AS pp_balls_per_boundary
    FROM deliveries d
    JOIN matches m USING (match_id)
    JOIN players p ON p.player_id = d.batter_id
    WHERE NOT d.is_super_over
    GROUP BY ALL
),
outs AS (
    SELECT
        d.player_out_id AS player_id,
        m.season,
        COUNT(*) AS dismissals
    FROM deliveries d
    JOIN matches m USING (match_id)
    WHERE d.is_wicket
      AND NOT d.is_super_over
      AND d.wicket_kind <> 'retired hurt'
    GROUP BY ALL
)
SELECT
    b.*,
    COALESCE(o.dismissals, 0) AS dismissals,
    ROUND(b.runs * 1.0 / NULLIF(o.dismissals, 0), 2) AS average
FROM batting b
LEFT JOIN outs o USING (player_id, season)
"""
BOWLING_SQL = """
CREATE OR REPLACE VIEW bowling_season AS
SELECT
	d.bowler_id as bowler_id,
	p.name AS player_name,
	m.season,
	SUM(is_legal_ball::INT) as legal_deliveries_bowled,
	sum(runs_conceded) as runs_conceded,
	sum(is_bowler_wicket::INT) as wickets_taken,
	ROUND(SUM(d.runs_conceded) * 6.0 / NULLIF(SUM(d.is_legal_ball::INT), 0), 2) as bowling_economy,
	sum(is_bowler_wicket::INT) FILTER (WHERE d.phase = 'middle') as middle_overs_wickets_taken,
	ROUND(sum(runs_conceded) FILTER (WHERE d.phase = 'middle') * 6.0  / NULLIF((SUM(is_legal_ball::INT) FILTER (WHERE d.phase = 'middle')) ,0),2) as middle_overs_economy,
	sum(is_bowler_wicket::INT) FILTER (WHERE d.phase = 'death') as death_overs_wickets_taken,
	ROUND(sum(runs_conceded) FILTER (WHERE d.phase = 'death') * 6.0 / NULLIF((SUM(is_legal_ball::INT) FILTER (WHERE d.phase = 'death')) ,0),2) as death_overs_economy
FROM deliveries d
JOIN matches m USING (match_id)
JOIN players p ON p.player_id = d.bowler_id
WHERE NOT d.is_super_over
GROUP BY bowler_id,p.name, m.season
"""

def create_views(con):
    """(Re)create all stat views. Safe to run any number of times."""
    con.execute(BATTING_SQL)
    con.execute(BOWLING_SQL)