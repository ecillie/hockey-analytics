"""PostgreSQL queries for the read-only public API.

The summary CTE deliberately chooses TOTAL rows when present and otherwise
aggregates team stints. That rule prevents traded players from being counted
twice while still supporting seasons whose source has no TOTAL row.
"""

SUMMARY_CTES = """
WITH team_choice AS (
    SELECT DISTINCT ON (pts.player_id, pts.season_start_year)
        pts.player_id, pts.season_start_year, t.id team_id,
        t.nhl_team_id, t.abbreviation, t.name team_name, t.city team_city,
        t.active team_active
    FROM player_team_stints pts
    JOIN teams t ON t.id = pts.team_id
    WHERE pts.season_start_year = :season
    ORDER BY pts.player_id, pts.season_start_year,
             (pts.departed_on IS NULL) DESC, pts.departed_on DESC NULLS LAST,
             pts.joined_on DESC NULLS LAST, pts.id DESC
),
traditional AS (
    SELECT s.player_id,
        SUM(s.games_played)::int games_played,
        SUM(s.goals)::int goals, SUM(s.assists)::int assists,
        SUM(s.points)::int points, SUM(s.plus_minus)::int plus_minus,
        SUM(s.penalty_minutes)::int penalty_minutes,
        SUM(s.power_play_goals)::int power_play_goals,
        SUM(s.power_play_points)::int power_play_points,
        SUM(s.short_handed_goals)::int short_handed_goals,
        SUM(s.shots)::int shots,
        CASE WHEN SUM(s.shots) > 0 THEN SUM(s.goals)::float / SUM(s.shots) END shooting_percentage
    FROM skater_season_stats s
    WHERE s.season_start_year = :season AND s.game_type = 2
      AND (s.stat_scope = 'TOTAL' OR NOT EXISTS (
          SELECT 1 FROM skater_season_stats total
          WHERE total.player_id = s.player_id
            AND total.season_start_year = s.season_start_year
            AND total.game_type = s.game_type AND total.stat_scope = 'TOTAL'))
    GROUP BY s.player_id
),
advanced AS (
    SELECT a.player_id,
        SUM(a.ice_time_seconds)::float ice_time_seconds,
        SUM(a.shifts)::int shifts, SUM(a.game_score)::float game_score,
        SUM(a.individual_expected_goals)::float individual_expected_goals,
        SUM(a.takeaways)::int takeaways, SUM(a.giveaways)::int giveaways,
        SUM(a.shots_blocked)::int shots_blocked,
        SUM(a.penalties)::int penalties, SUM(a.penalties_drawn)::int penalties_drawn,
        CASE WHEN SUM(a.ice_time_seconds) > 0
             THEN SUM(a.game_score) * 3600.0 / SUM(a.ice_time_seconds) END game_score_per_60,
        CASE WHEN SUM(a.ice_time_seconds) > 0
             THEN SUM(a.individual_expected_goals) * 3600.0 / SUM(a.ice_time_seconds) END expected_goals_per_60,
        CASE WHEN SUM(a.ice_time_seconds) > 0
             THEN SUM(a.on_ice_expected_goals_pct * a.ice_time_seconds)
                  / SUM(a.ice_time_seconds) END on_ice_expected_goals_pct
    FROM skater_advanced_season_stats a
    WHERE a.season_start_year = :season AND a.game_type = 2 AND a.situation = 'all'
      AND (a.stat_scope = 'TOTAL' OR NOT EXISTS (
          SELECT 1 FROM skater_advanced_season_stats total
          WHERE total.player_id = a.player_id
            AND total.season_start_year = a.season_start_year
            AND total.game_type = a.game_type AND total.situation = a.situation
            AND total.stat_scope = 'TOTAL'))
    GROUP BY a.player_id
),
goalie AS (
    SELECT g.player_id, SUM(g.games_played)::int games_played
    FROM goalie_season_stats g
    WHERE g.season_start_year = :season AND g.game_type = 2
      AND (g.stat_scope = 'TOTAL' OR NOT EXISTS (
          SELECT 1 FROM goalie_season_stats total
          WHERE total.player_id = g.player_id
            AND total.season_start_year = g.season_start_year
            AND total.game_type = g.game_type AND total.stat_scope = 'TOTAL'))
    GROUP BY g.player_id
),
eligible AS (
    SELECT a.player_id,
        CASE WHEN p.primary_position = 'D' THEN 'defense' ELSE 'forward' END position_group,
        a.game_score_per_60,
        a.ice_time_seconds / NULLIF(tr.games_played, 0) toi_per_game
    FROM advanced a JOIN players p ON p.id = a.player_id
    LEFT JOIN traditional tr ON tr.player_id = a.player_id
    WHERE p.primary_position <> 'G' AND tr.games_played >= 20 AND a.ice_time_seconds > 0
),
thresholds AS (
    SELECT position_group,
        percentile_cont(0.20) WITHIN GROUP (ORDER BY toi_per_game) toi_threshold
    FROM eligible GROUP BY position_group
),
replacement AS (
    SELECT e.position_group,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY e.game_score_per_60) replacement_gs60
    FROM eligible e JOIN thresholds t USING (position_group)
    WHERE e.toi_per_game <= t.toi_threshold
    GROUP BY e.position_group
),
active_model AS (
    SELECT id, version FROM model_versions
    WHERE active AND model_type IN ('skater_value', 'skater-value')
    ORDER BY created_at DESC LIMIT 1
),
projection AS (
    SELECT DISTINCT ON (pr.player_id) pr.player_id,
        NULLIF(pr.input_features ->> 'predicted_hockey_value', '')::float projected_hockey_value,
        am.version model_version
    FROM predictions pr
    JOIN active_model am ON am.id = pr.model_version_id
    WHERE pr.target_season = :season + 1
      AND pr.input_features ? 'predicted_hockey_value'
    ORDER BY pr.player_id, pr.created_at DESC
),
cap_hit AS (
    SELECT c.player_id, MAX(cs.cap_hit_cents)::bigint cap_hit_cents
    FROM contracts c JOIN contract_seasons cs ON cs.contract_id = c.id
    WHERE cs.season_start_year = :season GROUP BY c.player_id
),
summary AS (
    SELECT p.id, p.first_name, p.last_name,
        CONCAT_WS(' ', p.first_name, p.last_name) full_name,
        p.birth_date,
        CASE WHEN p.birth_date IS NULL THEN NULL
             ELSE EXTRACT(YEAR FROM age(CURRENT_DATE, p.birth_date))::int END age,
        p.primary_position, p.shoots_catches, p.nationality, p.active,
        p.roster_status::text roster_status,
        tc.team_id, tc.nhl_team_id, tc.abbreviation, tc.team_name, tc.team_city, tc.team_active,
        CAST(:season AS int) season,
        COALESCE(tr.games_played, g.games_played) games_played,
        tr.goals, tr.assists, tr.points, tr.plus_minus, tr.penalty_minutes,
        tr.power_play_goals, tr.power_play_points, tr.short_handed_goals,
        tr.shots, tr.shooting_percentage,
        a.ice_time_seconds, a.shifts, a.game_score, a.game_score_per_60,
        a.individual_expected_goals, a.expected_goals_per_60,
        a.on_ice_expected_goals_pct, a.takeaways, a.giveaways,
        a.shots_blocked, a.penalties, a.penalties_drawn,
        CASE WHEN a.game_score_per_60 IS NOT NULL AND r.replacement_gs60 IS NOT NULL
             THEN (a.game_score_per_60 - r.replacement_gs60) * a.ice_time_seconds / 3600.0 END hockey_value,
        pj.projected_hockey_value,
        CASE WHEN a.game_score_per_60 IS NOT NULL AND r.replacement_gs60 IS NOT NULL
             THEN a.game_score_per_60 - r.replacement_gs60 END gs60_above_replacement,
        CASE WHEN pj.model_version IS NOT NULL THEN pj.model_version
             WHEN a.game_score_per_60 IS NOT NULL
             THEN COALESCE((SELECT version FROM active_model), 'replacement-level-v1')
        END model_version,
        ch.cap_hit_cents
    FROM players p
    LEFT JOIN team_choice tc ON tc.player_id = p.id
    LEFT JOIN traditional tr ON tr.player_id = p.id
    LEFT JOIN advanced a ON a.player_id = p.id
    LEFT JOIN goalie g ON g.player_id = p.id
    LEFT JOIN replacement r ON r.position_group =
        CASE WHEN p.primary_position = 'D' THEN 'defense' ELSE 'forward' END
    LEFT JOIN projection pj ON pj.player_id = p.id
    LEFT JOIN cap_hit ch ON ch.player_id = p.id
)
"""


CONTRACT_SEASONS_SQL = """
SELECT cs.season_start_year, cs.base_salary_cents, cs.signing_bonus_cents,
    cs.performance_bonus_cents, cs.total_cash_cents, cs.cap_hit_cents,
    cs.cap_percentage, cs.is_slide,
    t.id team_id, t.nhl_team_id, t.abbreviation, t.name team_name,
    t.city team_city, t.active team_active
FROM contract_seasons cs LEFT JOIN teams t ON t.id = cs.owning_team_id
WHERE cs.contract_id = :contract_id ORDER BY cs.season_start_year
"""


TEAM_SQL = """
SELECT id, nhl_team_id, abbreviation, name team_name, city team_city,
       active team_active
FROM teams WHERE id = :team_id
"""


PLAYER_IDENTITY_SQL = """
SELECT p.id, p.first_name, p.last_name,
    CONCAT_WS(' ', p.first_name, p.last_name) full_name, p.birth_date,
    CASE WHEN p.birth_date IS NULL THEN NULL
         ELSE EXTRACT(YEAR FROM age(CURRENT_DATE, p.birth_date))::int END age,
    p.primary_position, p.shoots_catches, p.nationality, p.active,
    p.roster_status::text roster_status,
    t.id team_id, t.nhl_team_id, t.abbreviation, t.name team_name,
    t.city team_city, t.active team_active
FROM players p
LEFT JOIN LATERAL (
    SELECT pts.team_id FROM player_team_stints pts
    WHERE pts.player_id = p.id
    ORDER BY pts.season_start_year DESC, (pts.departed_on IS NULL) DESC,
             pts.departed_on DESC NULLS LAST, pts.joined_on DESC NULLS LAST,
             pts.id DESC LIMIT 1
) latest ON true
LEFT JOIN teams t ON t.id = latest.team_id
WHERE p.id = :player_id
"""


CONTRACT_SQL = """
SELECT c.id, c.player_id, c.signed_on, c.start_season, c.end_season,
    c.term_years, c.contract_type, c.expiry_status, c.total_value_cents,
    c.average_value_cents, c.is_entry_level,
    t.id signing_team_id, t.nhl_team_id signing_nhl_team_id,
    t.abbreviation signing_abbreviation, t.name signing_team_name,
    t.city signing_team_city, t.active signing_team_active
FROM contracts c LEFT JOIN teams t ON t.id = c.signing_team_id
WHERE c.player_id = :player_id
ORDER BY (:current_season BETWEEN c.start_season AND c.end_season) DESC,
         c.end_season DESC, c.signed_on DESC NULLS LAST, c.id DESC
LIMIT 1
"""


SEASONS_SQL = """SELECT start_year, end_year, label, salary_cap_cents
               FROM seasons
               WHERE start_year <= :latest_started_season
               ORDER BY start_year"""


CURRENT_SEASON_SQL = """SELECT MAX(start_year) FROM seasons
                    WHERE start_year <= :latest_started_season"""


HAS_SEASON_SQL = """SELECT EXISTS(
                    SELECT 1 FROM seasons
                    WHERE start_year = :season
                        AND start_year <= :latest_started_season
                    )"""


TEAMS_SQL = "SELECT id, nhl_team_id, abbreviation, name team_name, city team_city, active team_active FROM teams WHERE active ORDER BY name, id"


ROSTER_COUNTS_SQL = """SELECT p.roster_status::text roster_status, COUNT(*) count
               FROM players p JOIN LATERAL (
                 SELECT team_id FROM player_team_stints pts WHERE pts.player_id = p.id
                 ORDER BY season_start_year DESC, (departed_on IS NULL) DESC,
                          departed_on DESC NULLS LAST, pts.id DESC LIMIT 1
               ) stint ON true WHERE stint.team_id = :team_id GROUP BY p.roster_status"""


GOALIE_SQL = """
        WITH basic AS (
          SELECT SUM(g.games_played)::int games_played, SUM(g.wins)::int wins,
            SUM(g.losses)::int losses, SUM(g.overtime_losses)::int overtime_losses,
            SUM(g.shots_against)::int shots_against, SUM(g.saves)::int saves,
            CASE WHEN SUM(g.shots_against) > 0 THEN SUM(g.saves)::float / SUM(g.shots_against) END save_percentage,
            SUM(g.goals_against)::int goals_against, SUM(g.time_on_ice_seconds)::int time_on_ice_seconds,
            CASE WHEN SUM(g.time_on_ice_seconds) > 0 THEN SUM(g.goals_against) * 3600.0 / SUM(g.time_on_ice_seconds) END gaa,
            SUM(g.shutouts)::int shutouts
          FROM goalie_season_stats g WHERE g.player_id=:player_id AND g.season_start_year=:season AND g.game_type=2
            AND (g.stat_scope='TOTAL' OR NOT EXISTS (SELECT 1 FROM goalie_season_stats x WHERE x.player_id=g.player_id AND x.season_start_year=g.season_start_year AND x.game_type=2 AND x.stat_scope='TOTAL'))
        ), advanced AS (
          SELECT SUM(a.expected_goals_against)::float xga, SUM(a.goals_against)::float ga
          FROM goalie_advanced_season_stats a WHERE a.player_id=:player_id AND a.season_start_year=:season AND a.game_type=2 AND a.situation='all'
            AND (a.stat_scope='TOTAL' OR NOT EXISTS (SELECT 1 FROM goalie_advanced_season_stats x WHERE x.player_id=a.player_id AND x.season_start_year=a.season_start_year AND x.game_type=2 AND x.situation=a.situation AND x.stat_scope='TOTAL'))
        ) SELECT *, CASE WHEN xga IS NOT NULL AND ga IS NOT NULL THEN xga-ga END gsae FROM basic CROSS JOIN advanced
        """


PLAYER_SEASONS_SQL = """SELECT DISTINCT season_start_year season FROM (
                 SELECT season_start_year FROM skater_season_stats WHERE player_id=:player_id AND game_type=2
                 UNION SELECT season_start_year FROM goalie_season_stats WHERE player_id=:player_id AND game_type=2
               ) history ORDER BY season DESC LIMIT 40"""


CONTRACT_PLAYERS_SQL = """SELECT c.player_id FROM contracts c JOIN contract_seasons cs ON cs.contract_id=c.id
                           WHERE cs.owning_team_id=:team_id AND cs.season_start_year=:season ORDER BY c.player_id"""


CAP_SQL = """SELECT s.salary_cap_cents,
             COALESCE(SUM(cs.cap_hit_cents) FILTER (WHERE p.roster_status='ACTIVE'),0)::bigint active_cap,
             COALESCE(SUM(cs.cap_hit_cents) FILTER (WHERE p.roster_status='LTIR'),0)::bigint ltir_cap,
             COALESCE(SUM(GREATEST(cs.cap_hit_cents - :buried_relief_cents, 0))
                 FILTER (WHERE p.roster_status='MINORS'),0)::bigint minors_cap,
             COALESCE(SUM(CASE WHEN p.roster_status='MINORS'
                 THEN GREATEST(cs.cap_hit_cents - :buried_relief_cents, 0)
                 ELSE cs.cap_hit_cents END),0)::bigint total_cap
           FROM seasons s LEFT JOIN contract_seasons cs ON cs.season_start_year=s.start_year AND cs.owning_team_id=:team_id
           LEFT JOIN contracts c ON c.id=cs.contract_id LEFT JOIN players p ON p.id=c.player_id
           WHERE s.start_year=:season GROUP BY s.salary_cap_cents"""


SEARCH_PLAYERS_SQL = "SELECT id FROM players WHERE CONCAT_WS(' ', first_name, last_name) ILIKE :q ORDER BY active DESC, last_name, first_name, id LIMIT :limit"


SEARCH_TEAMS_SQL = """SELECT id, nhl_team_id, abbreviation, name team_name, city team_city, active team_active FROM teams
                              WHERE CONCAT_WS(' ', city, name, abbreviation) ILIKE :q ORDER BY active DESC, name, id LIMIT :limit"""
