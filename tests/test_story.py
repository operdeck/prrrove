"""Tests for the worked-solution writer and the proof it is built on.

Every placement a story states is checked against the brute force, so a
story can be clumsy but never wrong.
"""

import ast
import re
from pathlib import Path

import pytest

import csp
from csp import bruteforce, cli, murdoku
from csp.core import Model, Solver
from csp.proof import Move, replay, shortest
from csp.puzzlefile import load_board
from csp.story import Story, Wording, explain

EXAMPLES = Path(__file__).parent.parent / "examples"
PRRRDOKUS = ["prrrdoku1.txt", "prrrdoku2.txt", "prrrdoku3.txt"]
PLACED = re.compile(r"\*\*(\w+) op r(\d+)k(\d+)\*\*")


def _moves(model: Model) -> list[Move]:
    moves: list[Move] = []

    def collect(rule, steps):
        if (move := Move.of(rule, steps)) is not None:
            moves.append(move)

    Solver(model.clone()).solve(on_step=collect)
    return moves


# --- layering -------------------------------------------------------------

# Who may import whom inside the package; anything not listed may import freely.
ALLOWED = {
    "core": set(),
    "proof": {"core"},
    "murdoku": {"core"},
    "sudoku": {"core", "puzzlefile"},
    "calcudoku": {"core", "puzzlefile"},
    "futoshiki": {"core", "puzzlefile"},
    "story": {"core", "proof", "murdoku", "puzzlefile"},
    "picture": {"murdoku", "sudoku", "calcudoku", "futoshiki", "icons"},
}


@pytest.mark.parametrize("module", sorted(ALLOWED))
def test_modules_only_import_their_own_layer(module):
    """Solving knows nothing of explaining or drawing, and they know nothing of each other."""
    source = Path(csp.__file__).parent / f"{module}.py"
    tree = ast.parse(source.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            if node.module:
                imported.add(node.module.split(".")[0])
            else:
                imported |= {alias.name for alias in node.names}
    assert imported <= ALLOWED[module], f"{module} imports {imported - ALLOWED[module]}"


# --- proof ----------------------------------------------------------------


@pytest.mark.parametrize("name", PRRRDOKUS)
def test_shortest_proof_still_solves_and_drops_moves(name):
    board, clues = load_board((EXAMPLES / name).read_text())
    model = murdoku.compile_puzzle(board, clues)
    moves = _moves(model)
    kept = shortest(model, moves)
    assert len(kept) <= len(moves)
    assert all(move in moves for move in kept)
    assert replay(model, kept).solution() == replay(model, moves).solution()


def test_shortest_proof_drops_what_ifs_it_can_do_without():
    board, clues = load_board((EXAMPLES / "prrrdoku3.txt").read_text())
    model = murdoku.compile_puzzle(board, clues)
    moves = _moves(model)
    kept = shortest(model, moves)
    assert sum(m.rule == "what_if" for m in kept) < sum(m.rule == "what_if" for m in moves)


def test_replay_reports_each_change_like_the_solver():
    board, clues = load_board((EXAMPLES / "prrrdoku1.txt").read_text())
    model = murdoku.compile_puzzle(board, clues)
    fired: list[str] = []
    replay(model, _moves(model), lambda rule, steps: fired.append(rule))
    assert fired.count("single") == len(board.people)
    assert {"relations", "subsumption"} <= set(fired)


# --- story ----------------------------------------------------------------


@pytest.mark.parametrize("name", PRRRDOKUS)
def test_every_placement_in_the_story_is_right(name):
    text = (EXAMPLES / name).read_text()
    (solution,) = bruteforce.solutions(text)
    story = explain(text)
    placed = {who: f"r{solution[who].row + 1}k{solution[who].col + 1}" for who in solution}
    stated = {who: f"r{r}k{c}" for who, r, c in PLACED.findall(story)}
    assert stated == placed


@pytest.mark.parametrize("name", PRRRDOKUS)
def test_story_is_bullets_and_leads_with_the_direct_clues(name):
    story = explain((EXAMPLES / name).read_text())
    paragraphs = story.split("\n\n")
    assert all(p.startswith("- **") for p in paragraphs)
    assert paragraphs[0].startswith("- **De directe aanwijzingen.**")


def test_story_describes_by_region_and_row_before_squares():
    story = explain((EXAMPLES / "prrrdoku3.txt").read_text())
    assert "Luna zit in het water" in story
    assert "Otto zit in een klimgebied, dus Pip zit in een klimgebied" in story
    assert "Luna kan alleen in kolom 1, daar kan verder niemand" in story


@pytest.mark.parametrize("name", ["murdoku_intro.txt", "murdoku_house.txt"])
def test_english_story_places_everyone_right_and_titles_name_them(name):
    text = (EXAMPLES / name).read_text()
    (solution,) = bruteforce.solutions(text)
    story = explain(text)
    stated = re.findall(r"\*\*(\w+) on r(\d+)c(\d+)\*\*", story)
    assert {who: (int(r) - 1, int(c) - 1) for who, r, c in stated} == {
        who: (sq.row, sq.col) for who, sq in solution.items()
    }
    assert len(stated) == len(solution), "each person is placed in bold exactly once"
    for paragraph in story.split("\n\n")[1:]:
        title = re.match(r"- \*\*(.+?)\.\*\*", paragraph)[1]
        placed = re.findall(r"\*\*(\w+) on ", paragraph)
        assert title == "The rest" or all(who in title for who in placed), paragraph


def test_opening_narrows_clue_by_clue_and_places_whoever_it_pins_down():
    story = explain((EXAMPLES / "murdoku_house.txt").read_text())
    opening = story.split("\n\n")[0]
    assert "Ben is on the sofa (4): r3c3 or r3c4." in opening
    assert "Ben is not next to the lamp (6): **Ben on r3c4**." in opening


def test_counting_clue_is_worded_and_known_placements_are_not_bold_again():
    story = explain((EXAMPLES / "murdoku_house.txt").read_text())
    assert "Exactly one of these is true: Ada is in the study; Ben is in the hall (1)." in story
    assert "Ben is on r3c4, so Ada is not in the study" in story


def test_chains_are_told_as_if_then_with_the_reason_for_each_link():
    text = (EXAMPLES / "prrrdoku2.txt").read_text()
    original_clues = text.replace("above Anna Mao 5\n", "in_region Jos keukenwinkel\n")
    story = explain(original_clues.replace("at_least Jos Mao 13\n", ""))
    assert (
        "Als Otto niet op r6k5 zit, dan zit Otto op r7k6, dan zit Luna niet op r7k4 (rij 7), "
        "dan zit Luna op r8k3. Dus Otto zit op r6k5 of Luna zit op r8k3; hoe dan ook"
    ) in story
    assert "Tjitske zit op r5k2 of Tjitske zit op r6k1; hoe dan ook" in story


def test_story_cites_clue_numbers():
    story = explain((EXAMPLES / "prrrdoku1.txt").read_text())
    assert "Otto is precies één rij boven Tjitske (5)" in story
    assert "Jos is ergens links van Otto (8)" in story


def test_story_in_english():
    board, clues = load_board((EXAMPLES / "prrrdoku1.txt").read_text())
    story = Story(board, clues, Wording()).tell()
    assert story.startswith("- **The direct clues.**")
    assert "**Tim on r1c1**" in story
    assert "Otto is exactly one row above Tjitske (5)" in story


def test_wording_reads_its_sections_and_rejects_unknown_languages():
    say = Wording.read("Language: nl\nWords:\nvuurtje: het vuurtje\n")
    assert say.language == "nl" and say.words == {"vuurtje": "het vuurtje"}
    with pytest.raises(ValueError, match="no wording for language"):
        Wording.read("Language: xx\n")
    with pytest.raises(ValueError, match="Words"):
        Wording.read("Words:\nvuurtje\n")


def test_cli_explain(capsys):
    assert cli.main([str(EXAMPLES / "prrrdoku1.txt"), "--explain"]) == 0
    assert "**Tim op r1k1**" in capsys.readouterr().out
    assert cli.main([str(EXAMPLES / "sudoku_easy.txt"), "--explain"]) == 2


def test_board_rules_are_what_the_model_is_built_from():
    board, clues = load_board((EXAMPLES / "prrrdoku1.txt").read_text())
    model = murdoku.compile_puzzle(board, clues)
    names = {rule.name for rule in murdoku.board_rules(board)}
    assert names == {c.name for c in model.constraints}
