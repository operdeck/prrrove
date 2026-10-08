"""Exact-cover puzzle solver.

`core` holds the puzzle-agnostic engine; each other module compiles one
puzzle family down to literals and constraints.
"""

from .core import Contradiction, Kind, Model, Result, Solver, Step

__all__ = ["Contradiction", "Kind", "Model", "Result", "Solver", "Step"]
