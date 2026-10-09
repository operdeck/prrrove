"""Sudoku expressed as exact cover.

Literals are "cell holds digit". The four constraint families are the whole
of Sudoku:
  * each cell holds exactly one digit
  * each digit sits exactly once in each row
  * ... each column
  * ... each box

The grid is N x N for a square N: 9 x 9 with 3 x 3 boxes, or a 4 x 4 mini
Sudoku with 2 x 2 boxes.
"""

from collections.abc import Sequence
from math import isqrt

from .core import Kind, Model, Step

BLUE = "\033[94m"
RESET = "\033[0m"

type Grid = list[list[int]]


def cell_name(row: int, col: int) -> str:
    """1-indexed, matching what the grid prints."""
    return f"r{row + 1}c{col + 1}"


def box_size(size: int) -> int:
    """The side of a box: 3 for a 9 x 9 grid, 2 for 4 x 4."""
    return isqrt(size)


def parse(text: str) -> Grid:
    """Read a square grid whose side is a square number (4 or 9). Digits are
    givens; '.' and '0' are blanks; anything else, such as '|' and '-'
    separators, is ignored."""
    grid = []
    for line in text.strip().splitlines():
        row = [0 if ch in ".0" else int(ch) for ch in line if ch in ".0123456789"]
        if row:
            grid.append(row)
    size = len(grid)
    if size not in (4, 9):
        raise ValueError(f"grid has {size} rows, expected 4 or 9")
    for row in grid:
        if len(row) != size:
            raise ValueError(f"a row has {len(row)} cells, expected {size}")
        if any(d > size for d in row):
            raise ValueError(f"digits in a {size} x {size} grid go up to {size}")
    return grid


def compile_puzzle(text: str) -> tuple[Model, Grid]:
    """The model for a Sudoku, with its givens already assigned, and the grid read."""
    grid = parse(text)
    size, box = len(grid), box_size(len(grid))
    model = Model()

    digits = range(1, size + 1)
    cells = [(r, c) for r in range(size) for c in range(size)]

    # Each cell holds exactly one digit. This constraint is the cell's domain.
    for row, col in cells:
        name = cell_name(row, col)
        model.constrain(
            f"{name} holds one digit",
            Kind.EXACTLY_ONE,
            [model.literal(name, d) for d in digits],
            defines=name,
            family="each cell holds one digit",
        )

    # Each digit appears exactly once per row, column and box.
    for d in digits:
        for r in range(size):
            model.constrain(
                f"{d} once in row {r + 1}",
                Kind.EXACTLY_ONE,
                [model.literal(cell_name(r, c), d) for c in range(size)],
                family="each digit once per row",
            )
        for c in range(size):
            model.constrain(
                f"{d} once in col {c + 1}",
                Kind.EXACTLY_ONE,
                [model.literal(cell_name(r, c), d) for r in range(size)],
                family="each digit once per column",
            )
        for br in range(size // box):
            for bc in range(size // box):
                members = [
                    model.literal(cell_name(br * box + r, bc * box + c), d)
                    for r in range(box)
                    for c in range(box)
                ]
                model.constrain(
                    f"{d} once in box {br + 1},{bc + 1}",
                    Kind.EXACTLY_ONE,
                    members,
                    family="each digit once per box",
                )

    for row, col in cells:
        given = grid[row][col]
        if given:
            name = cell_name(row, col)
            model.assign(model.literal(name, given), "given", "stated in the puzzle")

    return model, grid


def render(model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """Draw the grid, colouring the cells placed by `steps`."""
    placed = {s.var for s in steps if s.asserted}
    size = isqrt(len(model.variables))
    box = box_size(size)
    rule = "  " + "+".join([""] + ["-" * (2 * box)] * (size // box) + [""])
    out = [f"\n{title}", rule]
    for r in range(size):
        if r and r % box == 0:
            out.append(rule)
        line = f"{r + 1} |"
        for c in range(size):
            if c and c % box == 0:
                line += "|"
            name = cell_name(r, c)
            digit = model.chosen(name)
            if digit is None:
                line += ". "
            elif name in placed:
                line += f"{BLUE}{digit}{RESET} "
            else:
                line += f"{digit} "
        out.append(line + "|")
    out.append(rule)
    labels = [
        " ".join(str(c + 1) for c in range(b * box, (b + 1) * box)) for b in range(size // box)
    ]
    out.append("  |" + " |".join(labels) + " |")
    return "\n".join(out)
