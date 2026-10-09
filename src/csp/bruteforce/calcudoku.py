"""Calcudoku by plain search: fill cells in reading order, checking rows,
columns, and each cage as far as its filled cells allow."""

from math import prod

from ..calcudoku import Cage, Cell, Puzzle, cell_name, parse


def solutions(text: str, limit: int = 2) -> list[dict[str, int]]:
    puzzle = parse(text)
    found: list[dict[str, int]] = []
    _search(puzzle, {}, 0, found, limit)
    return found


def _search(
    puzzle: Puzzle, grid: dict[Cell, int], i: int, found: list[dict[str, int]], limit: int
) -> None:
    n = puzzle.size
    if i == n * n:
        found.append({cell_name(cell): v for cell, v in sorted(grid.items())})
        return
    r, c = divmod(i, n)
    for v in range(1, n + 1):
        if any(grid.get((r, j)) == v for j in range(c)) or any(
            grid.get((k, c)) == v for k in range(r)
        ):
            continue
        grid[(r, c)] = v
        if _still_possible(puzzle.cage_at[(r, c)], grid, n):
            _search(puzzle, grid, i + 1, found, limit)
        del grid[(r, c)]
        if len(found) >= limit:
            return


def _still_possible(cage: Cage, grid: dict[Cell, int], n: int) -> bool:
    """Whether the cage can still make its target, given its filled cells."""
    values = [grid[cell] for cell in cage.cells if cell in grid]
    open_cells = len(cage.cells) - len(values)
    if open_cells == 0:
        return cage.holds(values)
    match cage.operator:
        case "+":
            return sum(values) + open_cells <= cage.target <= sum(values) + open_cells * n
        case "x":
            return cage.target % prod(values) == 0
        case "-":
            (v,) = values
            return v + cage.target <= n or v - cage.target >= 1
        case "/":
            (v,) = values
            return v * cage.target <= n or v % cage.target == 0
    return True
