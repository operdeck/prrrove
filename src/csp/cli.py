"""Command-line interface for the CSP solver."""

import argparse
import sys
from pathlib import Path

from .sudoku import SudokuCompiler, SudokuDisplay
from .murdoku import MurdokuCompiler, MurdokuDisplay
from .core import CSPSolver, Placement, Elimination


def _parse_murdoku(puzzle_str: str) -> tuple:
    """Parse Murdoku puzzle file format.

    Returns:
        (compiler, metadata) where metadata contains grid, regions, suspects
    """
    lines = puzzle_str.strip().split('\n')

    grid = None
    regions = {}
    suspects = []
    objects_pos = {}

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1

        if not line or line.startswith('#'):
            continue

        if line == 'Grid:':
            grid = []
            while i < len(lines) and lines[i].strip() and not lines[i].startswith('#'):
                row = [int(x) for x in lines[i].split()]
                grid.append(row)
                i += 1

        elif line == 'Regions:':
            while i < len(lines) and lines[i].strip() and not lines[i].startswith('#'):
                parts = lines[i].split(':', 1)
                if len(parts) == 2:
                    region_id = int(parts[0].strip())
                    region_name = parts[1].strip()
                    regions[region_id] = region_name
                i += 1

        elif line == 'Suspects:':
            while i < len(lines) and lines[i].strip() and not lines[i].startswith('#'):
                suspects.append(lines[i].strip())
                i += 1

        elif line == 'Objects:':
            while i < len(lines) and lines[i].strip() and not lines[i].startswith('#'):
                parts = lines[i].split(':')
                if len(parts) == 2:
                    cell_id = parts[0].strip()
                    obj_name = parts[1].strip()
                    r, c = MurdokuCompiler._from_cell_id(cell_id)
                    objects_pos[obj_name] = (r, c)
                i += 1

    if not grid or not suspects:
        raise ValueError("Murdoku file must have Grid and Suspects sections")

    compiler = MurdokuCompiler(grid, regions, suspects, objects_pos)
    metadata = {
        'grid': grid,
        'regions': regions,
        'suspects': suspects,
        'objects': objects_pos
    }
    return compiler, metadata


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
        default="auto",
        choices=["auto", "sudoku", "murdoku"],
        help="Type of puzzle (auto = detect from extension)"
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

    # Detect puzzle type if auto
    puzzle_type = args.puzzle_type
    if puzzle_type == "auto":
        if "Grid:" in puzzle_str:
            puzzle_type = "murdoku"
        else:
            puzzle_type = "sudoku"

    # Parse puzzle based on type
    compiler = None
    puzzle_meta = None
    try:
        if puzzle_type == "sudoku":
            compiler = SudokuCompiler(puzzle_str)
        elif puzzle_type == "murdoku":
            compiler, puzzle_meta = _parse_murdoku(puzzle_str)
        else:
            print(f"Unknown puzzle type: {puzzle_type}", file=sys.stderr)
            return 1
    except ValueError as e:
        print(f"Error parsing puzzle: {e}", file=sys.stderr)
        return 1

    # Build model and solve
    print(f"Building {puzzle_type.upper()} model...")
    model = compiler.build()

    if args.verbose:
        print(f"Cells: {len(model.candidates)}")
        print(f"Groups: {len(model.groups)}")
        print()

    # Show initial state
    if puzzle_type == "sudoku":
        SudokuDisplay.show(model, title="Initial puzzle")
    elif puzzle_type == "murdoku":
        MurdokuDisplay.show(model, puzzle_meta['grid'], puzzle_meta['regions'],
                          puzzle_meta['suspects'], title="Initial puzzle")
    if args.show_candidates:
        SudokuDisplay.show_candidates(model)

    print("\nSolving...")
    solver = CSPSolver(model)
    solution = solver.solve(verbose=args.verbose, step_through=args.step)

    # Display result
    if solution:
        print("\n✅ SOLVED!")
        if puzzle_type == "sudoku":
            SudokuDisplay.show(model, title="Solution")
        elif puzzle_type == "murdoku":
            MurdokuDisplay.show(model, puzzle_meta['grid'], puzzle_meta['regions'],
                              puzzle_meta['suspects'], title="Solution")
    else:
        print("\n⏸ Reached fixed point (may need advanced techniques)")
        if puzzle_type == "sudoku":
            SudokuDisplay.show(model, title="Current state")
        elif puzzle_type == "murdoku":
            MurdokuDisplay.show(model, puzzle_meta['grid'], puzzle_meta['regions'],
                              puzzle_meta['suspects'], title="Current state")
        unsolved = sum(
            1 for cell_id in model.candidates
            if cell_id not in model.placements
        )
        print(f"\n{unsolved} cells unsolved")

    # Show log
    if args.verbose and puzzle_type == "sudoku":
        SudokuDisplay.show_log(model, limit=args.log_limit)

    return 0 if solution else 1


if __name__ == "__main__":
    sys.exit(main())
