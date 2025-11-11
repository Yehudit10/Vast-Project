import os

# Kafka / topics
KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "kafka:9092")
SOURCE_TOPIC = os.getenv("SOURCE_TOPIC", "sound_new_sounds_connections") 
SINK_TOPIC = os.getenv("SINK_TOPIC", "")  # empty = print to stdout only
GROUP_ID = os.getenv("GROUP_ID", "flink-classifier-sounds")
KAFKA_START = os.getenv("KAFKA_START", "earliest")  # earliest|latest

# HTTP classifier
CLASSIFIER_HTTP_URL = os.getenv("CLASSIFIER_HTTP_URL", "http://sounds_classifier:8088/classify")
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "5.0"))
RETRIES_TOTAL = int(os.getenv("RETRIES_TOTAL", "3"))
BACKOFF_FACTOR = float(os.getenv("BACKOFF_FACTOR", "0.5"))

# Flink
DEFAULT_PARALLELISM = int(os.getenv("DEFAULT_PARALLELISM", "1"))
CHECKPOINT_MS = int(os.getenv("CHECKPOINT_MS", "10000"))  # 10s
DELIVERY_GUARANTEE = os.getenv("DELIVERY_GUARANTEE", "AT_LEAST_ONCE")  # AT_LEAST_ONCE|NONE
TRANSACTION_TIMEOUT_MS = os.getenv("TRANSACTION_TIMEOUT_MS", "600000")  # 10 min

# Optional default bucket to use when input only carries an object key
DEFAULT_BUCKET = os.getenv("DEFAULT_BUCKET", "sound")