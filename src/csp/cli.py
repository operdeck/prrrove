"""Command-line interface for the CSP solver."""

import argparse
import sys
from pathlib import Path

from .sudoku import SudokuCompiler, SudokuDisplay
from .core import CSPSolver, Placement, Elimination


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generic constraint satisfaction puzzle solver"
    )
    parser.add_argument(
        "puzzle_file",
        help="Path to puzzle file (e.g., sudoku.txt)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show each reasoning step"
    )
    parser.add_argument(
        "--step", "-s",
        action="store_true",
        help="Step through interactively (pause after each step)"
    )
    parser.add_argument(
        "--show-candidates",
        action="store_true",
        help="Display candidate counts"
    )
    parser.add_argument(
        "--puzzle-type",
        default="sudoku",
        choices=["sudoku"],
        help="Type of puzzle"
    )
    parser.add_argument(
        "--log-limit",
        type=int,
        default=50,
        help="Show last N log entries"
    )

    args = parser.parse_args()

    # Step mode implies verbose
    if args.step:
        args.verbose = True

    # Read puzzle file
    puzzle_path = Path(args.puzzle_file)
    if not puzzle_path.exists():
        print(f"Error: File not found: {puzzle_path}", file=sys.stderr)
        return 1

    puzzle_str = puzzle_path.read_text()

    # Parse puzzle based on type
    if args.puzzle_type == "sudoku":
        try:
            compiler = SudokuCompiler(puzzle_str)
        except ValueError as e:
            print(f"Error parsing puzzle: {e}", file=sys.stderr)
            return 1
    else:
        print(f"Unknown puzzle type: {args.puzzle_type}", file=sys.stderr)
        return 1

    # Build model and solve
    print(f"Building {args.puzzle_type.upper()} model...")
    model = compiler.build()

    if args.verbose:
        print(f"Cells: {len(model.candidates)}")
        print(f"Groups: {len(model.groups)}")
        print()

    # Show initial state
    SudokuDisplay.show(model, title="Initial puzzle")
    if args.show_candidates:
        SudokuDisplay.show_candidates(model)

    print("\nSolving...")
    solver = CSPSolver(model)
    solution = solver.solve(verbose=args.verbose, step_through=args.step)

    # Display result
    if solution:
        print("\n✅ SOLVED!")
        SudokuDisplay.show(model, title="Solution")
    else:
        print("\n⏸ Reached fixed point (may need advanced techniques)")
        SudokuDisplay.show(model, title="Current state")
        unsolved = sum(
            1 for cell_id in model.candidates
            if cell_id not in model.placements
        )
        print(f"\n{unsolved} cells unsolved")

    # Show log
    if args.verbose:
        SudokuDisplay.show_log(model, limit=args.log_limit)

    return 0 if solution else 1


if __name__ == "__main__":
    sys.exit(main())
