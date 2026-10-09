"""Brute-force solving: plain search, kept apart from the deduction engine.

Used to check that a puzzle has exactly one solution, and as an independent
answer to test the engine against. Each module reads the puzzle with the
same file reader and tests the same rule definitions as the engine does
(Calcudoku cage arithmetic, Murdoku clue conditions), but searches on its
own: nothing here imports from `csp.core`, so no literal, constraint or
deduction rule is involved.

Every `solutions` function returns up to `limit` solutions, each as a dict
from variable name to value - the same shape as the engine's
`Result.assignment` - so the two can be compared directly.
"""

from collections.abc import Callable
from typing import Any

from ..puzzlefile import detect
from . import calcudoku, futoshiki, murdoku, sudoku

SOLVERS: dict[str, Callable[[str, int], list[dict[str, Any]]]] = {
    "sudoku": sudoku.solutions,
    "murdoku": murdoku.solutions,
    "calcudoku": calcudoku.solutions,
    "futoshiki": futoshiki.solutions,
}


def solutions(text: str, kind: str | None = None, limit: int = 2) -> list[dict[str, Any]]:
    """Up to `limit` solutions; the default of 2 is enough to test uniqueness."""
    return SOLVERS[kind or detect(text)](text, limit)
