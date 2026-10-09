"""Murdoku by plain search: place people one at a time, most restricted first.

Each person takes a free square in an unused row and column; a clue is
tested as soon as everyone it mentions has been placed.
"""

from ..murdoku import Condition, Square, conditions
from ..puzzlefile import load_board


def solutions(text: str, limit: int = 2) -> list[dict[str, Square]]:
    board, clues = load_board(text)
    checks = conditions(board, clues)
    allowed = {
        person: [
            sq for sq in board.free if all(c.test(sq) for c in checks if c.people == (person,))
        ]
        for person in board.people
    }
    order = sorted(board.people, key=lambda p: len(allowed[p]))
    later = {person: i for i, person in enumerate(order)}
    # Test each multi-person condition when the last person it names is placed.
    due: dict[str, list[Condition]] = {p: [] for p in board.people}
    for check in checks:
        if len(check.people) > 1:
            due[max(check.people, key=later.__getitem__)].append(check)

    found: list[dict[str, Square]] = []
    _search(order, allowed, due, {}, found, limit)
    return found


def _search(
    order: list[str],
    allowed: dict[str, list[Square]],
    due: dict[str, list[Condition]],
    placed: dict[str, Square],
    found: list[dict[str, Square]],
    limit: int,
) -> None:
    if len(placed) == len(order):
        found.append(dict(placed))
        return
    person = order[len(placed)]
    rows = {sq.row for sq in placed.values()}
    cols = {sq.col for sq in placed.values()}
    for sq in allowed[person]:
        if sq.row in rows or sq.col in cols:
            continue
        placed[person] = sq
        if all(check.test(*(placed[p] for p in check.people)) for check in due[person]):
            _search(order, allowed, due, placed, found, limit)
        del placed[person]
        if len(found) >= limit:
            return
