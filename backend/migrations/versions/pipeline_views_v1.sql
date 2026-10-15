-- Frozen Phase 6 consumer projections. Change through a new migration.
CREATE SCHEMA pipeline_api;

CREATE VIEW pipeline_api.teams AS  SELECT (payload->>'team_id')::bigint AS id,
    (payload->>'nhl_team_id')::bigint AS nhl_team_id,
    (payload->>'name')::text AS name,
    (payload->>'abbreviation')::text AS abbreviation,
    (payload->>'city')::text AS city,
    (payload->>'active')::boolean AS active
FROM public.pipeline_current r WHERE dataset='teams'  ;

CREATE VIEW pipeline_api.seasons AS  SELECT (payload->>'season')::integer AS start_year,
    (payload->>'end_year')::integer AS end_year,
    (payload->>'label')::text AS label,
    (payload->>'salary_cap')::bigint AS salary_cap_cents
FROM public.pipeline_current r WHERE dataset='seasons'  ;

CREATE VIEW pipeline_api.players AS  SELECT (payload->>'player_id')::bigint AS id,
    (payload->>'nhl_player_id')::bigint AS nhl_player_id,
    (payload->>'first_name')::text AS first_name,
    (payload->>'last_name')::text AS last_name,
    (payload->>'nationality')::text AS nationality,
    (payload->>'shoots_catches')::text AS shoots_catches,
    (payload->>'birth_date')::date AS birth_date,
    (payload->>'position')::text AS primary_position,
    (payload->>'active')::boolean AS active,
    COALESCE((SELECT payload->>'status' FROM public.pipeline_current s WHERE s.dataset='roster_state' AND s.payload->>'player_id'=r.payload->>'player_id'),'UNKNOWN') AS roster_status
FROM public.pipeline_current r WHERE dataset='player_profiles'  ;

CREATE VIEW pipeline_api.player_team_stints AS  SELECT (payload->>'membership_id')::bigint AS id,
    (payload->>'player_id')::bigint AS player_id,
    (payload->>'team_id')::bigint AS team_id,
    (payload->>'season')::integer AS season_start_year,
    (payload->>'effective_from')::date AS joined_on,
    (payload->>'effective_to')::date AS departed_on
FROM public.pipeline_current r WHERE dataset='memberships'  ;

CREATE VIEW pipeline_api.contracts AS  SELECT (payload->>'contract_id')::bigint AS id,
    (payload->>'player_id')::bigint AS player_id,
    (payload->>'signing_team_id')::bigint AS signing_team_id,
    (payload->>'signed_on')::date AS signed_on,
    (payload->>'start_season')::integer AS start_season,
    (payload->>'end_season')::integer AS end_season,
    (payload->>'term_years')::integer AS term_years,
    (payload->>'contract_type')::text AS contract_type,
    (payload->>'expiry_status')::text AS expiry_status,
    (payload->>'total_value')::bigint AS total_value_cents,
    (payload->>'average_value')::bigint AS average_value_cents,
    (payload->>'is_entry_level')::boolean AS is_entry_level
FROM public.pipeline_current r WHERE dataset='contracts'  ;

CREATE VIEW pipeline_api.contract_seasons AS  SELECT (payload->>'contract_id')::bigint AS contract_id,
    (payload->>'owning_team_id')::bigint AS owning_team_id,
    (payload->>'season')::integer AS season_start_year,
    (payload->>'base_salary')::bigint AS base_salary_cents,
    (payload->>'signing_bonus')::bigint AS signing_bonus_cents,
    (payload->>'performance_bonus')::bigint AS performance_bonus_cents,
    (payload->>'total_cash')::bigint AS total_cash_cents,
    (payload->>'cap_hit')::bigint AS cap_hit_cents,
    (payload->>'cap_percentage')::double precision AS cap_percentage,
    (payload->>'is_slide')::boolean AS is_slide
FROM public.pipeline_current r WHERE dataset='contract_seasons'  ;

CREATE VIEW pipeline_api.skater_season_stats AS  SELECT (payload->>'player_id')::bigint AS player_id,
    (payload->>'season')::integer AS season_start_year,
    (payload->>'team_id')::bigint AS team_id,
    (payload->>'team_scope')::text AS stat_scope,
    (payload->>'game_type')::integer AS game_type,
    accepted_at AS updated_at,
    (payload->>'games_played')::bigint AS games_played,
    (payload->>'goals')::bigint AS goals,
    (payload->>'assists')::bigint AS assists,
    (payload->>'points')::bigint AS points,
    (payload->>'plus_minus')::bigint AS plus_minus,
    (payload->>'penalty_minutes')::bigint AS penalty_minutes,
    (payload->>'power_play_goals')::bigint AS power_play_goals,
    (payload->>'power_play_points')::bigint AS power_play_points,
    (payload->>'short_handed_goals')::bigint AS short_handed_goals,
    (payload->>'shots')::bigint AS shots,
    (payload->>'shooting_percentage')::double precision AS shooting_percentage
FROM public.pipeline_current r WHERE dataset='basic_stats' AND payload->>'stat_kind'='skater' AND lower(payload->>'source') IN ('nhl','cap space') AND payload->>'source' = (SELECT p.payload->>'source' FROM public.pipeline_current p
WHERE p.dataset=r.dataset AND p.payload->>'player_id'=r.payload->>'player_id'
AND p.payload->>'season'=r.payload->>'season' AND p.payload->>'game_type'=r.payload->>'game_type'
AND p.payload->>'stat_kind'=r.payload->>'stat_kind' AND lower(p.payload->>'source') IN ('nhl','cap space')
ORDER BY CASE lower(p.payload->>'source') WHEN 'nhl' THEN 0 WHEN 'cap space' THEN 1 ELSE 2 END,
p.payload->>'source' LIMIT 1) ;

CREATE VIEW pipeline_api.goalie_season_stats AS  SELECT (payload->>'player_id')::bigint AS player_id,
    (payload->>'season')::integer AS season_start_year,
    (payload->>'team_id')::bigint AS team_id,
    (payload->>'team_scope')::text AS stat_scope,
    (payload->>'game_type')::integer AS game_type,
    accepted_at AS updated_at,
    (payload->>'games_played')::bigint AS games_played,
    (payload->>'wins')::bigint AS wins,
    (payload->>'losses')::bigint AS losses,
    (payload->>'overtime_losses')::bigint AS overtime_losses,
    (payload->>'saves')::bigint AS saves,
    (payload->>'shots_against')::bigint AS shots_against,
    (payload->>'goals_against')::bigint AS goals_against,
    (payload->>'shutouts')::bigint AS shutouts,
    (payload->>'time_on_ice')::double precision AS time_on_ice_seconds,
    (payload->>'save_percentage')::double precision AS save_percentage,
    (payload->>'goals_against_average')::double precision AS goals_against_average
FROM public.pipeline_current r WHERE dataset='basic_stats' AND payload->>'stat_kind'='goalie' AND lower(payload->>'source') IN ('nhl','cap space') AND payload->>'source' = (SELECT p.payload->>'source' FROM public.pipeline_current p
WHERE p.dataset=r.dataset AND p.payload->>'player_id'=r.payload->>'player_id'
AND p.payload->>'season'=r.payload->>'season' AND p.payload->>'game_type'=r.payload->>'game_type'
AND p.payload->>'stat_kind'=r.payload->>'stat_kind' AND lower(p.payload->>'source') IN ('nhl','cap space')
ORDER BY CASE lower(p.payload->>'source') WHEN 'nhl' THEN 0 WHEN 'cap space' THEN 1 ELSE 2 END,
p.payload->>'source' LIMIT 1) ;

CREATE VIEW pipeline_api.skater_advanced_season_stats AS  SELECT (payload->>'player_id')::bigint AS player_id,
    (payload->>'season')::integer AS season_start_year,
    (payload->>'team_id')::bigint AS team_id,
    (payload->>'team_scope')::text AS stat_scope,
    (payload->>'game_type')::integer AS game_type,
    accepted_at AS updated_at,
    (payload->>'situation')::text AS situation,
    (payload->>'ice_time')::double precision AS ice_time_seconds,
    (payload->>'expected_goals')::double precision AS individual_expected_goals,
    (payload->>'on_ice_expected_goals_pct')::double precision AS on_ice_expected_goals_pct,
    (payload->>'game_score')::double precision AS game_score,
    (payload->>'shifts')::bigint AS shifts,
    (payload->>'individual_points')::bigint AS individual_points,
    (payload->>'individual_goals')::bigint AS individual_goals,
    (payload->>'individual_primary_assists')::bigint AS individual_primary_assists,
    (payload->>'individual_secondary_assists')::bigint AS individual_secondary_assists,
    (payload->>'individual_shots_on_goal')::bigint AS individual_shots_on_goal,
    (payload->>'individual_unblocked_attempts')::bigint AS individual_unblocked_attempts,
    (payload->>'takeaways')::bigint AS takeaways,
    (payload->>'giveaways')::bigint AS giveaways,
    (payload->>'shots_blocked')::bigint AS shots_blocked,
    (payload->>'penalties')::bigint AS penalties,
    (payload->>'penalties_drawn')::bigint AS penalties_drawn,
    (payload->>'offensive_zone_shift_starts')::bigint AS offensive_zone_shift_starts,
    (payload->>'defensive_zone_shift_starts')::bigint AS defensive_zone_shift_starts,
    (payload->>'neutral_zone_shift_starts')::bigint AS neutral_zone_shift_starts
FROM public.pipeline_current r WHERE dataset='moneypuck_skater_stats' AND lower(payload->>'source')='moneypuck' ;

CREATE VIEW pipeline_api.goalie_advanced_season_stats AS  SELECT (payload->>'player_id')::bigint AS player_id,
    (payload->>'season')::integer AS season_start_year,
    (payload->>'team_id')::bigint AS team_id,
    (payload->>'team_scope')::text AS stat_scope,
    (payload->>'game_type')::integer AS game_type,
    accepted_at AS updated_at,
    (payload->>'situation')::text AS situation,
    (payload->>'ice_time')::double precision AS ice_time_seconds,
    (payload->>'expected_goals_against')::double precision AS expected_goals_against,
    (payload->>'goals_against')::double precision AS goals_against
FROM public.pipeline_current r WHERE dataset='moneypuck_goalie_stats' AND lower(payload->>'source')='moneypuck' ;

CREATE VIEW pipeline_api.model_versions AS  SELECT (payload->>'model_id')::bigint AS id,
    (payload->>'version')::text AS version,
    (payload->>'model_type')::text AS model_type,
    (payload->>'active')::boolean AS active,
    (payload->>'created_at')::timestamptz AS created_at
FROM public.pipeline_current r WHERE dataset='model_versions'  UNION ALL SELECT id,version,model_type,active,created_at FROM public.model_versions old
WHERE NOT EXISTS (SELECT 1 FROM public.pipeline_current n WHERE n.dataset='model_versions' AND (n.payload->>'model_id')::bigint=old.id);

CREATE VIEW pipeline_api.predictions AS  SELECT (payload->>'prediction_id')::bigint AS id,
    (payload->>'player_id')::bigint AS player_id,
    (payload->>'model_id')::bigint AS model_version_id,
    (payload->>'target_season')::integer AS target_season,
    payload->'input_features' AS input_features,
    (payload->>'created_at')::timestamptz AS created_at
FROM public.pipeline_current r WHERE dataset='predictions'  UNION ALL SELECT id,player_id,model_version_id,target_season,input_features,created_at FROM public.predictions old
WHERE NOT EXISTS (SELECT 1 FROM public.pipeline_current n WHERE n.dataset='predictions' AND (n.payload->>'prediction_id')::bigint=old.id);
