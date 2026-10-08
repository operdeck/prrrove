"""Command line front end."""

import argparse
import sys
from pathlib import Path

from . import murdoku, sudoku
from .core import Solver, Step
from .puzzlefile import load_board


def detect(text: str) -> str:
    return "murdoku" if "Regions:" in text else "sudoku"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Exact-cover puzzle solver")
    parser.add_argument("puzzle", help="puzzle file")
    parser.add_argument("--verbose", "-v", action="store_true", help="narrate each deduction")
    parser.add_argument("--step", "-s", action="store_true", help="redraw and pause after each deduction")
    parser.add_argument("--type", choices=["auto", "sudoku", "murdoku"], default="auto")
    args = parser.parse_args(argv)

    path = Path(args.puzzle)
    if not path.exists():
        print(f"no such file: {path}", file=sys.stderr)
        return 2
    text = path.read_text()
    kind = detect(text) if args.type == "auto" else args.type
    narrate = args.verbose or args.step

    try:
        if kind == "sudoku":
            model, _ = sudoku.compile_puzzle(text)
            draw = lambda title, hl: sudoku.render(model, title, hl)
            names = sudoku.touched_cells
        else:
            board, clues = load_board(text)
            model = murdoku.compile_puzzle(board, clues)
            draw = lambda title, hl: murdoku.render(board, model, title, hl)
            names = murdoku.touched_people
    except ValueError as exc:
        print(f"could not read {path.name}: {exc}", file=sys.stderr)
        return 2

    print(f"{kind}: {len(model._literals)} literals, {len(model.constraints)} constraints, "
          f"{len(model.relations)} relations")
    print(draw("Start", set()))

    def on_step(rule: str, steps: list[Step]) -> None:
        if not narrate:
            return
        placed = [s for s in steps if s.asserted]
        dropped = len(steps) - len(placed)
        print(f"\n{rule}")
        for s in placed:
            print(f"  = {s.literal}  ({s.reason})")
        if not placed and dropped:
            first = next(s for s in steps if not s.asserted)
            print(f"  x {first.literal}  ({first.reason})")
        if dropped:
            print(f"  ... {dropped} option{'s' if dropped != 1 else ''} ruled out")
        if args.step:
            print(draw("After this step", names(steps)))
            try:
                input("\n[enter] ")
            except EOFError:
                raise SystemExit(0)

    result = Solver(model).solve(on_step=on_step)

    if result.solved:
        print(draw("Solved", set()))
    elif result.contradiction:
        print(draw("Stuck", set()))
        print(f"\ncontradiction: {result.contradiction}")
    else:
        print(draw("As far as the rules go", set()))
        open_vars = [v for v in model.variables if v not in result.assignment]
        print(f"\n{len(open_vars)} undecided: {', '.join(open_vars)}")
        print("needs a rule beyond single/relations/subsumption.")

    print(f"\n{result.iterations} iterations, {len(model.log)} deductions logged")
    return 0 if result.solved else 1


if __name__ == "__main__":
    sys.exit(main())
