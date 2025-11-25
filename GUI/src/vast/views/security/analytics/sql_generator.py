

# #!/usr/bin/env python3
# # -*- coding: utf-8 -*-

"""
Free-text → DSL → validated SQL generator for AgGuard analytics dashboard.
Uses your internal DSL schema:
{
  "source": "alerts",
  "_ops": [
    {"op": "select", "columns": ["..."]},
    {"op": "where", "cond": { ... }},
    {"op": "group_by", "columns": ["..."]},
    {"op": "having", "cond": { ... }},
    {"op": "order_by", "columns": ["..."], "directions": ["ASC"|"DESC"]},
    {"op": "limit", "limit": 50}
  ]
}
"""

import os, json
from openai import OpenAI
from dotenv import load_dotenv
from jsonschema import validate, ValidationError

# ──────────────────────────────────────────────
# 🔑 Initialize client
# ──────────────────────────────────────────────
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ──────────────────────────────────────────────
# 🧩 DSL schema (the one your DSL actually uses)
# ──────────────────────────────────────────────
QUERY_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "DSLQueryPlan",
    "type": "object",
    "properties": {
        "source": {"type": "string"},
        "_ops": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "op": {
                        "type": "string",
                        "enum": [
                            "select", "where", "group_by",
                            "having", "order_by", "limit", "offset"
                        ]
                    },
                    "columns": {
                        "type": "array",
                        "items": {
                            "type": "string",
                          
                        },
                        "minItems": 1,
                        "maxItems": 2,
                        "uniqueItems": True
                    },
                    "cond": {"type": "object"},
                    "directions": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["ASC", "DESC"]}
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                    "offset": {"type": "integer", "minimum": 0}
                },
                "required": ["op"],
                "additionalProperties": True
            }
        }
    },
    "required": ["source", "_ops"],
    "additionalProperties": False
}



SYSTEM_PROMPT = """
You are an expert DSL generator for the AgGuard Analytics Dashboard.
Your task: convert a natural-language request into a strict JSON object
compatible with the AgGuard DSL (no SQL, JSON only).

────────────────────────
TABLE: alerts
────────────────────────
CREATE TABLE alerts (
    alert_id   TEXT PRIMARY KEY,
    alert_type TEXT,
    device_id  TEXT,
    started_at TIMESTAMPTZ,
    ended_at   TIMESTAMPTZ,
    confidence DOUBLE PRECISION,
    area       TEXT,
    lat        DOUBLE PRECISION,
    lon        DOUBLE PRECISION,
    severity   INT DEFAULT 1,
    image_url  TEXT,
    vod        TEXT,
    hls        TEXT,
    ack        BOOLEAN DEFAULT FALSE,
    meta       JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

Use only these columns. Do not invent new columns or tables.

────────────────────────
DSL STRUCTURE
────────────────────────
The output MUST follow this shape:

{
  "source": "alerts",
  "_ops": [
    {"op": "select",   "columns": ["..."]},
    {"op": "where",    "cond": { ... }},
    {"op": "group_by", "columns": ["..."]},
    {"op": "having",   "cond": { ... }},
    {"op": "order_by", "columns": ["..."], "directions": ["ASC"|"DESC"]},
    {"op": "limit",    "limit": 50},
    {"op": "offset",   "offset": 0}
  ]
}

Rules for fields:
- "source" must always be "alerts".
- "_ops" is an ordered array of operations.
- "op" is one of: "select", "where", "group_by", "having", "order_by", "limit", "offset".
- "columns" is ALWAYS an array of strings (1–2 items, no duplicates).
  - For functions/expressions in SELECT/GROUP_BY/ORDER_BY, write SQL text strings, e.g.:
    "COUNT(alert_id)", "COUNT(*)", "DATE_TRUNC('month', started_at)".
  - Never put {"func": ...} objects inside "columns".
- "directions" aligns with "columns" and contains only "ASC" or "DESC".
- "limit" is 1–500; "offset" is >= 0.

SELECT rules (very important):
- When selecting entities, SELECT must contain only:
  - ["device_id"], or
  - ["area"].
- Never put aggregates or functions into SELECT (no COUNT(*), SUM, etc. in SELECT).

────────────────────────
CONDITION TREE FORMAT
────────────────────────
Conditions ("cond") are boolean trees:

1. Logical AND:
   { "all": [ <cond>, ... ] }

2. Logical OR:
   { "any": [ <cond>, ... ] }

3. Predicate:
   { "op": "<operator>", "left": <expr>, "right": <expr> }

Allowed operators: "=", "!=", "<", "<=", ">", ">=".

In conditions, an <expr> may be:
- {"col": "<column_name>"}
- {"literal": <value>}
- {"func": "<function_name>", "args": [ <expr>, ... ]}

Notes:
- Use {"col": "..."} only with real columns from the alerts table.
- Use {"literal": ...} for numbers, strings, booleans, and time expressions like:
  "now() - interval '1 month'".
- Use {"func": ...} only in WHERE/HAVING, not in SELECT/GROUP_BY/ORDER_BY.
- Do NOT use window functions or OVER() (no row_number, no "max(avg) over ()").

────────────────────────
EXAMPLES
────────────────────────

Example 1
User: "show devices with fence_hole alerts from the last month"
→
{
  "source": "alerts",
  "_ops": [
    {"op": "select", "columns": ["device_id"]},
    {
      "op": "where",
      "cond": {
        "all": [
          {
            "op": "=",
            "left":  {"col": "alert_type"},
            "right": {"literal": "fence_hole"}
          },
          {
            "op": ">",
            "left":  {"col": "started_at"},
            "right": {"literal": "now() - interval '1 month'"}
          }
        ]
      }
    },
    {"op": "group_by", "columns": ["device_id"]}
  ]
}

────────────────────────

Example 2
User: "show areas with more than 3 severe alerts (severity > 3) in the last month"
→
{
  "source": "alerts",
  "_ops": [
    {"op": "select", "columns": ["area"]},
    {
      "op": "where",
      "cond": {
        "all": [
          {
            "op": ">",
            "left":  {"col": "severity"},
            "right": {"literal": 3}
          },
          {
            "op": ">",
            "left":  {"col": "started_at"},
            "right": {"literal": "now() - interval '1 month'"}
          }
        ]
      }
    },
    {"op": "group_by", "columns": ["area"]},
    {
      "op": "having",
      "cond": {
        "op": ">",
        "left":  {"func": "count", "args": [ {"literal": "*"} ]},
        "right": {"literal": 3}
      }
    }
  ]
}


────────────────────────

Example 4
User: "top 5 devices with highest number of climbing_fence alerts"
→
{
  "source": "alerts",
  "_ops": [
    {"op": "select", "columns": ["device_id"]},
    {
      "op": "where",
      "cond": {
        "op": "=",
        "left":  {"col": "alert_type"},
        "right": {"literal": "climbing_fence"}
      }
    },
    {"op": "group_by", "columns": ["device_id"]},
    {
      "op": "order_by",
      "columns": ["COUNT(alert_id)"],
      "directions": ["DESC"]
    },
    {"op": "limit", "limit": 5}
  ]
}


────────────────────────

Example 5
User: "list devices with unacknowledged masked_person alerts in the last week, newest first, limit 20"
→
{
  "source": "alerts",
  "_ops": [
    {"op": "select", "columns": ["device_id"]},
    {
      "op": "where",
      "cond": {
        "all": [
          {
            "op": "=",
            "left":  {"col": "alert_type"},
            "right": {"literal": "masked_person"}
          },
          {
            "op": "=",
            "left":  {"col": "ack"},
            "right": {"literal": false}
          },
          {
            "op": ">",
            "left":  {"col": "started_at"},
            "right": {"literal": "now() - interval '1 week'"}
          }
        ]
      }
    },
    {
      "op": "order_by",
      "columns": ["started_at"],
      "directions": ["DESC"]
    },
    {"op": "limit", "limit": 20}
  ]
}

────────────────────────
GLOBAL RULES
────────────────────────
1. Always use only the columns of the alerts table.
2. Never reference table aliases like "a." or "r." and never reference other tables.
3. Output only VALID JSON, with "source" and "_ops" at the top level.
4. Use WHERE for row filters, GROUP_BY for aggregations, HAVING for aggregate conditions.
5. For queries that rank entities by number of alerts (e.g. "top", "most", "highest", "least", "fewest", "lowest"):
   - Use GROUP_BY on the entity ("device_id" or "area").
   - Use ORDER_BY with "COUNT(alert_id)" or "COUNT(*)".
     • For "top / most / highest": use direction "DESC".
     • For "least / fewest / lowest": use direction "ASC".
   - Use LIMIT N (or LIMIT 1 if the user asks for a single best/worst entity).
6. alert_type is one of: "masked_person", "intruding animal", "climbing_fence", "fence_hole".
"""


# ──────────────────────────────────────────────
# 🧮 Core generator
# ──────────────────────────────────────────────
from src.vast.dsl.ir import Plan
from src.vast.dsl.builder import SQLBuilder
from src.vast.dsl.dialects import PostgresDialect

def generate_sql_from_prompt(prompt: str) -> tuple[str | None, list]:
    """Convert natural language → DSL JSON → validated SQL."""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )

    obj = json.loads(response.choices[0].message.content)
    print(obj)
    try:
        validate(instance=obj, schema=QUERY_SCHEMA)
    except ValidationError as e:
        print("❌ Validation error:", e.message)
        return None, []

    # Compile directly with your DSL
    plan = Plan.from_dict(obj)
    print(plan)
    sql, params = SQLBuilder(PostgresDialect("named")).compile(plan)
    print(sql,params)
    return sql, params


# ──────────────────────────────────────────────
# 🧪 Example usage
# ──────────────────────────────────────────────
if __name__ == "__main__":
    user_text = "give me the region that had most alerts last month"
    print(f"\n🗣️ User: {user_text}\n")

    sql, params = generate_sql_from_prompt(user_text)
    if sql:
        print("✅ SQL:\n", sql)
        print("🧩 Params:", params)
    else:
        print("❌ Could not generate SQL.")














