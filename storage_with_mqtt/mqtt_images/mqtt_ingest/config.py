# mqtt_ingest/config.py
from dataclasses import dataclass
from pathlib import Path
import os, typing as t

try:
    import yaml 
except Exception:
    yaml = None

@dataclass(frozen=True)
class Config:
    # ingest
    MP_THRESHOLD: int = 5 * 1024 * 1024
    PART_SIZE: int = 5 * 1024 * 1024
    MAX_CONC: int = 32
    MQTT_PORT: int = 1883
    INGEST_WORKERS: int = 8

    # publisher
    LIMIT: int = 0              
    PUBLISH_QOS: int = 2
    PUBLISH_DELAY_MS: int = 10

def _coerce(v, to_type):
    if to_type is int:   return int(v)
    if to_type is float: return float(v)
    if to_type is bool:  return str(v).lower() in ("1","true","yes","on")
    return v


_ENV_ALIASES = {
    "MP_THRESHOLD":       ["MULTIPART_THRESHOLD_BYTES"],
    "PART_SIZE":          ["PART_SIZE_BYTES"],
    "MAX_CONC":           ["MULTIPART_MAX_CONCURRENCY"],
    "MQTT_PORT":          ["MQTT_PORT"],
    "INGEST_WORKERS":     ["INGEST_WORKERS"],
    "LIMIT":              ["LIMIT"],
    "PUBLISH_QOS":        ["MQTT_QOS"],
    "PUBLISH_DELAY_MS":   ["PUBLISH_DELAY_MS"],
}

def load_config(path: t.Optional[t.Union[str, Path]] = None) -> Config:
    base = Config()

    data = {}
    root = Path(__file__).resolve().parents[1]
    if path is None:
        for name in ("config.yaml", "config.yml"):
            p = root / name
            if p.exists():
                path = p
                break
    if path and yaml:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


    env = os.environ
    out = {}
    for f in base.__dataclass_fields__.values():
        key = f.name
        val = getattr(base, key)
        if key in data:
            try: val = _coerce(data[key], f.type)
            except Exception: pass
        for alias in _ENV_ALIASES.get(key, []):
            if alias in env:
                try: val = _coerce(env[alias], f.type)
                except Exception: pass
        out[key] = val
    return Config(**out)

cfg = load_config()




