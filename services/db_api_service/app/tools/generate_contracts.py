# tools/generate_contracts.py
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.exc import NoSuchTableError

from app.config import settings


CONTRACTS_DIR: Path = Path(settings.CONTRACTS_DIR)
ALLOWED: List[str] = list(settings.ALLOWED_TABLES)
DB_URL = os.environ.get("DATABASE_URL")

if not ALLOWED:
    raise RuntimeError("[contracts-gen] ERROR: No allowed tables defined in config.py")
if not DB_URL:
    raise RuntimeError("[contracts-gen] ERROR: DATABASE_URL not found in environment")


# Normalize a SQLAlchemy column type (or its string representation) to a canonical lowercase string
# used by subsequent type-mapping logic.
def _normalize_type_name(col_type: Any) -> str:
    """
    Convert SQLAlchemy/type string to a lowercase descriptor we can pattern-match on.
    """
    return str(col_type).lower()


# Map a database column type to a JSON Schema `type` and optional `format`.
# Returns a tuple (json_type, json_format_or_None).
def map_json_type_and_format(col_type: Any) -> Tuple[str, Optional[str]]:
    """
    Map a DB column type to (json_type, json_format?).
    - integer-like -> ("integer", None)
    - numeric/decimal/float -> ("number", None)
    - boolean -> ("boolean", None)
    - date -> ("string", "date")
    - time/timestamp/datetime -> ("string", "date-time")
    - default -> ("string", None)
    """
    t = _normalize_type_name(col_type)

    if "json" in t:
        return "object", None

    if any(k in t for k in ("int", "serial", "bigint", "smallint")):
        return "integer", None
    if any(k in t for k in ("float", "double", "numeric", "decimal", "real")):
        return "number", None
    if "bool" in t:
        return "boolean", None

    # Date/Time family
    if "timestamp" in t or "datetime" in t:
        return "string", "date-time"
    if "time" in t and "without time zone" in t:
        # DBs differ—treat bare "time" conservatively
        return "string", None
    if "date" in t:
        return "string", "date"

    # Fallback
    return "string", None


# Inspect the database for primary key constraint and return primary key column names.
# Returns an empty list if no PK could be determined.
def _infer_key_fields(ins: Inspector, table: str, schema: Optional[str] = None) -> List[str]:
    """
    Return primary key column names if available; empty list otherwise.
    """
    try:
        pk = ins.get_pk_constraint(table, schema=schema)
        cols = pk.get("constrained_columns") or []
        return [c for c in cols if isinstance(c, str)]
    except Exception:
        return []


# Build a JSON Schema (Draft 2020-12) for the given DB table by introspecting its columns.
# Adds helpful extensions (x-keyFields, x-sortable, x-queryable) and a legacy readOnly list.
def build_schema_for_table(ins: Inspector, table: str, schema: Optional[str] = None) -> Dict[str, Any]:
    """
    Build a JSON Schema (Draft 2020-12) for a DB table, enriched with:
      - "x-keyFields": primary key column names (if found)
      - "x-sortable": true (per property, defaults; can be edited later)
      - "x-queryable": true (per property, defaults; can be edited later)
      - "format": "date" / "date-time" where applicable
    Also exposes legacy root-level "readOnly" (list of column names) for compatibility.

    Raises:
        ValueError: if the table does not exist or cannot be inspected.
    """
    try:
        cols = ins.get_columns(table, schema=schema)  # List[dict]
    except NoSuchTableError as e:
        raise ValueError(f"table '{table}' not found in database") from e
    except Exception as e:
        raise ValueError(f"failed to inspect table '{table}': {e}") from e

    if not cols:
        raise ValueError(f"no columns returned for table '{table}'")

    props: Dict[str, Any] = {}
    required: List[str] = []
    read_only: List[str] = []

    # Per-column properties
    for c in cols:
        name = c["name"]
        json_type, json_format = map_json_type_and_format(c["type"])
        prop: Dict[str, Any] = {"type": json_type}

        if json_format:
            prop["format"] = json_format

        # schema-first hints (can be tightened manually later)
        prop["x-sortable"] = True
        prop["x-queryable"] = True

        props[name] = prop

        # required if DB says non-nullable (good initial hint)
        is_required = not c.get("nullable", True)
        autoinc = bool(c.get("autoincrement"))
        has_default = c.get("default") is not None
        server_default = c.get("server_default") is not None
        identity = bool(c.get("identity"))
        computed = bool(c.get("computed"))
        generated = bool(c.get("generated"))

        is_read_only = autoinc or has_default or server_default or identity or computed or generated
        if is_read_only:
            read_only.append(name)        
        if is_required and not is_read_only:
            required.append(name)

    # Key fields (primary key) for returning="keys"
    key_fields = _infer_key_fields(ins, table, schema=schema)

    schema_json: Dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": table,
        "type": "object",
        "properties": props,
        "required": required or [],
        # compatibility with your existing usage:
        "readOnly": read_only or [],
    }

    if key_fields:
        schema_json["x-keyFields"] = key_fields

    return schema_json


# Main entrypoint: generate JSON contract files for allowed tables by introspecting the DB.
# Writes one {table}.json file per allowed table into CONTRACTS_DIR.
def main() -> None:
    outdir = CONTRACTS_DIR
    outdir.mkdir(parents=True, exist_ok=True)

    eng = create_engine(DB_URL)
    ins = inspect(eng)

    generated_files: List[str] = []
    for table in ALLOWED:
        try:
            schema_json = build_schema_for_table(ins, table)
        except ValueError as e:
            # Log an error for this specific table, but do not abort the whole process
            print(f"[contracts-gen][ERROR] {e}; skipping '{table}'")
            continue
        except Exception as e:
            # Report any unexpected failure and continue with the next table
            print(f"[contracts-gen][ERROR] unexpected error for '{table}': {e}; skipping")
            continue

        out_path = outdir / f"{table}.json"
        out_path.write_text(
            json.dumps(schema_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        generated_files.append(out_path.name)

    print(f"[contracts-gen] generated {len(generated_files)} files: {generated_files}")
    if not generated_files:
        sys.stderr.write("[contracts-gen] ERROR: no contracts were generated\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
