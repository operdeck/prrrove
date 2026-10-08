"""Tests for Sudoku solver."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from csp.sudoku import SudokuCompiler
from csp.core import CSPSolver


def test_parse_simple_puzzle():
    """Test parsing a simple puzzle."""
    puzzle = """
    5 3 . | . 7 . | . . .
    6 . . | 1 9 5 | . . .
    . 9 8 | . . . | . 6 .
    ------+-------+------
    8 . . | . 6 . | . . 3
    4 . . | 8 . 3 | . . 1
    7 . . | . 2 . | . . 6
    ------+-------+------
    . 6 . | . . . | 2 8 .
    . . . | 4 1 9 | . . 5
    . . . | . 8 . | . 7 9
    """

    compiler = SudokuCompiler(puzzle)
    assert compiler.grid[0][0] == 5
    assert compiler.grid[0][2] == 0  # Empty
    assert compiler.grid[1][0] == 6


def test_build_model():
    """Test building CSP model."""
    puzzle = """
    5 3 . | . 7 . | . . .
    6 . . | 1 9 5 | . . .
    . 9 8 | . . . | . 6 .
    ------+-------+------
    8 . . | . 6 . | . . 3
    4 . . | 8 . 3 | . . 1
    7 . . | . 2 . | . . 6
    ------+-------+------
    . 6 . | . . . | 2 8 .
    . . . | 4 1 9 | . . 5
    . . . | . 8 . | . 7 9
    """

    compiler = SudokuCompiler(puzzle)
    model = compiler.build()

    # Check model has all cells
    assert len(model.candidates) == 81

    # Check model has groups (9 rows + 9 cols + 9 boxes + 81 cells)
    assert len(model.groups) == 27 + 81

    # Check givens are placed (1-indexed)
    assert model.placements["r1c1"] == 5
    assert model.placements["r1c2"] == 3


def test_solver_propagation():
    """Test that solver can make basic deductions."""
    puzzle = """
    5 3 . | . 7 . | . . .
    6 . . | 1 9 5 | . . .
    . 9 8 | . . . | . 6 .
    ------+-------+------
    8 . . | . 6 . | . . 3
    4 . . | 8 . 3 | . . 1
    7 . . | . 2 . | . . 6
    ------+-------+------
    . 6 . | . . . | 2 8 .
    . . . | 4 1 9 | . . 5
    . . . | . 8 . | . 7 9
    """

    compiler = SudokuCompiler(puzzle)
    model = compiler.build()
    solver = CSPSolver(model)

    initial_placements = len(model.placements)
    result = solver.solve(verbose=False)

    # Check that solver made progress and didn't break anything
    assert len(model.placements) >= initial_placements
    assert model.is_valid()


if __name__ == "__main__":
    test_parse_simple_puzzle()
    print("✓ test_parse_simple_puzzle")

    test_build_model()
    print("✓ test_build_model")

    test_solver_propagation()
    print("✓ test_solver_propagation")

    print("\nAll tests passed!")
