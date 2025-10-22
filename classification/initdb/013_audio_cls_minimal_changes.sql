-- 013_audio_cls_minimal_changes.sql
-- Minimal changes: drop audioset_topk_json and add processing_ms.

BEGIN;

ALTER TABLE audio_cls.file_aggregates
  DROP COLUMN IF EXISTS audioset_topk_json;

ALTER TABLE audio_cls.file_aggregates
  ADD COLUMN IF NOT EXISTS processing_ms INTEGER
    CHECK (processing_ms IS NULL OR processing_ms >= 0);

COMMIT;
