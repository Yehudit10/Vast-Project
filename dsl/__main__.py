"""
CLI demo: `python -m dsl`
"""
from . import Query, Field

def main() -> None:
    plan = (
        Query()
        .select("sensor")
        .where("ts < 'kl'")
        .where(Field("ts") < 'kl')
        .to_json(pretty=True)
    )
    print(plan)

if __name__ == "__main__":
    main()