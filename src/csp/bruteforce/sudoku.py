"""Sudoku by plain search: fill the cell with fewest candidates, backtrack.

Shares only `sudoku.Puzzle.houses()`, the definition of what a Sudoku
requires, with the engine's compiler.
"""

from ..sudoku import Cell, cell_name, parse

type Grid = list[list[int]]
type Peers = dict[Cell, list[Cell]]


def solutions(text: str, limit: int = 2) -> list[dict[str, int]]:
    puzzle = parse(text)
    grid = [list(row) for row in puzzle.grid]
    peers: Peers = {}
    for _, _, cells in puzzle.houses():
        for cell in cells:
            peers.setdefault(cell, []).extend(other for other in cells if other != cell)
    if not _givens_consistent(grid, peers):
        return []
    found: list[dict[str, int]] = []
    _search(grid, peers, found, limit)
    return found


def _candidates(grid: Grid, peers: Peers, r: int, c: int) -> list[int]:
    used = {grid[pr][pc] for pr, pc in peers[r, c]}
    return [d for d in range(1, len(grid) + 1) if d not in used]


def _givens_consistent(grid: Grid, peers: Peers) -> bool:
    for r in range(len(grid)):
        for c in range(len(grid)):
            if given := grid[r][c]:
                grid[r][c] = 0
                ok = given in _candidates(grid, peers, r, c)
                grid[r][c] = given
                if not ok:
                    return False
    return True


def _search(grid: Grid, peers: Peers, found: list[dict[str, int]], limit: int) -> None:
    size = len(grid)
    best: tuple[int, int, list[int]] | None = None
    for r in range(size):
        for c in range(size):
            if grid[r][c] == 0:
                options = _candidates(grid, peers, r, c)
                if best is None or len(options) < len(best[2]):
                    best = (r, c, options)
    if best is None:
        found.append({cell_name(r, c): grid[r][c] for r in range(size) for c in range(size)})
        return
    r, c, options = best
    for d in options:
        grid[r][c] = d
        _search(grid, peers, found, limit)
        grid[r][c] = 0
        if len(found) >= limit:
            return
