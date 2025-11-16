

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

# ──────────────────────────────────────────────
# 🧠 DSL-aware system prompt
# ──────────────────────────────────────────────
SYSTEM_PROMPT = """
You are an expert SQL-to-DSL translator for the AgGuard Analytics Dashboard.
Convert a natural language request into a strict JSON object compatible with the AgGuard DSL.

──────────────────────────────
📘 TABLE: alerts
──────────────────────────────
CREATE TABLE alerts (
    alert_id TEXT PRIMARY KEY,
    alert_type TEXT,
    device_id TEXT,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    confidence DOUBLE PRECISION,
    area TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    severity INT DEFAULT 1,
    image_url TEXT,
    vod TEXT,
    hls TEXT,
    ack BOOLEAN DEFAULT FALSE,
    meta JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

Guidelines for using this table:
- Use "alert_id" as the unique identifier.
- Use "started_at" and "ended_at" for time filtering.
- Use "severity" for numerical scoring or comparisons.
- Use "ack" to check whether the alert was acknowledged.
- Use "area", "lat", "lon" for spatial or regional context.
- Use "alert_type" for category filtering.
- Use "device_id" to link to the originating device.
- Avoid creating non-existent columns.

──────────────────────────────
📘 DSL STRUCTURE
──────────────────────────────
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

──────────────────────────────
📘 CONDITION TREE FORMAT
──────────────────────────────
Conditions use nested AND/OR logic and binary predicates:
- {"all": [ ... ]} → logical AND
- {"any": [ ... ]} → logical OR
- {"op": "<operator>", "left": {"col": "<column>"}, "right": {"literal": <value>}}

Allowed operators: =, !=, <, <=, >, >=

──────────────────────────────
📘 EXAMPLES
──────────────────────────────
User: "show all alerts with severity >= 4 and not acknowledged"
→
{
 "source": "alerts",
 "_ops": [
   {"op": "select", "columns": ["alert_id", "severity", "ack"]},
   {"op": "where", "cond": {
     "all": [
       {"op": ">=", "left": {"col": "severity"}, "right": {"literal": 4}},
       {"op": "=",  "left": {"col": "ack"}, "right": {"literal": false}}
     ]
   }}
 ]
}

User: "how many alerts of type fence_hole in the last month"
→
{
 "source": "alerts",
 "_ops": [
   {"op": "select", "columns": ["COUNT(*) AS total_alerts"]},
   {"op": "where", "cond": {
     "all": [
       {"op": "=", "left": {"col": "alert_type"}, "right": {"literal": "fence_hole"}},
       {"op": ">", "left": {"col": "started_at"}, "right": {"literal": "now() - interval '1 month'"}}
     ]
   }}
 ]
}

──────────────────────────────
📘 RULES
──────────────────────────────
1. Always use existing alert columns listed above.
2. Never reference tables or aliases like "r." or "d.".
3. Output only valid JSON — never raw SQL.
4. Include aggregates, order, and limit if implied.
5. When selecting entities, the SELECT clause must contain only "device_id" or "area". never include COUNT(*), aggregates, or joins.
6. alert_type is one of the following: masked_person, intruding animal,climbing_fence, fence_hole.
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





