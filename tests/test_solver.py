"""Tests for the exact-cover engine and both puzzle compilers.

The Murdoku cases check against the published solution and candidate lists in
Prrrdoku.docx, so a wrong board transcription fails here rather than quietly
solving some other puzzle.
"""

import re
from pathlib import Path

import pytest

from csp import murdoku, sudoku
from csp.core import (
    DEFAULT_RULES,
    Contradiction,
    Kind,
    Model,
    Rule,
    Solver,
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


def _backtrack(grid):
    """Plain search, sharing no code with the engine: the independent answer."""
    g = [row[:] for row in grid]

    def fits(r, c, d):
        br, bc = r - r % 3, c - c % 3
        return (
            d not in g[r]
            and all(g[i][c] != d for i in range(9))
            and all(g[br + i][bc + j] != d for i in range(3) for j in range(3))
        )

    def go(i):
        if i == 81:
            return True
        r, c = divmod(i, 9)
        if g[r][c]:
            return go(i + 1)
        for d in range(1, 10):
            if fits(r, c, d):
                g[r][c] = d
                if go(i + 1):
                    return True
        g[r][c] = 0
        return False

    assert go(0)
    return g


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
    ("sudoku_what_if.txt", "what_if", r"^assuming it leads"),
]


@pytest.mark.parametrize("name, rule, pattern", GRADED)
def test_graded_sudoku_matches_independent_solution(name, rule, pattern):
    model, grid = sudoku.compile_puzzle((EXAMPLES / name).read_text())
    result = Solver(model).solve()
    assert result.solved
    expected = _backtrack(grid)
    assert all(
        result.assignment[sudoku.cell_name(r, c)] == expected[r][c]
        for r in range(9)
        for c in range(9)
    )
    assert any(s.rule == rule and re.search(pattern, s.reason) for s in model.log)


@pytest.mark.parametrize("name, rule, pattern", GRADED)
def test_graded_sudoku_stalls_without_its_rule(name, rule, pattern):
    model, _ = sudoku.compile_puzzle((EXAMPLES / name).read_text())
    result = Solver(model, _before(rule)).solve()
    assert not result.solved and result.contradiction is None


def test_sudoku_rejects_a_malformed_grid():
    with pytest.raises(ValueError):
        sudoku.parse("1 2 3\n4 5 6")


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
    assert open_sq["Tjitske"] == ["r4c2", "r5c1", "r5c3", "r6c2"]
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
    assert not set(result.assignment.values()) & set(board.objects.values())


def test_people_count_must_match_board_size():
    with pytest.raises(ValueError):
        murdoku.Board(3, [[0] * 3] * 3, {0: "a"}, {}, ["only", "two"])


def test_parse_square_rejects_garbage():
    assert parse_square("R2C5") == murdoku.Square(1, 4)
    with pytest.raises(ValueError):
        parse_square("r2x5")


@pytest.mark.parametrize("name", sorted(p.name for p in EXAMPLES.glob("*.txt")))
def test_every_step_is_logged_under_its_rule_name(name):
    """Narration groups steps by rule, so the names in the log must match the ladder."""
    text = (EXAMPLES / name).read_text()
    if "Regions:" in text:
        model = murdoku.compile_puzzle(*load_board(text))
    else:
        model, _ = sudoku.compile_puzzle(text)
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
    board, model = _load("prrrdoku3.txt")
    open_sq = _open(board, model)
    assert open_sq["Tjitske"] == ["r7c2", "r8c1", "r8c3", "r9c2"]
    assert open_sq["Luna"] == ["r5c7", "r6c7", "r7c8", "r7c9", "r8c9"]
    assert len(open_sq["Otto"]) == 14
    assert len(open_sq["Jos"]) == 21


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
            "Mauw": "r9c9",
        },
        "cafe",
        ["Otto"],
    ),
    "prrrdoku3.txt": (
        {
            "Mauw": "r1c4",
            "Otto": "r2c1",
            "Tim": "r3c7",
            "Vladimir": "r4c3",
            "Jos": "r5c8",
            "Anna": "r6c6",
            "Pip": "r7c5",
            "Luna": "r8c9",
            "Tjitske": "r9c2",
        },
        "speeltuin",
        ["Pip"],
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


def test_prrrdoku2_needs_what_if():
    """The document's own solution splits on cases here; so must the engine."""
    _, model = _load("prrrdoku2.txt")
    result = Solver(model, _before("what_if")).solve()
    assert not result.solved and result.contradiction is None


def test_furthest_is_strict():
    board = murdoku.Board(2, [[0, 0], [0, 0]], {0: "here"}, {}, ["A", "B"])
    model = murdoku.compile_puzzle(board, [("furthest", ["A", "B"])])
    assert len(model.relations) == 0
    board = murdoku.Board(3, [[0] * 3] * 3, {0: "here"}, {}, ["A", "B", "C"])
    model = murdoku.compile_puzzle(board, [("furthest", ["A", "B"])])
    (rel,) = model.relations
    sq = murdoku.Square
    assert rel.holds(sq(0, 0), sq(2, 2), sq(1, 1))
    assert not rel.holds(sq(0, 2), sq(2, 2), sq(2, 0))


def test_unknown_region_name_is_rejected():
    board = murdoku.Board(2, [[0, 0], [0, 0]], {0: "here"}, {}, ["A", "B"])
    with pytest.raises(ValueError):
        murdoku.compile_puzzle(board, [("in_region", ["A", "nowhere"])])
