#!/bin/bash
set -e

if [ "$1" = "jobmanager" ]; then
    echo ">>> Waiting for Kafka to be ready..."

    # נבדוק אם Kafka מגיב לפורט 9092
    while ! timeout 2 bash -c "echo > /dev/tcp/kafka/9092" 2>/dev/null; do
      echo "Kafka not ready yet. Waiting 5 seconds..."
      sleep 5
    done

    echo ">>> Kafka is ready. Starting Flink JobManager..."
    /opt/flink/bin/jobmanager.sh start-foreground &
    sleep 10
    echo ">>> Submitting Flink job..."
    flink run -py /opt/app/flink_job.py
    tail -f /dev/null

else
    echo ">>> Starting Flink TaskManager..."
    exec /opt/flink/bin/taskmanager.sh start-foreground
fi
