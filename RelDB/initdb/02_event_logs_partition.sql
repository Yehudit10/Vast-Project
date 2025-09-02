-- Ensures inserts into partitioned event_logs succeed without creating date partitions.
CREATE TABLE IF NOT EXISTS event_logs_default PARTITION OF event_logs DEFAULT;
