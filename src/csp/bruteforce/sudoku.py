"""Sudoku by plain search: fill the cell with fewest candidates, backtrack."""

from ..sudoku import BOX, SIZE, cell_name, parse

type Grid = list[list[int]]


def solutions(text: str, limit: int = 2) -> list[dict[str, int]]:
    grid = parse(text)
    if not _givens_consistent(grid):
        return []
    found: list[dict[str, int]] = []
    _search(grid, found, limit)
    return found


def _candidates(grid: Grid, r: int, c: int) -> list[int]:
    br, bc = r - r % BOX, c - c % BOX
    used = set(grid[r]) | {grid[i][c] for i in range(SIZE)}
    used |= {grid[br + i][bc + j] for i in range(BOX) for j in range(BOX)}
    return [d for d in range(1, SIZE + 1) if d not in used]


def _givens_consistent(grid: Grid) -> bool:
    for r in range(SIZE):
        for c in range(SIZE):
            if given := grid[r][c]:
                grid[r][c] = 0
                ok = given in _candidates(grid, r, c)
                grid[r][c] = given
                if not ok:
                    return False
    return True


def _search(grid: Grid, found: list[dict[str, int]], limit: int) -> None:
    best: tuple[int, int, list[int]] | None = None
    for r in range(SIZE):
        for c in range(SIZE):
            if grid[r][c] == 0:
                options = _candidates(grid, r, c)
                if best is None or len(options) < len(best[2]):
                    best = (r, c, options)
    if best is None:
        found.append({cell_name(r, c): grid[r][c] for r in range(SIZE) for c in range(SIZE)})
        return
    r, c, options = best
    for d in options:
        grid[r][c] = d
        _search(grid, found, limit)
        grid[r][c] = 0
        if len(found) >= limit:
            return
