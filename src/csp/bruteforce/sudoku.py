"""Sudoku by plain search: fill the cell with fewest candidates, backtrack."""

from ..sudoku import box_size, cell_name, parse

type Grid = list[list[int]]


def solutions(text: str, limit: int = 2) -> list[dict[str, int]]:
    grid = parse(text)
    if not _givens_consistent(grid):
        return []
    found: list[dict[str, int]] = []
    _search(grid, found, limit)
    return found


def _candidates(grid: Grid, r: int, c: int) -> list[int]:
    size = len(grid)
    box = box_size(size)
    br, bc = r - r % box, c - c % box
    used = set(grid[r]) | {grid[i][c] for i in range(size)}
    used |= {grid[br + i][bc + j] for i in range(box) for j in range(box)}
    return [d for d in range(1, size + 1) if d not in used]


def _givens_consistent(grid: Grid) -> bool:
    for r in range(len(grid)):
        for c in range(len(grid)):
            if given := grid[r][c]:
                grid[r][c] = 0
                ok = given in _candidates(grid, r, c)
                grid[r][c] = given
                if not ok:
                    return False
    return True


def _search(grid: Grid, found: list[dict[str, int]], limit: int) -> None:
    size = len(grid)
    best: tuple[int, int, list[int]] | None = None
    for r in range(size):
        for c in range(size):
            if grid[r][c] == 0:
                options = _candidates(grid, r, c)
                if best is None or len(options) < len(best[2]):
                    best = (r, c, options)
    if best is None:
        found.append({cell_name(r, c): grid[r][c] for r in range(size) for c in range(size)})
        return
    r, c, options = best
    for d in options:
        grid[r][c] = d
        _search(grid, found, limit)
        grid[r][c] = 0
        if len(found) >= limit:
            return
