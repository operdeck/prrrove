"""Calcudoku (KenKen) expressed as exact cover.

An N x N grid holds 1..N once in every row and column. The grid is split into
cages; the numbers in a cage must make its target with its operation:

    7+   sum            12x  product
    2-   difference     2/   quotient (two-cell cages only, larger first)
    4    a one-cell cage simply states its number

Literals are "cell holds number", as in Sudoku. Cells, rows and columns are
EXACTLY_ONE constraints; each cage is one relation over its cells.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cached_property
from itertools import combinations
from math import prod

from .core import Kind, Model, Step
from .puzzlefile import read_sections

type Cell = tuple[int, int]

BOLD = "\033[1m"
NEW = "\033[38;5;21m"  # blue: changed by the step just shown
FADED = "\033[38;5;245m"
RESET = "\033[0m"

# Newspapers print the typographic signs; files may use those or plain ASCII.
OPERATORS = {
    "+": "+",
    "x": "x",
    "*": "x",
    "\u00d7": "x",  # multiplication sign
    "-": "-",
    "\u2212": "-",  # minus sign
    "/": "/",
    "\u00f7": "/",  # division sign
    ":": "/",
}
TWO_CELL_ONLY = {"-", "/"}
PENCIL_MARKS_UP_TO = 7  # larger grids show '.' for open cells to stay narrow


def cell_name(cell: Cell) -> str:
    row, col = cell
    return f"r{row + 1}c{col + 1}"


@dataclass(frozen=True)
class Cage:
    target: int
    operator: str | None  # None for a one-cell cage that states its number
    cells: tuple[Cell, ...]

    @property
    def label(self) -> str:
        return f"{self.target}{self.operator or ''}"

    def holds(self, values: Sequence[int]) -> bool:
        """Whether `values`, one per cell, make the target."""
        match self.operator:
            case None:
                return values[0] == self.target
            case "+":
                return sum(values) == self.target
            case "x":
                return prod(values) == self.target
            case "-":
                return abs(values[0] - values[1]) == self.target
            case "/":
                return max(values) == self.target * min(values)
        raise ValueError(f"unknown operator {self.operator!r}")


@dataclass(frozen=True)
class Puzzle:
    size: int
    cages: tuple[Cage, ...]

    @cached_property
    def cage_at(self) -> dict[Cell, Cage]:
        return {cell: cage for cage in self.cages for cell in cage.cells}


def parse(text: str) -> Puzzle:
    """Read a Calcudoku file: Size, a Grid of cage ids, and each cage's rule.

    Size: 4
    Grid:
    a a b c
    d e b c
    ...
    Cages:
    a: 3-
    b: 24x
    d: 4
    """
    section = read_sections(text)
    for required in ("Size", "Grid", "Cages"):
        if required not in section:
            raise ValueError(f"puzzle file is missing a {required}: section")
    size = int(section["Size"][0])

    grid = [line.split() for line in section["Grid"]]
    if len(grid) != size or any(len(row) != size for row in grid):
        raise ValueError(f"Grid is not {size}x{size}")
    cells_of: dict[str, list[Cell]] = {}
    for r, row in enumerate(grid):
        for c, cage_id in enumerate(row):
            cells_of.setdefault(cage_id, []).append((r, c))

    rules = {}
    for line in section["Cages"]:
        cage_id, _, rule = line.partition(":")
        rules[cage_id.strip()] = rule.strip()
    if missing := sorted(set(cells_of) - set(rules)):
        raise ValueError(f"no rule for cages {missing}")
    if unused := sorted(set(rules) - set(cells_of)):
        raise ValueError(f"cages {unused} are not on the grid")

    cages = tuple(_cage(cage_id, rules[cage_id], cells) for cage_id, cells in cells_of.items())
    return Puzzle(size, cages)


def _cage(cage_id: str, rule: str, cells: list[Cell]) -> Cage:
    symbol = rule[-1:]
    operator = OPERATORS.get(symbol)
    number = rule[:-1] if operator else rule
    if not number.isdigit() or int(number) < 1:
        raise ValueError(f"cage {cage_id}: bad rule {rule!r}, expected like 7+, 12x, 2-, 2/ or 4")
    if operator is None and len(cells) != 1:
        raise ValueError(f"cage {cage_id}: {len(cells)} cells need an operator, not just {rule}")
    if operator in TWO_CELL_ONLY and len(cells) != 2:
        raise ValueError(f"cage {cage_id}: {operator} needs exactly two cells, has {len(cells)}")
    if not _connected(cells):
        raise ValueError(f"cage {cage_id} is not one connected piece")
    return Cage(int(number), operator, tuple(cells))


def _connected(cells: list[Cell]) -> bool:
    remaining = set(cells)
    frontier = [remaining.pop()]
    while frontier:
        r, c = frontier.pop()
        for neighbour in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if neighbour in remaining:
                remaining.remove(neighbour)
                frontier.append(neighbour)
    return not remaining


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    """The model for a Calcudoku, with one-cell cages already assigned."""
    puzzle = parse(text)
    n = puzzle.size
    numbers = range(1, n + 1)
    cells = [(r, c) for r in range(n) for c in range(n)]
    model = Model()

    for cell in cells:
        name = cell_name(cell)
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

    for cage in puzzle.cages:
        names = [cell_name(cell) for cell in cage.cells]
        if cage.operator is None:
            model.assign(model.literal(names[0], cage.target), "given", "one-cell cage")
        else:
            model.relate(f"{cage.label} cage {' '.join(names)}", names, _cage_test(cage))
    return model, puzzle


def _cage_test(cage: Cage) -> Callable[..., bool]:
    """The cage's arithmetic, plus distinct numbers where its cells share a line.

    The second part repeats the row and column rules, but inside the relation
    it lets arc consistency rule out combinations like 3+3 in one row.
    """
    clashes = [
        (i, j)
        for i, j in combinations(range(len(cage.cells)), 2)
        if cage.cells[i][0] == cage.cells[j][0] or cage.cells[i][1] == cage.cells[j][1]
    ]

    def holds(*values: int) -> bool:
        return all(values[i] != values[j] for i, j in clashes) and cage.holds(values)

    return holds


# --- rendering ------------------------------------------------------------


def render(model: Model, puzzle: Puzzle, title: str, steps: Sequence[Step] = ()) -> str:
    """Draw the grid with cage walls, cage labels, and pencil marks.

    Open cells list the numbers still possible, as a person pencils them in.
    `steps` are highlighted: numbers placed, and cells that lost options.
    """
    n = puzzle.size
    width = max(5, n) if n <= PENCIL_MARKS_UP_TO else 5
    placed = {s.var for s in steps if s.asserted}
    narrowed = {s.var for s in steps if not s.asserted}
    first_cell = {cage.cells[0]: cage for cage in puzzle.cages}

    def same_cage(a: Cell, b: Cell) -> bool:
        return puzzle.cage_at[a] is puzzle.cage_at[b]

    out = [f"\n{BOLD}{title}{RESET}"]
    for r in range(n + 1):
        border = "+"
        for c in range(n):
            walled = r in (0, n) or not same_cage((r - 1, c), (r, c))
            border += ("-" if walled else " ") * width + "+"
        out.append(border)
        if r == n:
            break
        labels, values = "", ""
        for c in range(n):
            side = "|" if c == 0 or not same_cage((r, c - 1), (r, c)) else " "
            cage = first_cell.get((r, c))
            labels += side + (cage.label if cage else "").ljust(width)
            values += side + _cell_text(model, cell_name((r, c)), width, n, placed, narrowed)
        out += [labels + "|", values + "|"]
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
