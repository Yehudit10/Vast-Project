"""
CLI demo: `python -m dsl`
"""
from . import Query, Field

def main() -> None:
    plan = (
        Query()
        .select("sensor")
        .where("ts == -0.5")
        .where(Field("ts") > Field("last_ts"))
        .to_json(pretty=True)
    )
    print(plan)

if __name__ == "__main__":
    main()