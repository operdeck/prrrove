"""Futoshiki by plain search: fill cells in reading order, checking rows,
columns, givens, and every sign whose two cells are both filled."""

from collections import defaultdict

from ..futoshiki import Cell, Puzzle, Sign, cell_name, parse


def solutions(text: str, limit: int = 2) -> list[dict[str, int]]:
    puzzle = parse(text)
    signs_at: dict[Cell, list[Sign]] = defaultdict(list)
    for sign in puzzle.signs:
        signs_at[sign.smaller].append(sign)
        signs_at[sign.larger].append(sign)
    found: list[dict[str, int]] = []
    _search(puzzle, signs_at, {}, 0, found, limit)
    return found


def _search(
    puzzle: Puzzle,
    signs_at: dict[Cell, list[Sign]],
    grid: dict[Cell, int],
    i: int,
    found: list[dict[str, int]],
    limit: int,
) -> None:
    n = puzzle.size
    if i == n * n:
        found.append({cell_name(cell): v for cell, v in sorted(grid.items())})
        return
    r, c = divmod(i, n)
    given = puzzle.grid[r][c]
    for v in [given] if given else range(1, n + 1):
        if any(grid.get((r, j)) == v for j in range(c)) or any(
            grid.get((k, c)) == v for k in range(r)
        ):
            continue
        grid[(r, c)] = v
        if all(_holds(sign, grid) for sign in signs_at[(r, c)]):
            _search(puzzle, signs_at, grid, i + 1, found, limit)
        del grid[(r, c)]
        if len(found) >= limit:
            return


def _holds(sign: Sign, grid: dict[Cell, int]) -> bool:
    small, large = grid.get(sign.smaller), grid.get(sign.larger)
    return small is None or large is None or small < large
