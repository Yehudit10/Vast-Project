# tests/test_dsl.py
import json
import pytest
from dataclasses import FrozenInstanceError
from dsl import Query, Field, Literal, Predicate, Operator, parse_predicate


# ---------- Helpers ----------

def plan_of(expr):
    """Convenience: serialize an Expr (Predicate/Field/Literal) to its plan dict."""
    return expr.to_plan()


# ---------- Basic construction ----------

def test_field_to_plan():
    f = Field("ts")
    assert plan_of(f) == {"field": "ts"}

def test_literal_to_plan():
    lit = Literal(42)
    assert plan_of(lit) == {"literal": 42}


# ---------- Operator building (Python expressions) ----------

@pytest.mark.parametrize(
    "op,build,expect_op",
    [
        (Operator.GT,  lambda f: f > 5,  ">"),
        (Operator.LT,  lambda f: f < 5,  "<"),
        (Operator.GE,  lambda f: f >= 5, ">="),
        (Operator.LE,  lambda f: f <= 5, "<="),
        (Operator.EQ,  lambda f: f == 5, "=="),
        (Operator.NE,  lambda f: f != 5, "!="),
    ],
)
def test_field_op_literal(op, build, expect_op):
    p = build(Field("ts"))
    assert isinstance(p, Predicate)
    assert p.op == op
    assert plan_of(p) == {
        "op": expect_op,
        "lhs": {"field": "ts"},
        "rhs": {"literal": 5},
    }


def test_reversed_comparison_coerces_correctly():
    # 5 < Field("ts") should become Field("ts") > 5 (via Field.__gt__)
    p1 = Field("ts") > 5
    p2 = 5 < Field("ts")     # uses reflected logic via Python's fallback to other.__gt__
    assert plan_of(p1) == plan_of(p2)





# ---------- Parsing string predicates ----------

@pytest.mark.parametrize(
    "expr,expect",
    [
        ("ts > 100",        {"op": ">",  "lhs": {"field": "ts"}, "rhs": {"literal": 100}}),
        ("ts >= 5",         {"op": ">=", "lhs": {"field": "ts"}, "rhs": {"literal": 5}}),
        ("ts <= 5",         {"op": "<=", "lhs": {"field": "ts"}, "rhs": {"literal": 5}}),
        ("ts == 5",         {"op": "==", "lhs": {"field": "ts"}, "rhs": {"literal": 5}}),
        ("ts != 5",         {"op": "!=", "lhs": {"field": "ts"}, "rhs": {"literal": 5}}),
        ("ts =  5",         {"op": "==", "lhs": {"field": "ts"}, "rhs": {"literal": 5}}),  # '=' normalized
        ("name == 'A'",     {"op": "==", "lhs": {"field": "name"}, "rhs": {"literal": "A"}}),
        ('name == "B"',     {"op": "==", "lhs": {"field": "name"}, "rhs": {"literal": "B"}}),
        ("t.col >= 3.14",   {"op": ">=", "lhs": {"field": "t.col"}, "rhs": {"literal": 3.14}}),
        ("ts > -5",         {"op": ">",  "lhs": {"field": "ts"}, "rhs": {"literal": -5}}),
        ("ts >= -3.5",      {"op": ">=", "lhs": {"field": "ts"}, "rhs": {"literal": -3.5}}),
        ("ts<'2024-01-01T00:00:00Z'", {"op": "<", "lhs": {"field": "ts"}, "rhs": {"literal": "2024-01-01T00:00:00Z"}}),
    ],
)
def test_parse_predicate_happy(expr, expect):
    p = parse_predicate(expr)
    assert plan_of(p) == expect


def test_parse_predicate_handles_escaped_quotes_and_newlines():
    p1 = parse_predicate(r'name == "a\nb"')
    p2 = parse_predicate(r"name == 'a\nb'")
    assert plan_of(p1)["rhs"]["literal"] == "a\nb"
    assert plan_of(p2)["rhs"]["literal"] == "a\nb"


def test_parse_predicate_accepts_non_identifier_lhs_as_literal():
    # LHS that is not a valid field (e.g., starts with digit) becomes a literal string
    p = parse_predicate("123abc == 'x'")
    assert plan_of(p) == {
        "op": "==",
        "lhs": {"literal": "123abc"},
        "rhs": {"literal": "x"},
    }


def test_parse_predicate_rejects_invalid_syntax():
    with pytest.raises(ValueError):
        parse_predicate("ts >> 5")     # invalid operator
    with pytest.raises(ValueError):
        parse_predicate("ts >")        # missing rhs
    with pytest.raises(ValueError):
        parse_predicate("> 5")         # missing lhs
    with pytest.raises(ValueError):
        parse_predicate("ts 5")        # missing operator
    with pytest.raises(ValueError):
        parse_predicate("")            # empty


# ---------- Query builder behavior ----------

def test_query_select_and_where_with_str_and_expr_and_json_shape():
    q = (
        Query()
        .select("sensor", "ts", "value")
        .where("ts >= 5")            # string predicate
        .where(Field("sensor") == "A")  # expr predicate
    )
    d = q.to_plan()
    assert "ops" in d and isinstance(d["ops"], list)
    assert d["ops"][0] == {"op": "select", "fields": ["sensor", "ts", "value"]}
    assert d["ops"][1]["op"] == "filter"
    assert d["ops"][2]["op"] == "filter"

    # JSON is valid and stable
    js = q.to_json(pretty=True)
    assert isinstance(js, str)
    # round-trip into dict for sanity
    assert json.loads(q.to_json()) == d


def test_query_clone_is_independent():
    q1 = Query().select("sensor")
    q2 = q1.clone().where("ts > 5")
    # q1 unchanged; q2 has filter
    assert len(q1.to_plan()["ops"]) == 1
    assert len(q2.to_plan()["ops"]) == 2


def test_query_reset_clears_ops():
    q = Query().select("a").where("a == 1")
    assert len(q.to_plan()["ops"]) == 2
    q.reset()
    assert q.to_plan()["ops"] == []


def test_query_where_rejects_non_str_non_expr():
    with pytest.raises(ValueError):
        Query().where(123)  # not str and not Expr


def test_select_accepts_single_list_tuple_and_rejects_empty():
    q1 = Query().select(["a", "b"])
    assert q1.to_plan()["ops"][0] == {"op": "select", "fields": ["a", "b"]}

    q2 = Query().select(("x", "y"))
    assert q2.to_plan()["ops"][0] == {"op": "select", "fields": ["x", "y"]}

    with pytest.raises(ValueError):
        Query().select()


# ---------- Slots / immutability ergonomics ----------

def test_slots_on_field_and_literal_prevent_dyn_attrs():
    f = Field("ts")
    # Trying to create a new attribute on a slotted, frozen dataclass
    with pytest.raises((AttributeError, TypeError)):
        f.foo = 1  # No __dict__; new attrs disallowed

    # Trying to modify an existing frozen field
    with pytest.raises(FrozenInstanceError):
        f.name = "other"

    lit = Literal(7)
    with pytest.raises((AttributeError, TypeError)):
        lit.bar = 2

    with pytest.raises(FrozenInstanceError):
        lit.value = 8

def test_predicate_repr_is_helpful():
    p = Field("ts") > 5
    s = repr(p)
    assert "Predicate" in s and ">" in s and "ts" in s


# ---------- Operator precedence / longest match ----------

def test_operator_longest_match_parsing():
    # Ensure parser matches >= before >, <= before <
    p1 = parse_predicate("ts >= 10")
    p2 = parse_predicate("ts >  10")
    assert plan_of(p1)["op"] == ">="
    assert plan_of(p2)["op"] == ">"


# ---------- Whitespace robustness ----------

@pytest.mark.parametrize("expr", [
    "  ts>=5",
    "\tts   >=   5  ",
    "ts\t<=\t5",
    "name == 'a b c'",      # spaces inside quoted string
    'name == "a b c"',      # double quoted
])
def test_whitespace_and_spacing(expr):
    p = parse_predicate(expr)
    assert isinstance(p, Predicate)
