"""Murdoku expressed as exact cover.

The variables are *people*, not squares: each person picks one square. That
is the shape the puzzle actually has - "exactly one figure per row and per
column" puts seven figures on a 7x7 board, it does not fill every row with
all seven.

Literals are "person stands on square". The constraint families:
  * each person stands on exactly one square
  * each square holds at most one person   (many squares stay empty)
  * each row holds exactly one person
  * each column holds exactly one person

Positional clues then either delete literals outright ("Jos is in the
kitchen") or become pairwise relations ("Jos is left of Otto").
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .core import Kind, Model

RESET = "\033[0m"
BOLD = "\033[1m"
INK = "\033[38;5;233m"
# Pastel backgrounds, in the spirit of the printed board.
PALETTE = [217, 223, 157, 183, 153, 158, 222, 211, 195]


def _bg(colour: int) -> str:
    return f"\033[48;5;{colour}m"


@dataclass(frozen=True, order=True)
class Square:
    row: int
    col: int

    def __str__(self) -> str:
        return f"r{self.row + 1}c{self.col + 1}"

    __repr__ = __str__


def steps_between(a: Square, b: Square) -> int:
    """Orthogonal step count, as the puzzle counts distance."""
    return abs(a.row - b.row) + abs(a.col - b.col)


@dataclass
class Board:
    size: int
    regions: list[list[int]]
    region_names: dict[int, str]
    objects: dict[str, Square]
    people: list[str]

    def __post_init__(self) -> None:
        if len(self.people) != self.size:
            raise ValueError(
                f"{len(self.people)} people on a {self.size}x{self.size} board; "
                "one per row and column means these must match"
            )
        occupied = set(self.objects.values())
        self.free = [
            Square(r, c)
            for r in range(self.size)
            for c in range(self.size)
            if Square(r, c) not in occupied
        ]

    def region_of(self, square: Square) -> int:
        return self.regions[square.row][square.col]

    def region_id(self, name: str) -> int:
        for rid, rname in self.region_names.items():
            if rname == name:
                return rid
        raise ValueError(f"unknown region {name!r}; have {sorted(self.region_names.values())}")


# --- clue vocabulary ------------------------------------------------------
# Each entry either filters one person's squares, or relates two people.

FILTERS: dict[str, Callable[..., Callable[[Square], bool]]] = {
    # in_region <person> <region>
    "in_region": lambda board, region: (
        lambda sq: board.region_of(sq) == board.region_id(region)
    ),
    # next_to <person> <object>
    "next_to": lambda board, obj: (
        lambda sq: steps_between(sq, board.objects[obj]) == 1
    ),
}

RELATIONS: dict[str, Callable[..., Callable[[Square, Square], bool]]] = {
    # same_region <a> <b>
    "same_region": lambda board: (
        lambda a, b: board.region_of(a) == board.region_of(b)
    ),
    # left_of <a> <b>        a is somewhere left of b
    "left_of": lambda board: (lambda a, b: a.col < b.col),
    # above <a> <b> <n>      a is exactly n rows above b
    "above": lambda board, n: (lambda a, b: a.row + int(n) == b.row),
    # within <a> <b> <n>     at most n steps apart
    "within": lambda board, n: (lambda a, b: steps_between(a, b) <= int(n)),
}


def compile_puzzle(board: Board, clues: list[tuple[str, list[str]]]) -> Model:
    model = Model()

    for person in board.people:
        model.constrain(
            f"{person} stands somewhere",
            Kind.EXACTLY_ONE,
            [model.literal(person, sq) for sq in board.free],
            defines=person,
        )

    for sq in board.free:
        model.constrain(
            f"{sq} holds at most one",
            Kind.AT_MOST_ONE,
            [model.literal(p, sq) for p in board.people],
        )

    for r in range(board.size):
        row_squares = [sq for sq in board.free if sq.row == r]
        model.constrain(
            f"row {r + 1} holds one person",
            Kind.EXACTLY_ONE,
            [model.literal(p, sq) for p in board.people for sq in row_squares],
        )
    for c in range(board.size):
        col_squares = [sq for sq in board.free if sq.col == c]
        model.constrain(
            f"col {c + 1} holds one person",
            Kind.EXACTLY_ONE,
            [model.literal(p, sq) for p in board.people for sq in col_squares],
        )

    for kind, args in clues:
        if kind in FILTERS:
            person, rest = args[0], args[1:]
            allowed = FILTERS[kind](board, *rest)
            label = " ".join([kind, *rest])
            for sq in board.free:
                if not allowed(sq):
                    model.eliminate(model.literal(person, sq), "clue", label)
        elif kind in RELATIONS:
            a, b, rest = args[0], args[1], args[2:]
            model.relate(
                " ".join([a, kind, b, *rest]), a, b, RELATIONS[kind](board, *rest)
            )
        else:
            raise ValueError(f"unknown clue {kind!r}")

    return model


# --- rendering ------------------------------------------------------------


def render(board: Board, model: Model, title: str, highlight: set[str] = frozenset()) -> str:
    """Draw the board, one colour per region, 4 columns per square."""
    glyph = {name: sq for name, sq in board.objects.items()}
    at: dict[Square, str] = {}
    for person in board.people:
        square = model.chosen(person)
        if square is not None:
            at[square] = person

    out = [f"\n{BOLD}{title}{RESET}"]
    out.append("   " + "".join(f"{c + 1:^4}" for c in range(board.size)))
    for r in range(board.size):
        line = f"{r + 1:>2} "
        for c in range(board.size):
            sq = Square(r, c)
            colour = _bg(PALETTE[board.region_of(sq) % len(PALETTE)])
            obj = next((n for n, s in glyph.items() if s == sq), None)
            if obj is not None:
                body = f"{INK} ## "
            elif sq in at:
                person = at[sq]
                tint = "\033[38;5;21m" if person in highlight else INK
                body = f"{tint}{person[:3]:^4}"
            else:
                body = f"{INK} .  "
            line += colour + body + RESET
        out.append(line)

    out.append("")
    for rid in sorted(board.region_names):
        swatch = _bg(PALETTE[rid % len(PALETTE)]) + "   " + RESET
        out.append(f"  {swatch} {board.region_names[rid]}")
    out.append(f"\n  {INK}##{RESET} object   .  empty")
    objects = ", ".join(f"{n} {s}" for n, s in sorted(board.objects.items()))
    out.append(f"  objects: {objects}")
    return "\n".join(out)


def open_squares(board: Board, model: Model) -> dict[str, list[Square]]:
    """Remaining candidate squares per person - the working set."""
    return {
        p: sorted(model.value_of(l) for l in model.options(p)) for p in board.people
    }


def touched_people(steps) -> set[str]:
    return {s.literal.split("=")[0] for s in steps if s.asserted}
