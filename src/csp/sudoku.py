"""Sudoku expressed as exact cover.

Literals are "cell holds digit". The four constraint families are the whole
of Sudoku:
  * each cell holds exactly one digit
  * each digit sits exactly once in each row
  * ... each column
  * ... each 3x3 box
"""

from .core import Kind, Model

SIZE = 9
BOX = 3
BLUE = "\033[94m"
RESET = "\033[0m"


def cell_name(row: int, col: int) -> str:
    """1-indexed, matching what the grid prints."""
    return f"r{row + 1}c{col + 1}"


def parse(text: str) -> list[list[int]]:
    """Read a 9x9 grid. Digits are givens; '.' and '0' are blanks."""
    grid = []
    for line in text.strip().splitlines():
        if set(line.strip()) <= set("-+|  "):
            continue
        row = [0 if ch in ".0" else int(ch) for ch in line if ch in ".0123456789"]
        if not row:
            continue
        if len(row) != SIZE:
            raise ValueError(f"row has {len(row)} cells, expected {SIZE}: {line!r}")
        grid.append(row)
    if len(grid) != SIZE:
        raise ValueError(f"grid has {len(grid)} rows, expected {SIZE}")
    return grid


def compile_puzzle(text: str) -> tuple[Model, list[list[int]]]:
    grid = parse(text)
    model = Model()

    digits = range(1, SIZE + 1)
    cells = [(r, c) for r in range(SIZE) for c in range(SIZE)]

    # Each cell holds exactly one digit. This constraint is the cell's domain.
    for row, col in cells:
        name = cell_name(row, col)
        model.constrain(
            f"{name} holds one digit",
            Kind.EXACTLY_ONE,
            [model.literal(name, d) for d in digits],
            defines=name,
        )

    # Each digit appears exactly once per row, column and box.
    for d in digits:
        for r in range(SIZE):
            model.constrain(
                f"{d} once in row {r + 1}",
                Kind.EXACTLY_ONE,
                [model.literal(cell_name(r, c), d) for c in range(SIZE)],
            )
        for c in range(SIZE):
            model.constrain(
                f"{d} once in col {c + 1}",
                Kind.EXACTLY_ONE,
                [model.literal(cell_name(r, c), d) for r in range(SIZE)],
            )
        for br in range(BOX):
            for bc in range(BOX):
                members = [
                    model.literal(cell_name(br * BOX + r, bc * BOX + c), d)
                    for r in range(BOX)
                    for c in range(BOX)
                ]
                model.constrain(
                    f"{d} once in box {br + 1},{bc + 1}", Kind.EXACTLY_ONE, members
                )

    for row, col in cells:
        given = grid[row][col]
        if given:
            name = cell_name(row, col)
            model.assign(model.literal(name, given), "given", "stated in the puzzle")

    return model, grid


def render(model: Model, title: str, highlight: set[str] = frozenset()) -> str:
    """Draw the grid, colouring the cells named in `highlight`."""
    rule = "  +------+------+------+"
    out = [f"\n{title}", rule]
    for r in range(SIZE):
        if r and r % BOX == 0:
            out.append(rule)
        line = f"{r + 1} |"
        for c in range(SIZE):
            if c and c % BOX == 0:
                line += "|"
            name = cell_name(r, c)
            digit = model.chosen(name)
            if digit is None:
                line += ". "
            elif name in highlight:
                line += f"{BLUE}{digit}{RESET} "
            else:
                line += f"{digit} "
        out.append(line + "|")
    out.append(rule)
    out.append("  |1 2 3 |4 5 6 |7 8 9 |")
    return "\n".join(out)


def touched_cells(steps) -> set[str]:
    """Cell names newly decided by a batch of log steps."""
    return {s.literal.split("=")[0] for s in steps if s.asserted}
