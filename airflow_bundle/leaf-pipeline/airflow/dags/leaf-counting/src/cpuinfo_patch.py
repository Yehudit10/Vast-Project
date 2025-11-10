# Runs at import time. Neutralizes py-cpuinfo and Ultralytics CPU probe (no subprocess).
try:
    import cpuinfo as _cpuinfo
    _cpuinfo.get_cpu_info = lambda: {"brand_raw": "unknown-cpu", "count": 0}
    _cpuinfo.get_cpu_info_json = lambda: "{}"
except Exception:
    pass

try:
    from ultralytics.utils import torch_utils as _tu
    _tu.get_cpu_info = lambda: "unknown-cpu"
except Exception:
    pass
