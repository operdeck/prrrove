"""Command line front end."""

import argparse
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from . import bruteforce, calcudoku, futoshiki, murdoku, report, story, sudoku
from .core import DEFAULT_RULES, Contradiction, Model, Solver, Step
from .puzzlefile import KINDS, detect, load_board


@dataclass(frozen=True)
class Puzzle:
    """A compiled puzzle, and how to draw any state of its model."""

    kind: str
    model: Model
    render: Callable[[Model, str, Sequence[Step]], str]

    def draw(self, title: str, steps: Sequence[Step] = (), model: Model | None = None) -> str:
        """Draw `model` (by default the puzzle's own), highlighting `steps`."""
        return self.render(model or self.model, title, steps)


def load(text: str, kind: str) -> Puzzle:
    """Compile puzzle text of the given kind. Raises ValueError if malformed."""
    if kind == "sudoku":
        model, layout = sudoku.compile_puzzle(text)
        return Puzzle(kind, model, partial(sudoku.render, layout))
    if kind == "calcudoku":
        model, cages = calcudoku.compile_puzzle(text)
        return Puzzle(kind, model, partial(calcudoku.render, cages))
    if kind == "futoshiki":
        model, signs = futoshiki.compile_puzzle(text)
        return Puzzle(kind, model, partial(futoshiki.render, signs))
    board, clues = load_board(text)
    model = murdoku.compile_puzzle(board, clues)
    return Puzzle(kind, model, partial(murdoku.render, board))


def narrate(rule: str, steps: Sequence[Step]) -> None:
    """Print one rule firing: what it placed, or a sample of what it ruled out."""
    placed = [s for s in steps if s.asserted]
    dropped = [s for s in steps if not s.asserted]
    print(f"\n{rule}")
    for s in placed:
        print(f"  = {s.literal}  ({s.reason})")
    if dropped and not placed:
        print(f"  x {dropped[0].literal}  ({dropped[0].reason})")
    if dropped:
        print(f"  ... {len(dropped)} option{'s' if len(dropped) != 1 else ''} ruled out")


def brute_force(puzzle: Puzzle, text: str) -> int:
    """Search for solutions without the engine. Exit code 0 means exactly one."""
    start = time.perf_counter()
    found = bruteforce.solutions(text, puzzle.kind, limit=2)
    elapsed = time.perf_counter() - start
    if not found:
        print(f"\nbrute force: no solution ({elapsed:.2f}s)")
        return 1
    try:
        for i, solution in enumerate(found, 1):
            title = "The unique solution" if len(found) == 1 else f"Solution {i}"
            print(puzzle.draw(title, model=_filled(puzzle.model, solution)))
    except Contradiction as exc:
        print(f"\nbrute force found a solution the engine's model rules out: {exc}")
        return 3
    if len(found) == 1:
        print(f"\nbrute force: unique solution ({elapsed:.2f}s)")
        return 0
    first, second = found
    differ = ", ".join(
        f"{var} ({first[var]} or {second[var]})" for var in first if first[var] != second[var]
    )
    print(f"\nbrute force: more than one solution ({elapsed:.2f}s); these two differ at {differ}")
    return 1


def write_picture(kind: str, text: str, path: Path, solution: dict[str, Any] | None = None) -> bool:
    """Save the puzzle as a PNG, with `solution` drawn in if given."""
    try:
        from . import picture
    except ImportError:
        print("--png needs Pillow: uv sync --extra png", file=sys.stderr)
        return False
    if kind == "sudoku":
        image = picture.sudoku_picture(sudoku.parse(text), solution)
    elif kind == "calcudoku":
        image = picture.calcudoku_picture(calcudoku.parse(text), solution)
    elif kind == "futoshiki":
        image = picture.futoshiki_picture(futoshiki.parse(text), solution)
    else:
        board, _ = load_board(text)
        image = picture.murdoku_picture(board, solution)
    image.save(path)
    print(f"wrote {path}")
    return True


def _filled(model: Model, solution: dict[str, Any]) -> Model:
    """A copy of `model` with every variable set as in `solution`, for drawing.

    Raises Contradiction if the model had already ruled that value out, which
    would mean the compiler and the brute force disagree about the puzzle.
    """
    twin = model.clone()
    for var, value in solution.items():
        domain = twin.constraints[twin.domain_of(var)].literals
        (lit,) = (lit for lit in domain if twin.value_of(lit) == value)
        twin.assign(lit, "brute_force", "found by search")
    return twin


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exact-cover puzzle solver")
    parser.add_argument("puzzle", type=Path, help="puzzle file")
    parser.add_argument("--verbose", "-v", action="store_true", help="narrate each deduction")
    parser.add_argument(
        "--step", "-s", action="store_true", help="redraw and pause after each deduction"
    )
    parser.add_argument(
        "--track-person",
        metavar="PERSON",
        help="Murdoku only: trace a person's live squares and region-overlap companions",
    )
    parser.add_argument("--type", choices=["auto", *KINDS], default="auto")
    instead = parser.add_mutually_exclusive_group()
    instead.add_argument(
        "--show-model",
        action="store_true",
        help="explain the compiled model and the solving algorithm, then stop",
    )
    instead.add_argument(
        "--brute-force",
        action="store_true",
        help="search for every solution without the engine, to check uniqueness",
    )
    instead.add_argument(
        "--explain",
        action="store_true",
        help="Murdoku only: write out a short worked solution, as for a puzzle booklet",
    )
    instead.add_argument(
        "--grade",
        action="store_true",
        help="print only the puzzle's grade: the hardest rule the solve needed",
    )
    parser.add_argument(
        "--png",
        type=Path,
        metavar="FILE",
        help="write the puzzle as a picture to FILE, and once solved the "
        "solution to FILE with '-solution' before the extension (needs Pillow)",
    )
    args = parser.parse_args(argv)

    path: Path = args.puzzle
    if not path.exists():
        print(f"no such file: {path}", file=sys.stderr)
        return 2
    text = path.read_text()
    kind = detect(text) if args.type == "auto" else args.type
    try:
        puzzle = load(text, kind)
    except ValueError as exc:
        print(f"could not read {path.name}: {exc}", file=sys.stderr)
        return 2

    model = puzzle.model
    track_board: murdoku.Board | None = None
    if args.track_person:
        if kind != "murdoku":
            parser.error("--track-person is only available for Murdoku")
        if args.show_model or args.brute_force or args.explain or args.grade:
            parser.error("--track-person requires a normal solve")
        track_board, _ = load_board(text)
        if args.track_person not in track_board.people:
            parser.error(
                f"unknown person {args.track_person!r}; have {', '.join(track_board.people)}"
            )
    if args.grade:
        fired: list[str] = []
        result = Solver(model).solve(on_step=lambda rule, steps: fired.append(rule))
        print(report.grade(fired) if result.solved else "unsolved")
        return 0 if result.solved else 1
    print(
        f"{kind}: {model.num_literals} literals, {len(model.constraints)} constraints, "
        f"{len(model.relations)} relations"
    )
    print(puzzle.draw("Start"))
    if args.track_person:
        assert track_board is not None
        print(murdoku.track_person_status(track_board, model, args.track_person))
    if args.png and not write_picture(kind, text, args.png):
        return 2

    if args.show_model:
        print(f"\n{report.describe(model)}")
        return 0
    if args.brute_force:
        return brute_force(puzzle, text)
    if args.explain:
        if kind != "murdoku":
            print(
                f"--explain only writes out Murdoku solutions so far, not {kind}", file=sys.stderr
            )
            return 2
        print(f"\n{story.explain(text)}")
        return 0

    used: list[str] = []

    def on_step(rule: str, steps: Sequence[Step]) -> None:
        used.append(rule)
        if not (args.verbose or args.step or args.track_person):
            return
        narrate(rule, steps)
        if args.track_person:
            assert track_board is not None
            print(murdoku.track_person_status(track_board, model, args.track_person))
        if args.step:
            print(puzzle.draw("After this step", steps))
            try:
                input("\n[enter] ")
            except EOFError:
                raise SystemExit(0) from None

    result = Solver(model).solve(on_step=on_step)

    if result.solved:
        print(puzzle.draw("Solved"))
        if args.png:
            solved = args.png.with_stem(f"{args.png.stem}-solution")
            write_picture(kind, text, solved, result.assignment)
    elif result.contradiction:
        print(puzzle.draw("Stuck"))
        print(f"\ncontradiction: {result.contradiction}")
    else:
        print(puzzle.draw("As far as the rules go"))
        undecided = [v for v in model.variables if v not in result.assignment]
        print(f"\n{len(undecided)} undecided: {', '.join(undecided)}")
        print(f"needs a rule beyond {'/'.join(rule.name for rule in DEFAULT_RULES)}.")

    print(f"\n{result.iterations} iterations, {len(model.log)} deductions logged")
    print(report.rules_used(used))
    return 0 if result.solved else 1


if __name__ == "__main__":
    sys.exit(main())
