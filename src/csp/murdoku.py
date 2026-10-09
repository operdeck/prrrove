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
kitchen") or become relations between two or three people ("Jos is left of
Otto", "Luna is furthest from Mao").
"""

from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass, field

from .core import Kind, LiteralId, Model

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


def knight_move(a: Square, b: Square) -> bool:
    """Two squares straight, then one to the side."""
    return {abs(a.row - b.row), abs(a.col - b.col)} == {1, 2}


@dataclass
class Board:
    """The fixed layout: regions, things on the board, and who is playing.

    `objects` block their squares; `furniture` (such as a bank to lie on)
    does not. Several things may share a name, like three suitcases.
    """

    size: int
    regions: list[list[int]]
    region_names: dict[int, str]
    objects: dict[str, list[Square]]
    people: list[str]
    groups: dict[str, list[str]] = field(default_factory=dict)
    furniture: dict[str, list[Square]] = field(default_factory=dict)
    free: list[Square] = field(init=False)
    borders: set[frozenset[int]] = field(init=False)

    def __post_init__(self) -> None:
        if len(self.people) != self.size:
            raise ValueError(
                f"{len(self.people)} people on a {self.size}x{self.size} board; "
                "one per row and column means these must match"
            )
        squares = [Square(r, c) for r in range(self.size) for c in range(self.size)]
        self.free = [sq for sq in squares if sq not in self.blocked]
        self.borders = {
            frozenset((self.region_of(sq), self.region_of(nb)))
            for sq in squares
            for nb in (Square(sq.row, sq.col + 1), Square(sq.row + 1, sq.col))
            if nb.row < self.size
            and nb.col < self.size
            and self.region_of(sq) != self.region_of(nb)
        }

    def region_of(self, square: Square) -> int:
        return self.regions[square.row][square.col]

    def region_id(self, name: str) -> int:
        for rid, rname in self.region_names.items():
            if rname == name:
                return rid
        raise ValueError(f"unknown region {name!r}; have {sorted(self.region_names.values())}")

    def region_ids(self, names: Iterable[str]) -> set[int]:
        """Region ids for a mix of region names and group names."""
        return {
            self.region_id(member) for name in names for member in self.groups.get(name, [name])
        }

    def regions_touch(self, a: int, b: int) -> bool:
        """Share a side somewhere; a shared corner does not count."""
        return frozenset((a, b)) in self.borders

    @property
    def blocked(self) -> set[Square]:
        return {sq for squares in self.objects.values() for sq in squares}

    def squares_of(self, names: Iterable[str]) -> set[Square]:
        """Every square holding an object or piece of furniture of these names."""
        found: set[Square] = set()
        for name in names:
            if name not in self.objects and name not in self.furniture:
                known = sorted([*self.objects, *self.furniture])
                raise ValueError(f"nothing called {name!r} on the board; have {known}")
            found.update(self.objects.get(name, []), self.furniture.get(name, []))
        return found


# --- clue vocabulary ------------------------------------------------------
# A filter narrows one person's squares; a relation links two people's.
# Each builder takes the board plus the clue's extra words.

type Clue = tuple[str, list[str]]
type SquareTest = Callable[[Square], bool]
type PairTest = Callable[[Square, Square], bool]


def _in_region(board: Board, *names: str) -> SquareTest:
    ids = board.region_ids(names)
    return lambda sq: board.region_of(sq) in ids


def _outside(board: Board, *names: str) -> SquareTest:
    ids = board.region_ids(names)
    return lambda sq: board.region_of(sq) not in ids


def _next_to(board: Board, *things: str) -> SquareTest:
    targets = board.squares_of(things)
    return lambda sq: any(steps_between(sq, t) == 1 for t in targets)


def _knight_from(board: Board, *things: str) -> SquareTest:
    targets = board.squares_of(things)
    return lambda sq: any(knight_move(sq, t) for t in targets)


def _on(board: Board, *things: str) -> SquareTest:
    targets = board.squares_of(things)
    return lambda sq: sq in targets


def _same_region(board: Board) -> PairTest:
    return lambda a, b: board.region_of(a) == board.region_of(b)


def _different_region(board: Board) -> PairTest:
    return lambda a, b: board.region_of(a) != board.region_of(b)


def _apart(board: Board) -> PairTest:
    def test(a: Square, b: Square) -> bool:
        ra, rb = board.region_of(a), board.region_of(b)
        return ra != rb and not board.regions_touch(ra, rb)

    return test


def _left_of(board: Board) -> PairTest:
    return lambda a, b: a.col < b.col


def _above(board: Board, rows: str | None = None) -> PairTest:
    if rows is None:
        return lambda a, b: a.row < b.row
    gap = int(rows)
    return lambda a, b: a.row + gap == b.row


def _within(board: Board, steps: str) -> PairTest:
    limit = int(steps)
    return lambda a, b: steps_between(a, b) <= limit


def _at_least(board: Board, steps: str) -> PairTest:
    limit = int(steps)
    return lambda a, b: steps_between(a, b) >= limit


FILTERS: dict[str, Callable[..., SquareTest]] = {
    "in_region": _in_region,  # in_region <person> <region or group>...
    "outside": _outside,  # outside <person> <region or group>...
    "next_to": _next_to,  # next_to <person> <thing>...: beside any of them
    "knight_from": _knight_from,  # knight_from <person> <thing>...: a knight's move away
    "on": _on,  # on <person> <furniture>...
}

RELATIONS: dict[str, Callable[..., PairTest]] = {
    "same_region": _same_region,  # same_region <a> <b>
    "different_region": _different_region,  # different_region <a> <b>
    "apart": _apart,  # apart <a> <b>: different regions that do not border
    "left_of": _left_of,  # left_of <a> <b>: a somewhere left of b
    "above": _above,  # above <a> <b> [n]: exactly n rows above, or anywhere above
    "within": _within,  # within <a> <b> <n>: at most n steps apart
    "at_least": _at_least,  # at_least <a> <b> <n>: at least n steps apart
}

# Clues about everyone else, expanded to one relation per other person.
GROUP_CLUES = {
    "alone": 1,  # alone <a>: nobody else in a's region
    "furthest": 2,  # furthest <a> <b>: a strictly further from b than anyone
}


def compile_puzzle(board: Board, clues: Iterable[Clue]) -> Model:
    """The model for a Murdoku board and its clues."""
    model = Model()
    _add_board_rules(model, board)
    for kind, args in clues:
        _add_clue(model, board, kind, args)
    return model


def _add_board_rules(model: Model, board: Board) -> None:
    for person in board.people:
        model.constrain(
            f"{person} stands somewhere",
            Kind.EXACTLY_ONE,
            [model.literal(person, sq) for sq in board.free],
            defines=person,
            family="each person stands on one square",
        )
    for sq in board.free:
        model.constrain(
            f"{sq} holds at most one",
            Kind.AT_MOST_ONE,
            [model.literal(p, sq) for p in board.people],
            family="each square holds at most one person",
        )
    for i in range(board.size):
        model.constrain(
            f"row {i + 1} holds one person",
            Kind.EXACTLY_ONE,
            _anyone_on(model, board, [sq for sq in board.free if sq.row == i]),
            family="each row holds one person",
        )
    for i in range(board.size):
        model.constrain(
            f"col {i + 1} holds one person",
            Kind.EXACTLY_ONE,
            _anyone_on(model, board, [sq for sq in board.free if sq.col == i]),
            family="each column holds one person",
        )


def _anyone_on(model: Model, board: Board, squares: list[Square]) -> list[LiteralId]:
    return [model.literal(p, sq) for p in board.people for sq in squares]


def _add_clue(model: Model, board: Board, kind: str, args: list[str]) -> None:
    arity = 1 if kind in FILTERS else 2 if kind in RELATIONS else GROUP_CLUES.get(kind)
    if arity is None:
        raise ValueError(f"unknown clue {kind!r}")
    for who in args[:arity]:
        if who not in board.people:
            raise ValueError(f"clue {kind} {' '.join(args)} names unknown person {who!r}")

    if kind in FILTERS:
        person, *rest = args
        allowed = FILTERS[kind](board, *rest)
        label = " ".join([kind, *args])
        for sq in board.free:
            if not allowed(sq):
                model.eliminate(model.literal(person, sq), "clue", label)
    elif kind in RELATIONS:
        a, b, *rest = args
        model.relate(" ".join([a, kind, b, *rest]), (a, b), RELATIONS[kind](board, *rest))
    elif kind == "alone":
        (a,) = args
        for p in board.people:
            if p != a:
                name = f"{a} alone in region, so not with {p}"
                model.relate(name, (a, p), _different_region(board))
    elif kind == "furthest":
        a, b = args
        for p in board.people:
            if p not in (a, b):
                model.relate(f"{a} further from {b} than {p}", (a, b, p), _further)


def _further(a: Square, b: Square, other: Square) -> bool:
    return steps_between(a, b) > steps_between(other, b)


# --- rendering ------------------------------------------------------------


def render(board: Board, model: Model, title: str, highlight: Collection[str] = frozenset()) -> str:
    """Draw the board, one colour per region, 4 columns per square."""
    blocked = board.blocked
    furnished = board.squares_of(board.furniture)
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
            if sq in blocked:
                body = f"{INK} ## "
            elif sq in at:
                person = at[sq]
                tint = "\033[38;5;21m" if person in highlight else INK
                body = f"{tint}{person[:3]:^4}"
            elif sq in furnished:
                body = f"{INK} =  "
            else:
                body = f"{INK} .  "
            line += colour + body + RESET
        out.append(line)

    out.append("")
    for rid in sorted(board.region_names):
        swatch = _bg(PALETTE[rid % len(PALETTE)]) + "   " + RESET
        out.append(f"  {swatch} {board.region_names[rid]}")
    out.append(f"\n  {INK}##{RESET} object   =  furniture   .  empty")
    for label, things in (("objects", board.objects), ("furniture", board.furniture)):
        if things:
            listed = ", ".join(
                f"{name} {' '.join(map(str, sorted(squares)))}"
                for name, squares in sorted(things.items())
            )
            out.append(f"  {label}: {listed}")
    return "\n".join(out)


def open_squares(board: Board, model: Model) -> dict[str, list[Square]]:
    """Remaining candidate squares per person - the working set."""
    return {p: sorted(model.value_of(lit) for lit in model.options(p)) for p in board.people}
