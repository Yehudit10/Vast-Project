from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, Optional

# Lightweight in-memory contract store.
# Loads JSON contracts from a directory and provides case-insensitive lookup by table/name.
class ContractStore:
    # Initialize store with resolved base directory and empty index mapping.
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir).resolve()
        self._by_table: Dict[str, Dict[str, Any]] = {}

    # Compute lookup keys for a contract file: filename stem, schema title, and title suffix.
    def _index_keys(self, file_path: Path, schema: Dict[str, Any]) -> set[str]:
        keys = set()
        stem = file_path.stem.strip().lower()
        keys.add(stem)

        title = str(schema.get("title", "")).strip().lower()
        if title:
            keys.add(title)                     
            if "." in title:
                keys.add(title.split(".", 1)[1])
        return keys

    # Load all JSON contract files from base_dir into the in-memory index.
    # Creates the directory if missing and prints a short load summary.
    def load_all(self) -> None:
        self._by_table.clear()
        print(f"[contract-store] trying to load from: {self.base_dir}")
        self.base_dir.mkdir(parents=True, exist_ok=True)

        loaded_files = 0
        for p in self.base_dir.glob("*.json"):
            try:
                with p.open("r", encoding="utf-8") as f:
                    schema = json.load(f)
            except Exception as e:
                print(f"[contract-store] failed to load {p}: {e}")
                continue

            for key in self._index_keys(p, schema):
                self._by_table[key] = schema
            loaded_files += 1

        print(
            f"[contract-store] loaded_files={loaded_files} "
            f"mapped_keys={len(self._by_table)} "
            f"keys={sorted(self._by_table.keys())}"
        )

    # Return the contract dict for the given table/key (case-insensitive), or None if not found.
    def get(self, table: str) -> Optional[Dict[str, Any]]:
        return self._by_table.get(table.strip().lower())

    # Return True if a contract exists for the given table/key.
    def has(self, table: str) -> bool:
        return self.get(table) is not None
