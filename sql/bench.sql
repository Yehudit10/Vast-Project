-- Optional: seed small demo data (10k vectors in batches)
TRUNCATE TABLE embeddings;
DO $$
BEGIN
  FOR i IN 1..10 LOOP
    INSERT INTO embeddings (vec)
    SELECT ARRAY(SELECT random() FROM generate_series(1,384))::vector(384)
    FROM generate_series(1,1000);
    PERFORM pg_sleep(0.2);
  END LOOP;
END$$;
VACUUM ANALYZE embeddings;

-- Build HNSW only after loading (if needed):
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname='idx_embeddings_vec_hnsw') THEN
    EXECUTE 'CREATE INDEX idx_embeddings_vec_hnsw ON embeddings USING hnsw (vec vector_l2_ops) WITH (m=4, ef_construction=10)';
  END IF;
END$$;

-- Point query 42-NN with timing
SET hnsw.ef_search = 100;
\timing on
WITH q(v) AS (
  SELECT ARRAY(SELECT random() FROM generate_series(1,384))::vector(384)
)
SELECT id
FROM embeddings, q
ORDER BY vec <-> q.v
LIMIT 42;

-- Run 20 samples into nn42_bench
DO $$
BEGIN
  FOR i IN 1..20 LOOP
    PERFORM bench_nn42_once();
  END LOOP;
END$$;

-- Summary (cast to numeric for round)
SELECT
  count(*)                           AS runs,
  round(avg(ms)::numeric,2)          AS avg_ms,
  round(min(ms)::numeric,2)          AS min_ms,
  round(max(ms)::numeric,2)          AS max_ms
FROM nn42_bench;
