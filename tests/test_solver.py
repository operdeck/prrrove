"""Tests for the exact-cover engine and both puzzle compilers.

The Murdoku cases check against the published solution and candidate lists in
Prrrdoku.docx, so a wrong board transcription fails here rather than quietly
solving some other puzzle.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from csp import murdoku, sudoku
from csp.core import Contradiction, Kind, Model, Solver, rule_single, rule_subsumption
from csp.puzzlefile import load_board

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
    assert all(m.is_false(l) for l in extra)
    assert not any(m.is_false(l) for l in inner)


# --- sudoku ---------------------------------------------------------------


def test_sudoku_model_shape():
    model, grid = sudoku.compile_puzzle((EXAMPLES / "sudoku_easy.txt").read_text())
    assert len(model._literals) == 81 * 9
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
    assert all(
        grid[r][c] in (0, rows[r][c]) for r in range(9) for c in range(9)
    )


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
    assert len(model._literals) == 7 * 43


def test_clue_filtering_matches_the_published_candidate_lists(prrrdoku1):
    """These four lists are quoted verbatim in the document's solution."""
    board, model = prrrdoku1
    open_sq = {p: [str(s) for s in sqs] for p, sqs in murdoku.open_squares(board, model).items()}
    assert open_sq["Tim"] == ["r1c1", "r2c2", "r3c1"]
    assert open_sq["Tjitske"] == ["r4c2", "r5c1", "r5c3", "r6c2"]
    assert open_sq["Jos"] == ["r1c4", "r1c5", "r2c4", "r3c4", "r3c5", "r3c6"]
    assert open_sq["Pip"] == ["r1c6", "r1c7", "r2c6", "r2c7", "r4c7", "r5c7"]


def test_prrrdoku1_reaches_the_published_solution(prrrdoku1):
    board, model = prrrdoku1
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


def test_unknown_region_name_is_rejected():
    board = murdoku.Board(2, [[0, 0], [0, 0]], {0: "here"}, {}, ["A", "B"])
    with pytest.raises(ValueError):
        murdoku.compile_puzzle(board, [("in_region", ["A", "nowhere"])])
