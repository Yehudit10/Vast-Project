-- Create an 11-class view (leaves the old 10-class view in place).
SET search_path TO audio_cls, public;

DROP VIEW IF EXISTS v_file_aggregates_probs11;
CREATE VIEW v_file_aggregates_probs11 AS
SELECT
  fa.run_id,
  fa.file_id,

  -- per-label probabilities (NULL if key missing in JSON)
  (fa.head_probs_json->>'predatory_animals')::double precision      AS head_p_predatory_animals,
  (fa.head_probs_json->>'non_predatory_animals')::double precision  AS head_p_non_predatory_animals,
  (fa.head_probs_json->>'birds')::double precision                   AS head_p_birds,
  (fa.head_probs_json->>'fire')::double precision                    AS head_p_fire,
  (fa.head_probs_json->>'footsteps')::double precision               AS head_p_footsteps,
  (fa.head_probs_json->>'insects')::double precision                 AS head_p_insects,
  (fa.head_probs_json->>'screaming')::double precision               AS head_p_screaming,
  (fa.head_probs_json->>'shotgun')::double precision                 AS head_p_shotgun,
  (fa.head_probs_json->>'stormy_weather')::double precision          AS head_p_stormy_weather,
  (fa.head_probs_json->>'streaming_water')::double precision         AS head_p_streaming_water,
  (fa.head_probs_json->>'vehicle')::double precision                 AS head_p_vehicle,

  -- final decision fields
  fa.head_pred_label,
  fa.head_pred_prob,
  fa.head_unknown_threshold,
  fa.head_is_another,

  -- aggregation context
  fa.num_windows,
  fa.agg_mode
FROM file_aggregates fa;
