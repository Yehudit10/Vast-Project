from prometheus_client import Counter, Histogram

METRICS = {
    "alerts_sent_total": Counter("alerts_sent_total", "Total alerts sent", ["decision"]),
    "kafka_publish_errors_total": Counter("kafka_publish_errors_total", "Kafka publish errors", ["reason"]),
    "inference_latency_ms": Histogram(
        "inference_latency_ms",
        "Inference latency (ms)",
        buckets=(5,10,20,50,100,200,500,1000,2000)
    ),
}
