# Latency & Throughput Report

**Setup:** Publisher → Mosquitto → mqtt_ingest → MinIO (S3 API); ~3,000 images, ~1 MiB each.

## Run A — Single PUT (no multipart)
- **count:** 813
- **latency (ms):** p50=4884.00, p95=8489.00, p99=8753.00, avg=4717.61
- **throughput:** 74.19 imgs/s (~4451 imgs/min)
- **data volume:** 1240.83 MB total (113.22 MB/s)

## Run B — Multipart PUT
- **count:** 1609
- **latency (ms):** p50=5069.00, p95=8823.00, p99=9172.00, avg=4939.08
- **throughput:** 40.34 imgs/s (~2420 imgs/min)
- **data volume:** 2454.98 MB total (61.55 MB/s)

## Run C — Current run (latest)
- **count:** 3000 (S3) / 3000 (CSV)
- **elapsed (publisher):** 49.59 s
- **throughput:** 60.5 imgs/s (~3,630 imgs/min)
- **broker logs:** no drops/disconnects observed
- **latency quantiles:** not computed here (CSV available with 3,000 rows)
- **data rate, assuming 1 MiB/image:** ~60.5 MB/s (~3.0 GB total)
- **data rate, assuming 1.53 MB/image (as in A/B):** ~92.6 MB/s (~4.59 GB total)

## Comparison
- **A vs B:** Δp95 = +334 ms (+3.9%), Δthroughput = −33.85 imgs/s (−45.6%), ΔMB/s = −51.68 MB/s
- **C vs A:** throughput −18.5% (60.5 vs 74.19 imgs/s)
- **C vs B:** throughput +50% (60.5 vs 40.34 imgs/s)

## Metric Glossary
- **count:** number of images included in the metric.
- **latency (ms):** end-to-end time from publisher timestamp in the MQTT topic to successful object upload to S3/MinIO, measured in milliseconds.
- **latency quantiles (p50/p95/p99):** the 50th/95th/99th percentile of latencies; e.g., p95 means 95% of images were faster than this value.
- **avg:** arithmetic mean latency across all images in the run.
- **throughput (imgs/s, imgs/min):** how many images are processed per second (or minute), computed as count ÷ elapsed time.
- **data volume (MB total):** total payload bytes uploaded, converted to megabytes.
- **data rate (MB/s):** data volume ÷ elapsed time.
- **elapsed (publisher):** wall-clock time the publisher spent sending the batch; it approximates but is not identical to end-to-end ingest time.
- **Single PUT vs Multipart:** Single PUT uploads the whole object in one request; Multipart splits large objects into parts and uploads in parallel—useful for very large files or high-latency links, but it can add overhead for ~1 MiB objects.

## Notes
- Current run quantiles can be computed from `out/latency.csv` (3,000 rows) later if needed.
