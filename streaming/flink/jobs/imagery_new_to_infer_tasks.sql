-- English-only comments
-- Source: MinIO notifications (Kafka)
CREATE TABLE imagery_new (
  bucket STRING,
  key STRING,
  size BIGINT,
  etag STRING,
  ts TIMESTAMP(3),
  WATERMARK FOR ts AS ts - INTERVAL '5' SECOND
) WITH (
  'connector' = 'kafka',
  'topic' = 'imagery.new',
  'properties.bootstrap.servers' = '${kafka.bootstrap}',
  'format' = 'json',
  'scan.startup.mode' = 'latest-offset'
);

-- Sink: inference task queue (Kafka)
CREATE TABLE infer_tasks (
  bucket STRING,
  key STRING,
  ts TIMESTAMP(3)
) WITH (
  'connector' = 'kafka',
  'topic' = 'fruit.infer.tasks',
  'properties.bootstrap.servers' = '${kafka.bootstrap}',
  'format' = 'json'
);

-- MVP pass-through (add dedup later if needed)
INSERT INTO infer_tasks
SELECT bucket, key, ts
FROM imagery_new;
