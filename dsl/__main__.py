"""
CLI demo: `python -m dsl`
"""
from . import Query, Field

def main() -> None:
    plan = (
        Query()
        .select("sensor")
        .where("ts == True")
        .where(Field("ts") == True)
        .to_json(pretty=True)
    )
    print(plan)

if __name__ == "__main__":
    main()