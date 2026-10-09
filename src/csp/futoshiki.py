"""Futoshiki expressed as exact cover.

An N x N grid holds 1..N once in every row and column. Some cells are given,
and signs between neighbouring cells say which of the two is larger:

    Grid:
    . . . 4 .
    . . . . .
    ...
    Signs:
    r1c1 < r1c2
    r2c3 > r3c3

Literals are "cell holds number", as in Sudoku. Cells, rows and columns are
EXACTLY_ONE constraints; each sign is one relation over its two cells.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property

from .core import Kind, Model, Step
from .puzzlefile import read_sections

type Cell = tuple[int, int]

BOLD = "\033[1m"
NEW = "\033[38;5;21m"  # blue: changed by the step just shown
FADED = "\033[38;5;245m"
RESET = "\033[0m"

SIZES = range(4, 10)
PENCIL_MARKS_UP_TO = 7  # larger grids show '.' for open cells to stay narrow


def cell_name(cell: Cell) -> str:
    row, col = cell
    return f"r{row + 1}c{col + 1}"


@dataclass(frozen=True)
class Sign:
    """`smaller` holds a smaller number than its neighbour `larger`."""

    smaller: Cell
    larger: Cell

    @property
    def label(self) -> str:
        return f"{cell_name(self.smaller)} < {cell_name(self.larger)}"


@dataclass(frozen=True)
class Puzzle:
    grid: list[list[int]]  # 0 for an open cell
    signs: tuple[Sign, ...]

    @property
    def size(self) -> int:
        return len(self.grid)

    @cached_property
    def sign_between(self) -> dict[tuple[Cell, Cell], str]:
        """(first, second) in reading order -> '<' or '>', read left to right or top down."""
        out = {}
        for s in self.signs:
            if s.smaller < s.larger:
                out[s.smaller, s.larger] = "<"
            else:
                out[s.larger, s.smaller] = ">"
        return out


def parse(text: str) -> Puzzle:
    """Read a Futoshiki file: a Grid of digits and dots, and its Signs."""
    section = read_sections(text)
    for required in ("Grid", "Signs"):
        if required not in section:
            raise ValueError(f"puzzle file is missing a {required}: section")
    rows = [line.split() for line in section["Grid"]]
    n = len(rows)
    if n not in SIZES or any(len(row) != n for row in rows):
        raise ValueError(f"Grid must be square, 4x4 to 9x9; got {n} rows")
    grid = []
    for row in rows:
        if bad := [t for t in row if t != "." and not ("1" <= t <= str(n) and len(t) == 1)]:
            raise ValueError(f"Grid holds {bad[0]!r}; expected 1-{n} or '.'")
        grid.append([0 if t == "." else int(t) for t in row])
    signs = tuple(_sign(line, n) for line in section["Signs"])
    return Puzzle(grid, signs)


def _sign(line: str, n: int) -> Sign:
    match = re.fullmatch(r"r(\d)c(\d)\s*([<>])\s*r(\d)c(\d)", line.strip().lower())
    if match is None:
        raise ValueError(f"bad sign {line!r}, expected like r1c1 < r1c2")
    a = (int(match[1]) - 1, int(match[2]) - 1)
    b = (int(match[4]) - 1, int(match[5]) - 1)
    if not all(0 <= i < n for i in (*a, *b)):
        raise ValueError(f"sign {line!r} is off the grid")
    if abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
        raise ValueError(f"sign {line!r} is not between neighbouring cells")
    return Sign(a, b) if match[3] == "<" else Sign(b, a)


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    """The model for a Futoshiki, with the givens already assigned."""
    puzzle = parse(text)
    n = puzzle.size
    numbers = range(1, n + 1)
    model = Model()

    for r in range(n):
        for c in range(n):
            name = cell_name((r, c))
            model.constrain(
                f"{name} holds one number",
                Kind.EXACTLY_ONE,
                [model.literal(name, v) for v in numbers],
                defines=name,
                family="each cell holds one number",
            )
    for v in numbers:
        for i in range(n):
            model.constrain(
                f"{v} once in row {i + 1}",
                Kind.EXACTLY_ONE,
                [model.literal(cell_name((i, c)), v) for c in range(n)],
                family="each number once per row",
            )
            model.constrain(
                f"{v} once in col {i + 1}",
                Kind.EXACTLY_ONE,
                [model.literal(cell_name((r, i)), v) for r in range(n)],
                family="each number once per column",
            )

    for r, row in enumerate(puzzle.grid):
        for c, v in enumerate(row):
            if v:
                model.assign(model.literal(cell_name((r, c)), v), "given", "given")
    for sign in puzzle.signs:
        names = [cell_name(sign.smaller), cell_name(sign.larger)]
        model.relate(sign.label, names, lambda small, large: small < large)
    return model, puzzle


# --- rendering ------------------------------------------------------------


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """Draw the grid with its signs between cells, and pencil marks.

    `steps` are highlighted: numbers placed, and cells that lost options.
    """
    n = puzzle.size
    width = n if n <= PENCIL_MARKS_UP_TO else 1
    placed = {s.var for s in steps if s.asserted}
    narrowed = {s.var for s in steps if not s.asserted}
    between = puzzle.sign_between

    out = [f"\n{BOLD}{title}{RESET}"]
    for r in range(n):
        line = ""
        for c in range(n):
            if c:
                line += f" {between.get(((r, c - 1), (r, c)), ' ')} "
            line += _cell_text(model, cell_name((r, c)), width, n, placed, narrowed)
        out.append(line)
        if r < n - 1:
            arrows = {"<": "^", ">": "v"}
            under = [arrows.get(between.get(((r, c), (r + 1, c)), ""), " ") for c in range(n)]
            out.append("   ".join(a.center(width) for a in under).rstrip())
    return "\n".join(out)


def _cell_text(
    model: Model, name: str, width: int, n: int, placed: set[str], narrowed: set[str]
) -> str:
    value = model.chosen(name)
    if value is not None:
        tint = NEW if name in placed else ""
        return f"{BOLD}{tint}{str(value).center(width)}{RESET}"
    if n > PENCIL_MARKS_UP_TO:
        return ".".center(width)
    marks = "".join(str(model.value_of(lit)) for lit in model.options(name))
    tint = NEW if name in narrowed else FADED
    return f"{tint}{marks.ljust(width)}{RESET}"
