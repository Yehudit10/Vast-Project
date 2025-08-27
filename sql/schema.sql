-- Enable extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Main table
CREATE TABLE IF NOT EXISTS embeddings (
  id  BIGSERIAL PRIMARY KEY,
  vec vector(384)
);

-- HNSW index as required: m=4, ef_construction=10
CREATE INDEX IF NOT EXISTS idx_embeddings_vec_hnsw
  ON embeddings USING hnsw (vec vector_l2_ops)
  WITH (m = 4, ef_construction = 10);

-- Benchmark table
CREATE TABLE IF NOT EXISTS nn42_bench(
  ts timestamptz DEFAULT now(),
  ms double precision
);

-- Benchmark function (single run)
CREATE OR REPLACE FUNCTION bench_nn42_once() RETURNS double precision AS $$
DECLARE
  q vector(384); t0 timestamptz; dur_ms double precision;
BEGIN
  SELECT ARRAY(SELECT random() FROM generate_series(1,384))::vector(384) INTO q;
  t0 := clock_timestamp();
  PERFORM id FROM embeddings ORDER BY vec <-> q LIMIT 42;
  dur_ms := EXTRACT(EPOCH FROM (clock_timestamp() - t0)) * 1000.0;
  INSERT INTO nn42_bench(ms) VALUES (dur_ms);
  RETURN dur_ms;
END$$ LANGUAGE plpgsql;
