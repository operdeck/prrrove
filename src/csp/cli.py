"""Command line front end."""

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from . import murdoku, report, sudoku
from .core import DEFAULT_RULES, Model, Solver, Step
from .puzzlefile import load_board


@dataclass(frozen=True)
class Puzzle:
    """A compiled puzzle, and how to draw it highlighting a batch of steps."""

    kind: str
    model: Model
    draw: Callable[[str, Sequence[Step]], str]


def detect(text: str) -> str:
    return "murdoku" if "Regions:" in text else "sudoku"


def load(text: str, kind: str) -> Puzzle:
    """Compile puzzle text of the given kind. Raises ValueError if malformed."""
    if kind == "sudoku":
        model, _ = sudoku.compile_puzzle(text)
        return Puzzle(kind, model, partial(sudoku.render, model))
    board, clues = load_board(text)
    model = murdoku.compile_puzzle(board, clues)
    return Puzzle(kind, model, partial(murdoku.render, board, model))


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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exact-cover puzzle solver")
    parser.add_argument("puzzle", type=Path, help="puzzle file")
    parser.add_argument("--verbose", "-v", action="store_true", help="narrate each deduction")
    parser.add_argument(
        "--step", "-s", action="store_true", help="redraw and pause after each deduction"
    )
    parser.add_argument("--type", choices=["auto", "sudoku", "murdoku"], default="auto")
    parser.add_argument(
        "--show-model",
        action="store_true",
        help="explain the compiled model and the solving algorithm, then stop",
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
    print(
        f"{kind}: {model.num_literals} literals, {len(model.constraints)} constraints, "
        f"{len(model.relations)} relations"
    )
    print(puzzle.draw("Start", ()))

    if args.show_model:
        print(f"\n{report.describe(model)}")
        return 0

    def on_step(rule: str, steps: Sequence[Step]) -> None:
        if not (args.verbose or args.step):
            return
        narrate(rule, steps)
        if args.step:
            print(puzzle.draw("After this step", steps))
            try:
                input("\n[enter] ")
            except EOFError:
                raise SystemExit(0) from None

    result = Solver(model).solve(on_step=on_step)

    if result.solved:
        print(puzzle.draw("Solved", ()))
    elif result.contradiction:
        print(puzzle.draw("Stuck", ()))
        print(f"\ncontradiction: {result.contradiction}")
    else:
        print(puzzle.draw("As far as the rules go", ()))
        undecided = [v for v in model.variables if v not in result.assignment]
        print(f"\n{len(undecided)} undecided: {', '.join(undecided)}")
        print(f"needs a rule beyond {'/'.join(rule.name for rule in DEFAULT_RULES)}.")

    print(f"\n{result.iterations} iterations, {len(model.log)} deductions logged")
    return 0 if result.solved else 1


if __name__ == "__main__":
    sys.exit(main())
