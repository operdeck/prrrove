"""Tests for the exact-cover engine and both puzzle compilers.

The Murdoku cases check against the published solution and candidate lists in
the documents in prrrdokus/, so a wrong board transcription fails here rather than quietly
solving some other puzzle.
"""

import re
from pathlib import Path

import pytest

from csp import bruteforce, calcudoku, cli, murdoku, report, sudoku
from csp.core import (
    DEFAULT_RULES,
    Contradiction,
    Kind,
    Model,
    Rule,
    Solver,
    follow_chain,
    rule_chains,
    rule_cover,
    rule_relations,
    rule_single,
    rule_subsumption,
    rule_what_if,
)
from csp.puzzlefile import load_board, parse_square

EXAMPLES = Path(__file__).parent.parent / "examples"


# --- engine ---------------------------------------------------------------


def test_assign_rules_out_siblings():
    m = Model()
    a, b, c = (m.literal("x", v) for v in (1, 2, 3))
    m.constrain("x picks one", Kind.EXACTLY_ONE, [a, b, c], defines="x")
    m.assign(a, "test", "chosen")
    assert m.is_true(a) and m.is_false(b) and m.is_false(c)
    assert m.chosen("x") == 1


def test_single_fires_on_last_option():
    m = Model()
    a, b = m.literal("x", 1), m.literal("x", 2)
    m.constrain("x picks one", Kind.EXACTLY_ONE, [a, b], defines="x")
    m.eliminate(a, "test", "ruled out")
    assert rule_single(m) is True
    assert m.chosen("x") == 2


def test_at_most_one_does_not_force():
    """The distinction the old engine got wrong: AT_MOST_ONE never forces."""
    m = Model()
    a, b = m.literal("x", 1), m.literal("y", 1)
    m.constrain("square shared", Kind.AT_MOST_ONE, [a, b])
    m.eliminate(a, "test", "ruled out")
    assert rule_single(m) is False
    assert not m.is_true(b)


def test_exhausted_exactly_one_is_a_contradiction():
    m = Model()
    a = m.literal("x", 1)
    m.constrain("x picks one", Kind.EXACTLY_ONE, [a], defines="x")
    m.eliminate(a, "test", "ruled out")
    with pytest.raises(Contradiction):
        m.check()


def test_subsumption_prunes_the_wider_constraint():
    m = Model()
    inner = [m.literal("p", 1), m.literal("p", 2)]
    extra = [m.literal("q", 3), m.literal("q", 4)]
    m.constrain("narrow", Kind.EXACTLY_ONE, inner)
    m.constrain("wide", Kind.EXACTLY_ONE, inner + extra)
    assert rule_subsumption(m) is True
    assert all(m.is_false(lit) for lit in extra)
    assert not any(m.is_false(lit) for lit in inner)


def _variable(m: Model, var: str, values) -> list[int]:
    """Declare `var` with the given domain; return its literals."""
    lits = [m.literal(var, v) for v in values]
    m.constrain(f"{var} picks one", Kind.EXACTLY_ONE, lits, defines=var)
    return lits


def _naked_pair_model():
    """Cells x, y take {1, 2}; z takes 1-4, w {3, 4}; each digit used once."""
    m = Model()
    allowed = {"x": (1, 2), "y": (1, 2), "z": (1, 2, 3, 4), "w": (3, 4)}
    for var, values in allowed.items():
        _variable(m, var, values)
    for d in (1, 2, 3, 4):
        holders = [m.literal(var, d) for var, values in allowed.items() if d in values]
        m.constrain(f"{d} used once", Kind.EXACTLY_ONE, holders)
    return m, {(var, d): m.literal(var, d) for var, values in allowed.items() for d in values}


def test_cover2_is_a_naked_pair():
    m, lit = _naked_pair_model()
    assert rule_subsumption(m) is False
    assert rule_cover(2)(m) is True
    assert m.is_false(lit["z", 1]) and m.is_false(lit["z", 2])
    assert not m.is_false(lit["z", 3]) and not m.is_false(lit["z", 4])


def test_cover_needs_disjoint_anchors():
    """A1 and A2 share their literals, so they place one truth, not two."""
    m = Model()
    a, b, c = m.literal("p", 1), m.literal("p", 2), m.literal("q", 1)
    m.constrain("A1", Kind.EXACTLY_ONE, [a, b])
    m.constrain("A2", Kind.EXACTLY_ONE, [a, b])
    m.constrain("B", Kind.AT_MOST_ONE, [a, c])
    m.constrain("C", Kind.AT_MOST_ONE, [b])
    assert rule_cover(2)(m) is False
    assert not m.is_false(c)


def test_three_way_relation_needs_a_supporting_combination():
    m = Model()
    for var in "abc":
        _variable(m, var, (1, 2, 3))
    m.relate("a is the sum", "abc", lambda a, b, c: a == b + c)
    while rule_relations(m):
        pass
    assert [m.value_of(lit) for lit in m.options("a")] == [2, 3]
    assert [m.value_of(lit) for lit in m.options("b")] == [1, 2]


def test_clone_leaves_the_original_untouched():
    m = Model()
    a, b = _variable(m, "x", (1, 2))
    twin = m.clone()
    twin.assign(a, "test", "chosen")
    assert twin.is_false(b) and not m.is_false(b) and m.log == []


def test_what_if_eliminates_a_literal_that_leads_to_contradiction():
    """x=1 forces both y=1 and z=1, which may not hold together."""
    m = Model()
    for var in "xyz":
        _variable(m, var, (1, 2))
    m.relate("y follows x", "xy", lambda x, y: x != 1 or y == 1)
    m.relate("y avoids z", "yz", lambda y, z: y != 1 or z != 1)
    m.relate("z follows x", "xz", lambda x, z: x != 1 or z == 1)
    assert rule_relations(m) is False
    assert rule_what_if(m) is True
    assert m.is_false(m.literal("x", 1))


def test_what_if_rules_out_the_value_with_the_shortest_refutation():
    """x=1 comes first but fails only after y and z follow it; x=2 fails at
    once, so x=2 is the one ruled out."""
    m = Model()
    for var in "xyz":
        _variable(m, var, (1, 2))
    m.relate("x is never 2", "xy", lambda x, y: x != 2)
    m.relate("y follows x", "xy", lambda x, y: x != 1 or y == 1)
    m.relate("z follows y", "yz", lambda y, z: y != 1 or z == 1)
    m.relate("z avoids x", "xz", lambda x, z: x != 1 or z != 1)
    assert rule_what_if(m) is True
    (step,) = m.log
    assert (step.var, step.value) == ("x", 2)


# --- sudoku ---------------------------------------------------------------


def test_sudoku_model_shape():
    model, _ = sudoku.compile_puzzle((EXAMPLES / "sudoku_easy.txt").read_text())
    assert model.num_literals == 81 * 9
    assert len(model.constraints) == 81 + 3 * 81
    assert model.chosen("r1c1") == 5
    assert model.chosen("r1c3") is None


def test_sudoku_solves_to_a_valid_grid():
    model, grid = sudoku.compile_puzzle((EXAMPLES / "sudoku_easy.txt").read_text())
    result = Solver(model).solve()
    assert result.solved

    rows = [[result.assignment[sudoku.cell_name(r, c)] for c in range(9)] for r in range(9)]
    full = list(range(1, 10))
    assert all(sorted(row) == full for row in rows)
    assert all(sorted(rows[r][c] for r in range(9)) == full for c in range(9))
    assert all(
        sorted(rows[br * 3 + r][bc * 3 + c] for r in range(3) for c in range(3)) == full
        for br in range(3)
        for bc in range(3)
    )
    # every given survived
    assert all(grid[r][c] in (0, rows[r][c]) for r in range(9) for c in range(9))


def _before(rule: str) -> tuple[Rule, ...]:
    names = [r.name for r in DEFAULT_RULES]
    return DEFAULT_RULES[: names.index(rule)]


FISH = r"(\d) once in (row|col) \d+"  # a digit in one line; \1 digit, \2 row or col
LINE = r"once in \2 \d+"  # the same digit in another line of the same kind
HOUSE = r"\d once in [a-z]+ [\d,]+"  # any digit in any row, column or box

# file, the rule it needs, and the deduction pattern it must show
GRADED = [
    ("sudoku_pointing.txt", "subsumption", r"once in box"),
    ("sudoku_naked_pair.txt", "cover2", r"^r\dc\d holds one digit, r\dc\d holds one digit use up"),
    ("sudoku_hidden_pair.txt", "cover2", rf"^{HOUSE}, {HOUSE} use up r\dc\d holds"),
    ("sudoku_xwing.txt", "cover2", rf"^{FISH}, \1 {LINE} use up \1 once in (?!\2)"),
    ("sudoku_swordfish.txt", "cover3", rf"^{FISH}, \1 {LINE}, \1 {LINE} use up \1 once in (?!\2)"),
    ("sudoku_chains.txt", "chains", r"holds, by a chain of"),
]


@pytest.mark.parametrize("name, rule, pattern", GRADED)
def test_graded_sudoku_shows_its_pattern(name, rule, pattern):
    model, _ = sudoku.compile_puzzle((EXAMPLES / name).read_text())
    assert Solver(model).solve().solved
    assert any(s.rule == rule and re.search(pattern, s.reason) for s in model.log)


@pytest.mark.parametrize("name, rule, pattern", GRADED)
def test_graded_sudoku_stalls_without_its_rule(name, rule, pattern):
    model, _ = sudoku.compile_puzzle((EXAMPLES / name).read_text())
    result = Solver(model, _before(rule)).solve()
    assert not result.solved and result.contradiction is None


def test_sudoku_rejects_a_malformed_grid():
    with pytest.raises(ValueError):
        sudoku.parse("1 2 3\n4 5 6")
    with pytest.raises(ValueError, match="4 or 9"):
        sudoku.parse("\n".join([". " * 5] * 5))
    with pytest.raises(ValueError, match="go up to 4"):
        sudoku.parse("5 . . .\n. . . .\n. . . .\n. . . .")


def test_mini_sudoku_has_two_by_two_boxes():
    model, grid = sudoku.compile_puzzle((EXAMPLES / "sudoku_4x4.txt").read_text())
    boxes = [c for c in model.constraints if c.family == "each digit once per box"]
    assert len(grid) == 4 and len(boxes) == 4 * 4
    assert all(len(c.literals) == 4 for c in boxes)
    assert Solver(model).solve().solved


# --- murdoku --------------------------------------------------------------


@pytest.fixture
def prrrdoku1():
    board, clues = load_board((EXAMPLES / "prrrdoku1.txt").read_text())
    return board, murdoku.compile_puzzle(board, clues)


def test_people_are_the_variables(prrrdoku1):
    board, model = prrrdoku1
    assert sorted(model.variables) == sorted(board.people)
    # 7 people x 43 free squares
    assert len(board.free) == 49 - 6
    assert model.num_literals == 7 * 43


def test_clue_filtering_matches_the_published_candidate_lists(prrrdoku1):
    """These four lists are quoted verbatim in the document's solution."""
    board, model = prrrdoku1
    open_sq = {p: [str(s) for s in sqs] for p, sqs in murdoku.open_squares(board, model).items()}
    assert open_sq["Tim"] == ["r1c1", "r2c2", "r3c1"]
    assert open_sq["Tjitske"] == ["r4c2", "r5c1", "r6c2"]
    assert open_sq["Jos"] == ["r1c4", "r1c5", "r2c4", "r3c4", "r3c5", "r3c6"]
    assert open_sq["Pip"] == ["r1c6", "r1c7", "r2c6", "r2c7", "r4c7", "r5c7"]


def test_prrrdoku1_reaches_the_published_solution(prrrdoku1):
    _, model = prrrdoku1
    result = Solver(model).solve()
    assert result.solved
    assert {p: str(sq) for p, sq in result.assignment.items()} == {
        "Tim": "r1c1",
        "Jos": "r2c4",
        "Anna": "r3c6",
        "Pip": "r4c7",
        "Otto": "r5c5",
        "Tjitske": "r6c2",
        "Vladimir": "r7c3",
    }


def test_vladimir_shares_his_region_with_exactly_tjitske(prrrdoku1):
    """The puzzle's actual question."""
    board, model = prrrdoku1
    result = Solver(model).solve()
    assert result.solved
    vlad_region = board.region_of(result.assignment["Vladimir"])
    company = [
        p
        for p, sq in result.assignment.items()
        if p != "Vladimir" and board.region_of(sq) == vlad_region
    ]
    assert company == ["Tjitske"]
    assert board.region_names[vlad_region] == "kampeerplek"


def test_one_person_per_row_and_column(prrrdoku1):
    board, model = prrrdoku1
    result = Solver(model).solve()
    squares = list(result.assignment.values())
    assert sorted(s.row for s in squares) == list(range(board.size))
    assert sorted(s.col for s in squares) == list(range(board.size))


def test_nobody_stands_on_an_object(prrrdoku1):
    board, model = prrrdoku1
    result = Solver(model).solve()
    assert not set(result.assignment.values()) & board.blocked


def _one_region_board(size: int, people: list[str], objects=None, **extra) -> murdoku.Board:
    """A size x size board that is all region 'a', called 'here'."""
    grid = [["a"] * size for _ in range(size)]
    return murdoku.Board(size, grid, {"a": "here"}, objects or {}, people, **extra)


def test_people_count_must_match_board_size():
    with pytest.raises(ValueError):
        _one_region_board(3, ["only", "two"])


def test_relations_prunes_a_whole_relation_in_one_step():
    m = Model()
    _variable(m, "a", (1, 2, 3, 4))
    _variable(m, "b", (1, 2, 3, 4))
    m.relate("a below 2 and b above 3", "ab", lambda a, b: a < 2 and b > 3)
    assert rule_relations(m) is True
    assert [m.value_of(lit) for lit in m.options("a")] == [1]
    assert [m.value_of(lit) for lit in m.options("b")] == [4]
    assert rule_relations(m) is False


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_render_crosses_out_squares_nobody_can_reach():
    board = _one_region_board(2, ["A", "B"])
    model = murdoku.compile_puzzle(board, [("in_region", ["A", "here"])])
    sq = murdoku.Square
    model.eliminate(model.literal("A", sq(0, 0)), "test", "gone")
    rows = _plain(murdoku.render(board, model, "t")).splitlines()[3:5]
    assert [row.split() for row in rows] == [["1", ".", "."], ["2", ".", "."]]
    steps_from = len(model.log)
    model.eliminate(model.literal("B", sq(0, 0)), "test", "gone")
    drawn = murdoku.render(board, model, "t", model.log[steps_from:])
    assert _plain(drawn).splitlines()[3].split() == ["1", "x", "."]
    assert "3 of 4 empty squares still possible" in _plain(drawn)
    assert re.search(r"B\s+-1\s+3 left", _plain(drawn))


def test_parse_square_rejects_garbage():
    assert parse_square("R2C5") == murdoku.Square(1, 4)
    with pytest.raises(ValueError):
        parse_square("r2x5")


@pytest.mark.parametrize("name", sorted(p.name for p in EXAMPLES.glob("*.txt")))
def test_every_step_is_logged_under_its_rule_name(name):
    """Narration groups steps by rule, so the names in the log must match the ladder."""
    text = (EXAMPLES / name).read_text()
    model = cli.load(text, cli.detect(text)).model
    fired: list[tuple[str, set[str]]] = []
    Solver(model).solve(on_step=lambda rule, steps: fired.append((rule, {s.rule for s in steps})))
    assert fired
    for rule, logged in fired:
        assert logged == {rule}


# --- prrrdoku 2 and 3 -----------------------------------------------------


def _load(name):
    board, clues = load_board((EXAMPLES / name).read_text())
    return board, murdoku.compile_puzzle(board, clues)


def _open(board, model):
    return {p: [str(s) for s in sqs] for p, sqs in murdoku.open_squares(board, model).items()}


def test_prrrdoku2_candidate_lists_match_the_document():
    board, model = _load("prrrdoku2.txt")
    open_sq = _open(board, model)
    assert open_sq["Tim"] == ["r1c2", "r2c1", "r2c3", "r3c2"]
    assert open_sq["Tjitske"] == ["r5c2", "r6c1", "r6c3", "r7c2"]
    assert open_sq["Otto"] == ["r5c6", "r6c5", "r6c7", "r7c6"]
    assert open_sq["Luna"] == ["r7c4", "r8c3", "r8c5", "r9c4"]


def test_prrrdoku2_region_borders_match_the_document():
    """'De speeltuin grenst aan het klimgebied, de keukenwinkel, het cafe en de kampeerplek.'"""
    board, _ = _load("prrrdoku2.txt")
    speeltuin = board.region_id("speeltuin")
    touching = {
        name for rid, name in board.region_names.items() if board.regions_touch(speeltuin, rid)
    }
    assert touching == {"klimgebied", "keukenwinkel", "cafe", "kampeerplek"}


def test_prrrdoku3_candidate_lists_match_the_document():
    """The five lists the document's solution opens with."""
    board, model = _load("prrrdoku3.txt")
    open_sq = _open(board, model)
    assert open_sq["Tjitske"] == ["r4c1", "r5c2"]
    assert open_sq["Jos"] == ["r1c2", "r1c3", "r3c4", "r3c5", "r8c3", "r8c4"]
    assert open_sq["Tim"] == ["r1c6", "r3c6", "r6c7", "r6c9", "r7c6", "r9c6"]
    assert len(open_sq["Anna"]) == 7
    assert len(open_sq["Luna"]) == 19


PUBLISHED = {
    "prrrdoku2.txt": (
        {
            "Jos": "r1c4",
            "Pip": "r2c8",
            "Tim": "r3c2",
            "Anna": "r4c7",
            "Vladimir": "r5c5",
            "Tjitske": "r6c1",
            "Otto": "r7c6",
            "Luna": "r8c3",
            "Mao": "r9c9",
        },
        "cafe",
        ["Otto"],
    ),
    "prrrdoku3.txt": (
        {
            "Anna": "r1c4",
            "Mao": "r2c9",
            "Tim": "r3c6",
            "Vladimir": "r4c5",
            "Tjitske": "r5c2",
            "Otto": "r6c7",
            "Luna": "r7c1",
            "Jos": "r8c3",
            "Pip": "r9c8",
        },
        "moestuin",
        ["Tim"],
    ),
}


@pytest.mark.parametrize("name", sorted(PUBLISHED))
def test_later_prrrdokus_reach_the_published_solution(name):
    solution, vlad_region, company = PUBLISHED[name]
    board, model = _load(name)
    result = Solver(model).solve()
    assert result.solved
    assert {p: str(sq) for p, sq in result.assignment.items()} == solution
    region = board.region_of(result.assignment["Vladimir"])
    assert board.region_names[region] == vlad_region
    assert [
        p
        for p, sq in result.assignment.items()
        if p != "Vladimir" and board.region_of(sq) == region
    ] == company


def test_prrrdoku2_needs_chains():
    """The document splits on cases here; chains do it without guessing."""
    _, model = _load("prrrdoku2.txt")
    result = Solver(model, _before("chains")).solve()
    assert not result.solved and result.contradiction is None
    _, model = _load("prrrdoku2.txt")
    assert Solver(model, _before("what_if")).solve().solved


def test_prrrdoku3_still_needs_what_if():
    _, model = _load("prrrdoku3.txt")
    result = Solver(model, _before("what_if")).solve()
    assert not result.solved and result.contradiction is None


def _chain_model(weak_by_relation: bool) -> Model:
    """A1 or A2, B1 or B2, T1 or T2; A2 and B1 exclude each other, and T1
    excludes both A1 and B2. Chain: A1 false, A2 true, B1 false, B2 true."""
    m = Model()
    lits = {(v, i): m.literal(v, i) for v in "ABT" for i in (1, 2)}
    for v in "ABT":
        m.constrain(f"{v} one", Kind.EXACTLY_ONE, [lits[v, 1], lits[v, 2]], defines=v)
    if weak_by_relation:
        m.relate("not A2 with B1", ("A", "B"), lambda a, b: (a, b) != (2, 1))
    else:
        m.constrain("A2 or B1", Kind.AT_MOST_ONE, [lits["A", 2], lits["B", 1]])
    m.constrain("A1 or T1", Kind.AT_MOST_ONE, [lits["A", 1], lits["T", 1]])
    m.constrain("B2 or T1", Kind.AT_MOST_ONE, [lits["B", 2], lits["T", 1]])
    return m


@pytest.mark.parametrize("weak_by_relation", [False, True])
def test_chains_rule_out_what_excludes_both_ends(weak_by_relation):
    m = _chain_model(weak_by_relation)
    assert not rule_relations(m) and not rule_subsumption(m)
    assert rule_chains(m)
    (step,) = m.log
    assert (step.var, step.value, step.asserted) == ("T", 1, False)
    assert step.chain == (("A", 1), ("A", 2), ("B", 1), ("B", 2))
    assert step.sources == ("A one", "not A2 with B1" if weak_by_relation else "A2 or B1", "B one")


def test_follow_chain_refuses_a_broken_chain():
    m = _chain_model(False)
    a1, a2, b1, b2 = (m.literal(v, i) for v, i in (("A", 1), ("A", 2), ("B", 1), ("B", 2)))
    assert not follow_chain(m, [a1, b1, a2, b2])
    assert not m.log


def test_furniture_can_be_stood_on_and_objects_cannot():
    sq = murdoku.Square
    board = _one_region_board(
        2, ["A", "B"], {"rock": [sq(0, 0)]}, furniture={"bank": [sq(1, 0), sq(1, 1)]}
    )
    assert board.free == [sq(0, 1), sq(1, 0), sq(1, 1)]
    model = murdoku.compile_puzzle(board, [("on", ["A", "bank"])])
    assert sorted(model.value_of(lit) for lit in model.options("A")) == [sq(1, 0), sq(1, 1)]


def test_knight_move_and_shared_object_names():
    sq = murdoku.Square
    board = _one_region_board(3, ["A", "B", "C"], {"koffer": [sq(0, 0), sq(2, 2)]})
    model = murdoku.compile_puzzle(board, [("knight_from", ["A", "koffer"])])
    reachable = sorted(model.value_of(lit) for lit in model.options("A"))
    assert reachable == [sq(0, 1), sq(1, 0), sq(1, 2), sq(2, 1)]
    with pytest.raises(ValueError):
        murdoku.compile_puzzle(board, [("next_to", ["A", "suitcase"])])


def test_furthest_is_strict():
    board = _one_region_board(2, ["A", "B"])
    model = murdoku.compile_puzzle(board, [("furthest", ["A", "B"])])
    assert len(model.relations) == 0
    board = _one_region_board(3, ["A", "B", "C"])
    model = murdoku.compile_puzzle(board, [("furthest", ["A", "B"])])
    (rel,) = model.relations
    sq = murdoku.Square
    assert rel.holds(sq(0, 0), sq(2, 2), sq(1, 1))
    assert not rel.holds(sq(0, 2), sq(2, 2), sq(2, 0))


def test_unknown_region_name_is_rejected():
    board = _one_region_board(2, ["A", "B"])
    with pytest.raises(ValueError):
        murdoku.compile_puzzle(board, [("in_region", ["A", "nowhere"])])


def test_not_next_to_rules_out_the_squares_beside_a_thing():
    sq = murdoku.Square
    board = _one_region_board(3, ["A", "B", "C"], {"vaas": [sq(1, 1)]})
    model = murdoku.compile_puzzle(board, [("not_next_to", ["A", "vaas"])])
    left = sorted(model.value_of(lit) for lit in model.options("A"))
    assert left == [sq(0, 0), sq(0, 2), sq(2, 0), sq(2, 2)]


def test_counting_clue_parses_its_parts():
    n, parts = murdoku.counted(["1", "in_region", "A", "x", ";", "left_of", "A", "B"])
    assert n == 1 and parts == [("in_region", ["A", "x"]), ("left_of", ["A", "B"])]
    with pytest.raises(ValueError, match="count first"):
        murdoku.counted(["in_region", "A", "x"])


def test_counting_clue_holds_when_exactly_n_parts_do():
    sq = murdoku.Square
    board = _one_region_board(3, ["A", "B", "C"])
    clue = ("exactly", ["1", "left_of", "A", "B", ";", "above", "A", "B"])
    (rel,) = murdoku.compile_puzzle(board, [clue]).relations
    assert rel.variables == ("A", "B")
    assert rel.holds(sq(1, 0), sq(0, 2))  # left of, not above
    assert not rel.holds(sq(0, 0), sq(2, 2))  # both
    assert not rel.holds(sq(2, 2), sq(0, 0))  # neither


def test_counting_clue_about_one_person_filters_at_compile_time():
    sq = murdoku.Square
    board = _one_region_board(2, ["A", "B"], {"vaas": [sq(0, 0)]})
    clue = ("exactly", ["1", "next_to", "A", "vaas", ";", "not_next_to", "A", "vaas"])
    model = murdoku.compile_puzzle(board, [clue])
    assert not model.relations and len(model.options("A")) == 3


@pytest.mark.parametrize(
    "args, problem",
    [
        (["3", "left_of", "A", "B", ";", "above", "A", "B"], "can never hold"),
        (["1", "alone", "A", ";", "above", "A", "B"], "simple clues only"),
        (["1", "left_of", "A", "B", ";", "left_of", "C", "D"], "at most 3"),
    ],
)
def test_counting_clue_rejects_what_it_cannot_do(args, problem):
    board = _one_region_board(4, ["A", "B", "C", "D"])
    with pytest.raises(ValueError, match=problem):
        murdoku.compile_puzzle(board, [("exactly", args)])


def test_numeric_region_ids_still_read():
    """Ids are just tokens: older files numbered their regions."""
    text = (EXAMPLES / "prrrdoku1.txt").read_text()
    numbered = text.replace("\na: ", "\n0: ").replace("\nb: ", "\n1: ")
    numbered = re.sub(
        r"(?m)^([a-f] )+[a-f]$",
        lambda m: m[0].replace("a", "0").replace("b", "1"),
        numbered,
    )
    board, _ = load_board(numbered)
    assert board.region_names["0"] == "klimgebied"
    assert board.region_of(murdoku.Square(0, 3)) == "1"


# --- calcudoku -----------------------------------------------------------


# file, the rule it needs
CALCUDOKUS = [
    ("calcudoku_4x4_easy.txt", "relations"),
    ("calcudoku_6x6_medium.txt", "relations"),
    ("calcudoku_6x6_hard.txt", "cover2"),
    ("calcudoku_6x6_fiendish.txt", "what_if"),
    ("calcudoku_7x7_hard.txt", "cover3"),
]


@pytest.mark.parametrize("name, rule", CALCUDOKUS)
def test_calcudoku_solution_obeys_every_rule(name, rule):
    """A property check: Latin square, and every cage makes its target."""
    text = (EXAMPLES / name).read_text()
    model, puzzle = calcudoku.compile_puzzle(text)
    result = Solver(model).solve()
    assert result.solved
    n = puzzle.size
    grid = [[result.assignment[calcudoku.cell_name((r, c))] for c in range(n)] for r in range(n)]
    assert all(sorted(row) == list(range(1, n + 1)) for row in grid)
    assert all(sorted(col) == list(range(1, n + 1)) for col in zip(*grid, strict=True))
    assert all(cage.holds([grid[r][c] for r, c in cage.cells]) for cage in puzzle.cages)


@pytest.mark.parametrize("name, rule", [c for c in CALCUDOKUS if c[1] != "relations"])
def test_calcudoku_stalls_without_its_rule(name, rule):
    model, _ = calcudoku.compile_puzzle((EXAMPLES / name).read_text())
    result = Solver(model, _before(rule)).solve()
    assert not result.solved and result.contradiction is None


@pytest.mark.parametrize(
    "grid, cages, problem",
    [
        ("a a\nb b", "a: 3+", "no rule for cages"),
        ("a a\nb b", "a: 3+\nb: 3+\nc: 1", "not on the grid"),
        ("a b\nb a", "a: 3+\nb: 3+", "not one connected piece"),
        ("a a\nb c", "a: 1-\nb: 1\nc: 2/x", "bad rule"),
        ("a a\na b", "a: 2-\nb: 1", "needs exactly two cells"),
        ("a a\nb c", "a: 3\nb: 1\nc: 2", "need an operator"),
    ],
)
def test_calcudoku_rejects_malformed_files(grid, cages, problem):
    with pytest.raises(ValueError, match=problem):
        calcudoku.parse(f"Size: 2\nGrid:\n{grid}\nCages:\n{cages}\n")


def test_cage_arithmetic():
    cage = calcudoku.Cage
    assert cage(2, "/", ((0, 0), (0, 1))).holds([3, 6])
    assert cage(2, "/", ((0, 0), (0, 1))).holds([6, 3])
    assert not cage(2, "/", ((0, 0), (0, 1))).holds([4, 6])
    assert cage(3, "-", ((0, 0), (0, 1))).holds([1, 4])
    assert cage(24, "x", ((0, 0), (0, 1), (1, 0))).holds([2, 3, 4])


def test_cli_detects_calcudoku():
    text = (EXAMPLES / "calcudoku_4x4_easy.txt").read_text()
    assert cli.detect(text) == "calcudoku"
    assert cli.main([str(EXAMPLES / "calcudoku_4x4_easy.txt")]) == 0


# --- brute force ----------------------------------------------------------


@pytest.mark.parametrize("name", sorted(p.name for p in EXAMPLES.glob("*.txt")))
def test_every_example_is_unique_and_the_engine_finds_it(name):
    text = (EXAMPLES / name).read_text()
    (expected,) = bruteforce.solutions(text)
    result = Solver(cli.load(text, cli.detect(text)).model).solve()
    assert result.solved
    assert result.assignment == expected


@pytest.mark.parametrize("name", sorted(p.name for p in EXAMPLES.glob("*.txt")))
def test_no_step_ever_contradicts_the_brute_force_solution(name):
    """Every placement is right and every elimination removes a wrong value,
    compile time included: the soundness contract, checked step by step."""
    text = (EXAMPLES / name).read_text()
    (expected,) = bruteforce.solutions(text)
    model = cli.load(text, cli.detect(text)).model
    Solver(model).solve()
    for step in model.log:
        assert (step.value == expected[step.var]) == step.asserted, step


def test_bruteforce_never_touches_the_engine():
    """Its whole point is independence: no import from csp.core, directly."""
    import ast

    package = Path(bruteforce.__file__).parent
    for source in package.glob("*.py"):
        tree = ast.parse(source.read_text())
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        imported |= {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert not {m for m in imported if m.endswith("core")}, source.name


@pytest.mark.parametrize(
    "kind, text, count",
    [
        ("calcudoku", "Size: 2\nGrid:\na a\nb b\nCages:\na: 3+\nb: 3+\n", 2),
        ("calcudoku", "Size: 2\nGrid:\na a\nb b\nCages:\na: 4+\nb: 3+\n", 0),
        ("murdoku", "Size: 2\nRegions:\na: here\nGrid:\na a\na a\nPeople:\nA\nB\n", 4),
        ("sudoku", "\n".join(["5 5 . . . . . . ."] + [". " * 9] * 8), 0),
    ],
)
def test_bruteforce_reports_non_unique_and_impossible_puzzles(kind, text, count):
    assert len(bruteforce.solutions(text, kind, limit=5)) == count


def test_bruteforce_sudoku_stops_at_the_limit():
    empty = "\n".join([". " * 9] * 9)
    assert len(bruteforce.solutions(empty, "sudoku", limit=3)) == 3


def test_cli_brute_force_exit_codes(tmp_path, capsys):
    assert cli.main([str(EXAMPLES / "prrrdoku2.txt"), "--brute-force"]) == 0
    assert "unique solution" in capsys.readouterr().out
    two = tmp_path / "two.txt"
    two.write_text("Size: 2\nGrid:\na a\nb b\nCages:\na: 3+\nb: 3+\n")
    assert cli.main([str(two), "--brute-force"]) == 1
    assert "more than one solution" in capsys.readouterr().out


# --- model report ---------------------------------------------------------


def test_report_describes_prrrdoku1_as_the_engine_sees_it():
    _, model = _load("prrrdoku1.txt")
    text = report.describe(model)
    assert "7 variables, 301 literals, 64 constraints, 4 relations." in text
    assert re.search(r"each square holds at most one person\s+AT_MOST_ONE\s+43\s+7", text)
    assert "Every literal sits in exactly 4 constraints." in text
    assert re.search(r"next_to Tim klimwand\s+40 ruled out", text)
    assert re.search(r"Otto above Tjitske 1\s+18 of 129", text)
    assert all(re.search(rf"\d\. {rule.name}\s", text) for rule in DEFAULT_RULES)
    assert "cover2       Subsumption over 2 constraints" in text


def test_report_groups_unlabelled_constraints_by_name():
    m = Model()
    lits = _variable(m, "x", (1, 2, 3))
    m.constrain("pair 1", Kind.AT_MOST_ONE, lits[:2])
    m.constrain("pair 2", Kind.AT_MOST_ONE, lits[1:])
    assert re.search(r"pair #\s+AT_MOST_ONE\s+2\s+2", report.describe(m))


def test_report_leaves_the_model_untouched():
    model, _ = sudoku.compile_puzzle((EXAMPLES / "sudoku_xwing.txt").read_text())
    before = (len(model.log), model.assignment(), [model.options(v) for v in model.variables])
    report.describe(model)
    assert before == (
        len(model.log),
        model.assignment(),
        [model.options(v) for v in model.variables],
    )


def test_grade_is_the_hardest_rung_used():
    assert report.grade(["single", "cover2", "relations", "single"]) == "cover2"
    assert report.grade([]) == "none"
    assert report.rules_used(["single", "cover2", "single"]) == (
        "rules used: single 2, cover2 1; grade: cover2"
    )


@pytest.mark.parametrize(
    "name, grade",
    [
        ("sudoku_easy.txt", "single"),
        ("sudoku_pointing.txt", "subsumption"),
        ("sudoku_swordfish.txt", "cover3"),
        ("sudoku_chains.txt", "chains"),
        ("prrrdoku3.txt", "what_if"),
    ],
)
def test_cli_grade_prints_only_the_grade(name, grade, capsys):
    assert cli.main([str(EXAMPLES / name), "--grade"]) == 0
    assert capsys.readouterr().out == f"{grade}\n"


def test_show_model_explains_and_does_not_solve(capsys):
    assert cli.main([str(EXAMPLES / "sudoku_easy.txt"), "--show-model"]) == 0
    out = capsys.readouterr().out
    assert "each digit once per box" in out
    assert "How the solver will run" in out
    assert "Solved" not in out
    assert max(len(line) for line in out.split("Start", 1)[1].splitlines()) <= report.WIDTH
