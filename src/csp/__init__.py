"""Exact-cover puzzle solver.

`core` holds the puzzle-agnostic engine; each other module compiles one
puzzle family down to literals and constraints.
"""

from .core import DEFAULT_RULES, Contradiction, Kind, Model, Result, Rule, Solver, Step

__all__ = ["DEFAULT_RULES", "Contradiction", "Kind", "Model", "Result", "Rule", "Solver", "Step"]
