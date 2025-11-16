
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import threading, os, time, psutil

# Optional torch + NVML for GPU monitoring
try:
    import torch
except ImportError:
    torch = None
try:
    from pynvml import (
        nvmlInit, nvmlDeviceGetHandleByIndex,
        nvmlDeviceGetUtilizationRates, nvmlDeviceGetMemoryInfo,
        nvmlDeviceGetCount
    )
    nvmlInit()
except Exception:
    nvmlDeviceGetCount = None


# ─────────────────────────────────────────────
# Shared Prometheus metrics
# ─────────────────────────────────────────────
INFER_REQUESTS = Counter(
    "inference_requests_total",
    "Total inference requests",
    ["service"]
)

INFER_ERRORS = Counter(
    "inference_errors_total",
    "Total inference errors",
    ["service"]
)

INFER_LATENCY = Histogram(
    "inference_latency_seconds",
    "Inference latency in seconds",
    ["service"]
)

MODEL_LOAD_SEC = Gauge(
    "model_load_seconds",
    "Model load time in seconds",
    ["service"]
)

# ─────────────────────────────────────────────
# System / GPU metrics
# ─────────────────────────────────────────────
CPU_USAGE_PERCENT = Gauge(
    "system_cpu_usage_percent",
    "System CPU utilization percentage",
)

PROC_CPU_PERCENT = Gauge(
    "process_cpu_usage_percent",
    "This process's CPU utilization percentage",
)

PROC_MEM_MB = Gauge(
    "process_memory_megabytes",
    "This process's resident memory (MB)",
)

GPU_USAGE_PERCENT = Gauge(
    "gpu_utilization_percent",
    "GPU utilization percentage per device",
    ["gpu_id"]
)

GPU_MEM_USED_MB = Gauge(
    "gpu_memory_used_megabytes",
    "GPU memory used (MB per device)",
    ["gpu_id"]
)

GPU_MEM_TOTAL_MB = Gauge(
    "gpu_memory_total_megabytes",
    "GPU total memory (MB per device)",
    ["gpu_id"]
)


# ─────────────────────────────────────────────
# Background collector for system metrics
# ─────────────────────────────────────────────
def _collect_system_metrics(interval: int = 5):
    """Continuously update CPU, memory, GPU metrics."""
    process = psutil.Process(os.getpid())
    while True:
        try:
            # System + process CPU/mem
            CPU_USAGE_PERCENT.set(psutil.cpu_percent(interval=None))
            PROC_CPU_PERCENT.set(process.cpu_percent(interval=None))
            PROC_MEM_MB.set(process.memory_info().rss / (1024 * 1024))

            # GPU metrics
            if torch and torch.cuda.is_available():
                num_gpus = torch.cuda.device_count()
                for i in range(num_gpus):
                    used = torch.cuda.memory_allocated(i) / (1024 * 1024)
                    total = torch.cuda.get_device_properties(i).total_memory / (1024 * 1024)
                    GPU_MEM_USED_MB.labels(gpu_id=str(i)).set(used)
                    GPU_MEM_TOTAL_MB.labels(gpu_id=str(i)).set(total)
                    GPU_USAGE_PERCENT.labels(gpu_id=str(i)).set((used / total) * 100)
            elif nvmlDeviceGetCount:
                for i in range(nvmlDeviceGetCount()):
                    handle = nvmlDeviceGetHandleByIndex(i)
                    util = nvmlDeviceGetUtilizationRates(handle)
                    mem = nvmlDeviceGetMemoryInfo(handle)
                    GPU_USAGE_PERCENT.labels(gpu_id=str(i)).set(util.gpu)
                    GPU_MEM_USED_MB.labels(gpu_id=str(i)).set(mem.used / (1024 * 1024))
                    GPU_MEM_TOTAL_MB.labels(gpu_id=str(i)).set(mem.total / (1024 * 1024))
            else:
                # No GPU — clear gauges
                GPU_USAGE_PERCENT.clear()
                GPU_MEM_USED_MB.clear()
                GPU_MEM_TOTAL_MB.clear()

        except Exception as e:
            print(f"[Metrics] ⚠️ System metrics update failed: {e}")

        time.sleep(interval)


# ─────────────────────────────────────────────
# Helper to start background /metrics server
# ─────────────────────────────────────────────
def start_metrics_server():
    """Start Prometheus metrics endpoint and background collector."""
    port = int(os.getenv("METRICS_PORT", "8000"))
    threading.Thread(target=start_http_server, args=(port,), daemon=True).start()
    threading.Thread(target=_collect_system_metrics, daemon=True).start()
    print(f"[Metrics] 📊 Prometheus metrics exposed on :{port}/metrics")







