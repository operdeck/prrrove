"""Sudoku expressed as exact cover.

Literals are "cell holds digit". The constraint families are the whole of
Sudoku:
  * each cell holds exactly one digit
  * each digit sits exactly once in each house: row, column, box, and any
    extra houses (NRC Sudoku's grey boxes, X-Sudoku's diagonals)

A plain file is just the grid: 9 x 9 with 3 x 3 boxes, or a 4 x 4 mini
Sudoku with 2 x 2 boxes. A sectioned file can change the houses:

    Givens:
    . . 3 .
    ...
    Boxes:              # Jigsaw Sudoku: a box id per cell, N boxes of N cells
    a a b b
    ...
    Extra:              # extra houses of N cells: per cell '.' or its house ids
    x . . . . . . . y
    . x . . . . . y .
    ...
    . . . . xy . . . .
    ...

That `Extra:` is X-Sudoku: diagonals x and y, with the centre cell on both.
NRC Sudoku's four grey boxes are written the same way.
With `Boxes:` the grid may be any size from 4 to 9.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from math import isqrt

from .core import Kind, Model, Step
from .puzzlefile import read_sections

BLUE = "\033[94m"
RESET = "\033[0m"
WORDS = {"col": "column", "extra": "extra house"}

type Grid = list[list[int]]
type Cell = tuple[int, int]


@dataclass(frozen=True)
class Puzzle:
    """The givens (0 for blank), a box id per cell, and any extra houses: per
    cell '.' or the one-character ids of the extra houses it is in."""

    grid: Grid
    boxes: list[list[str]]
    extra: list[list[str]] | None = None

    @property
    def size(self) -> int:
        return len(self.grid)

    @property
    def jigsaw(self) -> bool:
        return self.boxes != standard_boxes(self.size)

    def houses(self) -> list[tuple[str, str, list[Cell]]]:
        """(family, name, cells) for every house a digit appears once in.

        The one definition of what a Sudoku requires: the compiler, the
        brute force and the pictures all read it.
        """
        n = self.size
        houses = [("row", f"row {r + 1}", [(r, c) for c in range(n)]) for r in range(n)]
        houses += [("col", f"col {c + 1}", [(r, c) for r in range(n)]) for c in range(n)]
        cells_of: dict[str, list[Cell]] = {}
        for r in range(n):
            for c in range(n):
                cells_of.setdefault(self.boxes[r][c], []).append((r, c))
        houses += [("box", f"box {box}", cells) for box, cells in sorted(cells_of.items())]
        houses += [("extra", f"extra house {e}", cells) for e, cells in self.extra_houses().items()]
        return houses

    def extra_houses(self) -> dict[str, list[Cell]]:
        cells_of: dict[str, list[Cell]] = {}
        for r, row in enumerate(self.extra or []):
            for c, ids in enumerate(row):
                for house in ids.strip("."):
                    cells_of.setdefault(house, []).append((r, c))
        return dict(sorted(cells_of.items()))


def cell_name(row: int, col: int) -> str:
    """1-indexed, matching what the grid prints."""
    return f"r{row + 1}c{col + 1}"


def box_size(size: int) -> int:
    """The side of a square box: 3 for a 9 x 9 grid, 2 for 4 x 4."""
    return isqrt(size)


def standard_boxes(size: int) -> list[list[str]]:
    """Square boxes, ids like '1,2' for the box in band 1, stack 2."""
    box = box_size(size)
    return [[f"{r // box + 1},{c // box + 1}" for c in range(size)] for r in range(size)]


def parse(text: str) -> Puzzle:
    """Read a plain grid, or a sectioned file with Givens, Boxes and Extra."""
    if "Givens:" not in text:
        grid = _grid(text.splitlines())
        if len(grid) not in (4, 9):
            raise ValueError(f"grid has {len(grid)} rows, expected 4 or 9")
        return Puzzle(grid, standard_boxes(len(grid)))
    section = read_sections(text)
    grid = _grid(section["Givens"])
    size = len(grid)
    extra = _extra(section["Extra"], size) if "Extra" in section else None
    if "Boxes" not in section:
        if size not in (4, 9):
            raise ValueError(f"grid has {size} rows; without Boxes: it must be 4 or 9")
        return Puzzle(grid, standard_boxes(size), extra)
    boxes = [line.split() for line in section["Boxes"]]
    if not 4 <= size <= 9:
        raise ValueError(f"a jigsaw grid is 4 to 9 cells wide, not {size}")
    if len(boxes) != size or any(len(row) != size for row in boxes):
        raise ValueError(f"Boxes is not {size}x{size}")
    sizes = {box: sum(row.count(box) for row in boxes) for row in boxes for box in row}
    if len(sizes) != size or set(sizes.values()) != {size}:
        raise ValueError(f"Boxes needs {size} boxes of {size} cells, got {sorted(sizes.items())}")
    return Puzzle(grid, boxes, extra)


def _extra(lines: Sequence[str], size: int) -> list[list[str]]:
    extra = [line.split() for line in lines]
    if len(extra) != size or any(len(row) != size for row in extra):
        raise ValueError(f"Extra is not {size}x{size}")
    sizes: dict[str, int] = {}
    for row in extra:
        for ids in row:
            for house in ids.strip("."):
                sizes[house] = sizes.get(house, 0) + 1
    if wrong := sorted(e for e, count in sizes.items() if count != size):
        raise ValueError(f"extra houses {wrong} do not have {size} cells")
    return extra


def _grid(lines: Sequence[str]) -> Grid:
    """Digits are givens; '.' and '0' are blanks; anything else, such as '|'
    and '-' separators, is ignored."""
    grid = []
    for line in lines:
        row = [0 if ch in ".0" else int(ch) for ch in line if ch in ".0123456789"]
        if row:
            grid.append(row)
    size = len(grid)
    for row in grid:
        if len(row) != size:
            raise ValueError(f"a row has {len(row)} cells, expected {size}")
        if any(d > size for d in row):
            raise ValueError(f"digits in a {size} x {size} grid go up to {size}")
    return grid


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    """The model for a Sudoku, with its givens already assigned, and the puzzle read."""
    puzzle = parse(text)
    size = puzzle.size
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

    # Each digit appears exactly once per house.
    for d in digits:
        for family, name, members in puzzle.houses():
            model.constrain(
                f"{d} once in {name}",
                Kind.EXACTLY_ONE,
                [model.literal(cell_name(r, c), d) for r, c in members],
                family=f"each digit once per {WORDS.get(family, family)}",
            )

    for row, col in cells:
        given = puzzle.grid[row][col]
        if given:
            name = cell_name(row, col)
            model.assign(model.literal(name, given), "given", "stated in the puzzle")

    return model, puzzle


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """Draw the grid with its box walls, colouring the cells placed by `steps`.

    Open cells in an extra house show ':' rather than '.'.
    """
    placed = {s.var for s in steps if s.asserted}
    n, boxes = puzzle.size, puzzle.boxes
    extra = {cell for cells in puzzle.extra_houses().values() for cell in cells}

    def wall_below(r: int, c: int) -> bool:
        return r + 1 < n and boxes[r][c] != boxes[r + 1][c]

    def rule(r: int) -> str:
        marks = "".join("--" if r < 0 or wall_below(r, c) else "  " for c in range(n))
        return f"  +{marks[:-1]}+"

    out = [f"\n{title}", rule(-1)]
    for r in range(n):
        line = f"{r + 1} |"
        for c in range(n):
            if c and boxes[r][c] != boxes[r][c - 1]:
                line = line[:-1] + "|"
            name = cell_name(r, c)
            digit = model.chosen(name)
            if digit is None:
                line += ": " if (r, c) in extra else ". "
            elif name in placed:
                line += f"{BLUE}{digit}{RESET} "
            else:
                line += f"{digit} "
        out.append(line[:-1] + "|")
        if r + 1 < n and any(wall_below(r, c) for c in range(n)):
            out.append(rule(r))
    out.append(rule(-1))
    out.append("   " + " ".join(str(c + 1) for c in range(n)))
    return "\n".join(out)
