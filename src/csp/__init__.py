"""Constraint Satisfaction Puzzle Solver.

A generic solver for puzzles modeled as exact cover with propagation.
Supports Sudoku, Murdoku, Kakuro, and similar constraint puzzles.
"""

from .core import CSPModel, CSPSolver, Elimination, Placement

__all__ = ["CSPModel", "CSPSolver", "Elimination", "Placement"]
