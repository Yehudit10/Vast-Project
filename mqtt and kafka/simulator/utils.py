from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
import pandas as pd


def positive_float(x: str) -> float:
    """argparse type: positive float."""
    try:
        value = float(x)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a number")
    if value <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return value


def load_data(file_path: Path) -> pd.DataFrame:
    """Load CSV or Parquet."""
    if file_path.is_dir():
        raise ValueError(f"Path points to a directory, not a file: {file_path}")
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    name = file_path.name.lower()
    if name.endswith((".parquet", ".parq", ".pq")):
        try:
            return pd.read_parquet(file_path)
        except Exception as e:
            raise RuntimeError("Failed to read parquet. Install 'pyarrow' or 'fastparquet'.") from e

    if name.endswith(".csv"):
        return pd.read_csv(file_path)

    raise ValueError(f"Unsupported file type: {file_path.name} (expected .csv or .parquet)")


def iterate_records(df: pd.DataFrame) -> Iterator[Dict[str, Any]]:
    """Yield the dataframe rows as dicts."""
    cols = list(df.columns)
    for row in df.itertuples(index=False, name=None):
        yield dict(zip(cols, row))


def percentile(vals: List[float], p: float) -> Optional[float]:
    """Small helper for p-th percentile (0..100)."""
    if not vals:
        return None
    vals_sorted = sorted(vals)
    k = (len(vals_sorted) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(vals_sorted) - 1)
    if f == c:
        return vals_sorted[f]
    d0 = vals_sorted[f] * (c - k)
    d1 = vals_sorted[c] * (k - f)
    return d0 + d1


def fmt_latency(x: Optional[float]) -> str:
    """Format seconds -> 'X.Yms' or 'n/a'."""
    return f"{x*1000:.1f}ms" if x is not None else "n/a"


def extract_sid_from_headers(headers: Optional[List[Tuple[str, bytes]]]) -> Optional[str]:
    """Extract 'sid' header from Kafka message headers."""
    if not headers:
        return None
    for k, v in headers:
        if k == "sid":
            try:
                return v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
            except Exception:
                return str(v)
    return None
