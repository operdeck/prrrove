"""Murdoku expressed as exact cover.

The variables are *people*, not squares: each person picks one square. That
is the shape the puzzle actually has: at most one figure per row and column.
When the number of people matches the board width, every row and column is
occupied; on larger boards, some may stay empty.

Literals are "person stands on square". The constraint families:
  * each person stands on exactly one square
  * each square holds at most one person   (many squares stay empty)
  * each row holds exactly one person
  * each column holds exactly one person

Positional clues then either delete literals outright ("Jos is in the
kitchen") or become relations between two or three people ("Jos is left of
Otto", "Luna is furthest from Mao").
"""

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .core import Kind, Model, Step

RESET = "\033[0m"
BOLD = "\033[1m"
INK = "\033[38;5;233m"
NEW = "\033[38;5;21m"  # blue: changed by the step just shown
FADED = "\033[38;5;245m"
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

    `regions` holds a short region id per square (a letter, say) and
    `region_names` maps each id to its name. `objects` block their squares;
    `furniture` (such as a bank to lie on) does not. Several things may share
    a name, like three suitcases. `doors` maps names to edges between adjacent
    cells in different regions; a door is not itself a square. `colours`
    (region id -> '#RRGGBB') and `hatched` (region ids) only affect pictures.

    `rules` are clues that come with the board rather than the puzzle, such
    as "only Luna can be in the water"; they are not numbered.
    """

    size: int
    regions: list[list[str]]
    region_names: dict[str, str]
    objects: dict[str, list[Square]]
    people: list[str]
    groups: dict[str, list[str]] = field(default_factory=dict)
    furniture: dict[str, list[Square]] = field(default_factory=dict)
    colours: dict[str, str] = field(default_factory=dict)
    hatched: set[str] = field(default_factory=set)
    rules: list["Clue"] = field(default_factory=list)
    doors: dict[str, list[tuple[Square, Square]]] = field(default_factory=dict)
    free: list[Square] = field(init=False)
    borders: set[frozenset[str]] = field(init=False)

    def __post_init__(self) -> None:
        if not self.people or len(self.people) > self.size:
            raise ValueError(
                f"{len(self.people)} people on a {self.size}x{self.size} board; "
                f"the number of people must be between 1 and {self.size}"
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
        if door_names := set(self.doors) & (set(self.objects) | set(self.furniture)):
            raise ValueError(f"door names overlap objects or furniture: {sorted(door_names)}")
        for name, edges in self.doors.items():
            if not edges:
                raise ValueError(f"door {name!r} has no edges")
            for first, second in edges:
                if any(
                    square.row not in range(self.size) or square.col not in range(self.size)
                    for square in (first, second)
                ):
                    raise ValueError(f"door {name!r} is off the grid: {first}-{second}")
                if steps_between(first, second) != 1:
                    raise ValueError(f"door {name!r} must separate neighboring squares")
                if self.region_of(first) == self.region_of(second):
                    raise ValueError(f"door {name!r} must be on a region boundary")

    def region_of(self, square: Square) -> str:
        return self.regions[square.row][square.col]

    def region_id(self, name: str) -> str:
        for rid, rname in self.region_names.items():
            if rname == name:
                return rid
        raise ValueError(f"unknown region {name!r}; have {sorted(self.region_names.values())}")

    def region_ids(self, names: Iterable[str]) -> set[str]:
        """Region ids for a mix of region names and group names."""
        return {
            self.region_id(member) for name in names for member in self.groups.get(name, [name])
        }

    def regions_touch(self, a: str, b: str) -> bool:
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
    """Beside one of the things, in the same region: Murdoku's general rule is
    that 'next to' never crosses a region boundary. A door is an edge, so
    either square on its sides counts, even across a region boundary."""
    targets: set[Square] = set()
    doors: set[tuple[Square, Square]] = set()
    for thing in things:
        if thing in board.doors:
            doors.update(board.doors[thing])
        else:
            targets.update(board.squares_of([thing]))

    def test(square: Square) -> bool:
        beside_door = any(square in edge for edge in doors)
        beside_thing = any(
            steps_between(square, target) == 1
            and board.region_of(target) == board.region_of(square)
            for target in targets
        )
        return beside_door or beside_thing

    return test


def _knight_from(board: Board, *things: str) -> SquareTest:
    targets = board.squares_of(things)
    return lambda sq: any(knight_move(sq, t) for t in targets)


def _not_next_to(board: Board, *things: str) -> SquareTest:
    beside = _next_to(board, *things)
    return lambda sq: not beside(sq)


def _on(board: Board, *things: str) -> SquareTest:
    targets = board.squares_of(things)
    return lambda sq: sq in targets


def _not_on(board: Board, *things: str) -> SquareTest:
    targets = board.squares_of(things)
    return lambda sq: sq not in targets


def _in_corner(board: Board) -> SquareTest:
    corners = {
        Square(0, 0),
        Square(0, board.size - 1),
        Square(board.size - 1, 0),
        Square(board.size - 1, board.size - 1),
    }
    return lambda sq: sq in corners


def _same_region(board: Board) -> PairTest:
    return lambda a, b: board.region_of(a) == board.region_of(b)


def _different_region(board: Board) -> PairTest:
    return lambda a, b: board.region_of(a) != board.region_of(b)


def _apart(board: Board) -> PairTest:
    def test(a: Square, b: Square) -> bool:
        ra, rb = board.region_of(a), board.region_of(b)
        return ra != rb and not board.regions_touch(ra, rb)

    return test


def _left_of(board: Board, columns: str | None = None) -> PairTest:
    if columns is not None:
        gap = int(columns)
        if gap < 1:
            raise ValueError("left_of column gap must be at least 1")
        return lambda a, b: a.col + gap == b.col
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
    "not_next_to": _not_next_to,  # not_next_to <person> <thing>...: beside none of them
    "knight_from": _knight_from,  # knight_from <person> <thing>...: a knight's move away
    "on": _on,  # on <person> <furniture>...
    "not_on": _not_on,  # not_on <person> <furniture>...
    "in_corner": _in_corner,  # in_corner <person>
}

RELATIONS: dict[str, Callable[..., PairTest]] = {
    # No "two people side by side": with one person per row and column it never holds.
    "same_region": _same_region,  # same_region <a> <b>
    "different_region": _different_region,  # different_region <a> <b>
    "apart": _apart,  # apart <a> <b>: different regions that do not border
    "left_of": _left_of,  # left_of <a> <b> [n]: somewhere left, or exactly n columns left
    "above": _above,  # above <a> <b> [n]: exactly n rows above, or anywhere above
    "within": _within,  # within <a> <b> <n>: at most n steps apart
    "at_least": _at_least,  # at_least <a> <b> <n>: at least n steps apart
}

# Clues about everyone else, expanded to one relation per other person.
GROUP_CLUES = {
    "alone": 1,  # alone <a>: nobody else in a's region
    "furthest": 2,  # furthest <a> <b>: a strictly further from b than anyone
}

# exactly <n> <clue> ; <clue> ...: exactly n of the listed clues hold. Each
# listed clue is a filter or a relation; together they may name at most
# COUNTED_PEOPLE people, since the engine tries every combination of their squares.
COUNTING = "exactly"
COUNTED_PEOPLE = 3


def counted(args: Sequence[str]) -> tuple[int, list[Clue]]:
    """A counting clue's arguments: '2 next_to Tim boom ; left_of Jos Otto'
    -> (2, [('next_to', ['Tim', 'boom']), ('left_of', ['Jos', 'Otto'])])."""
    if not args or not args[0].isdigit():
        raise ValueError(f"{COUNTING} needs a count first, as in '{COUNTING} 1 <clue> ; <clue>'")
    parts: list[Clue] = []
    words: list[str] = []
    for word in [*args[1:], ";"]:
        if word != ";":
            words.append(word)
        elif words:
            kind, *rest = words
            parts.append((kind, rest))
            words = []
    return int(args[0]), parts


@dataclass(frozen=True)
class Condition:
    """What one clue requires: `test(*squares)` of `people`, in order.

    This is the puzzle's meaning, independent of how it is solved: the
    compiler turns it into the model, the brute-force checker tests it
    directly. `kind` and `args` are the clue it came from, `number` its
    place in the clue list (None for a board rule).
    """

    label: str
    people: tuple[str, ...]
    test: Callable[..., bool]
    kind: str = ""
    args: tuple[str, ...] = ()
    number: int | None = None


def conditions(board: Board, clues: Iterable[Clue]) -> list[Condition]:
    """The board's rules and every clue, as conditions on one, two or three people."""
    out: list[Condition] = []
    for kind, args in board.rules:
        out += _conditions(board, kind, args, None)
    for number, (kind, args) in enumerate(clues, 1):
        out += _conditions(board, kind, args, number)
    return out


def _conditions(board: Board, kind: str, args: list[str], number: int | None) -> list[Condition]:
    if kind == COUNTING:
        return [_counting(board, args, number)]
    if kind == "only_on":
        if len(args) < 2:
            raise ValueError("only_on needs a person and at least one furniture name")
        person, *furniture = args
        if person not in board.people:
            raise ValueError(f"clue only_on {' '.join(args)} names unknown person {person!r}")
        unknown = set(furniture) - set(board.furniture)
        if unknown:
            raise ValueError(f"only_on needs furniture; unknown furniture {sorted(unknown)}")
        targets = board.squares_of(furniture)
        label = " ".join([kind, *args])
        conditions = [
            Condition(label, (person,), lambda sq: sq in targets, kind, tuple(args), number)
        ]
        conditions.extend(
            Condition(label, (other,), lambda sq: sq not in targets, kind, tuple(args), number)
            for other in board.people
            if other != person
        )
        return conditions
    arity = 1 if kind in FILTERS else 2 if kind in RELATIONS else GROUP_CLUES.get(kind)
    if arity is None:
        raise ValueError(f"unknown clue {kind!r}")
    for who in args[:arity]:
        if who not in board.people:
            raise ValueError(f"clue {kind} {' '.join(args)} names unknown person {who!r}")

    def made(label: str, people: tuple[str, ...], test: Callable[..., bool]) -> Condition:
        return Condition(label, people, test, kind, tuple(args), number)

    if kind in FILTERS:
        person, *rest = args
        return [made(" ".join([kind, *args]), (person,), FILTERS[kind](board, *rest))]
    if kind in RELATIONS:
        a, b, *rest = args
        return [made(" ".join([a, kind, b, *rest]), (a, b), RELATIONS[kind](board, *rest))]
    if kind == "alone":
        (a,) = args
        return [
            made(f"{a} alone in region, so not with {p}", (a, p), _different_region(board))
            for p in board.people
            if p != a
        ]
    a, b = args
    return [
        made(f"{a} further from {b} than {p}", (a, b, p), _further)
        for p in board.people
        if p not in (a, b)
    ]


def _further(a: Square, b: Square, other: Square) -> bool:
    return steps_between(a, b) > steps_between(other, b)


def _counting(board: Board, args: list[str], number: int | None) -> Condition:
    """One condition over everyone the listed clues name: exactly n of them hold."""
    n, parts = counted(args)
    if not 0 <= n <= len(parts):
        raise ValueError(f"{COUNTING} {n} of {len(parts)} clues can never hold")
    subs: list[Condition] = []
    for kind, rest in parts:
        if kind not in FILTERS and kind not in RELATIONS:
            raise ValueError(f"{COUNTING} can count simple clues only, not {kind!r}")
        (sub,) = _conditions(board, kind, rest, None)
        subs.append(sub)
    people = tuple(dict.fromkeys(p for sub in subs for p in sub.people))
    if len(people) > COUNTED_PEOPLE:
        raise ValueError(
            f"{COUNTING} names {len(people)} people; at most {COUNTED_PEOPLE} are supported"
        )

    def test(*squares: Square) -> bool:
        at = dict(zip(people, squares, strict=True))
        return sum(sub.test(*(at[p] for p in sub.people)) for sub in subs) == n

    label = f"{COUNTING} {n} of: {'; '.join(sub.label for sub in subs)}"
    return Condition(label, people, test, COUNTING, tuple(args), number)


def compile_puzzle(board: Board, clues: Iterable[Clue]) -> Model:
    """The model for a Murdoku board and its clues.

    A condition on one person is applied straight away, ruling out the
    squares that fail it; a condition on several people becomes a relation.
    """
    model = Model()
    _add_board_rules(model, board)
    for condition in conditions(board, clues):
        if len(condition.people) == 1:
            (person,) = condition.people
            for sq in board.free:
                if not condition.test(sq):
                    model.eliminate(
                        model.literal(person, sq),
                        "clue",
                        condition.label,
                        sources=(condition.label,),
                    )
        else:
            model.relate(condition.label, condition.people, condition.test)
    return model


@dataclass(frozen=True)
class BoardRule:
    """One constraint every Murdoku has, and what it is `about`:
    ('person', name), ('square', Square), ('row', i) or ('col', i), 0-based.

    `compile_puzzle` builds the model from these, so a reader can look a
    constraint's meaning up by name instead of parsing the name.
    """

    name: str
    kind: Kind
    family: str
    about: tuple[str, Any]
    options: tuple[tuple[str, Square], ...]  # (person, square) pairs


def board_rules(board: Board) -> list[BoardRule]:
    people, free = board.people, board.free
    line_kind = Kind.EXACTLY_ONE if len(people) == board.size else Kind.AT_MOST_ONE
    line_capacity = "one person" if line_kind is Kind.EXACTLY_ONE else "at most one person"
    rules = [
        BoardRule(
            f"{p} stands somewhere",
            Kind.EXACTLY_ONE,
            "each person stands on one square",
            ("person", p),
            tuple((p, sq) for sq in free),
        )
        for p in people
    ]
    rules += [
        BoardRule(
            f"{sq} holds at most one",
            Kind.AT_MOST_ONE,
            "each square holds at most one person",
            ("square", sq),
            tuple((p, sq) for p in people),
        )
        for sq in free
    ]
    for line, word in (("row", "row"), ("col", "column")):
        rules += [
            BoardRule(
                f"{line} {i + 1} holds {line_capacity}",
                line_kind,
                f"each {word} holds {line_capacity}",
                (line, i),
                tuple(
                    (p, sq)
                    for p in people
                    for sq in free
                    if (sq.row if line == "row" else sq.col) == i
                ),
            )
            for i in range(board.size)
        ]
    return rules


def _add_board_rules(model: Model, board: Board) -> None:
    for rule in board_rules(board):
        person = rule.about[1] if rule.about[0] == "person" else None
        model.constrain(
            rule.name,
            rule.kind,
            [model.literal(p, sq) for p, sq in rule.options],
            defines=person,
            family=rule.family,
        )


# --- rendering ------------------------------------------------------------


def render(board: Board, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """Draw the board, one colour per region, 4 columns per square.

    A square nobody can stand on any more is crossed out, as a person would
    on paper. `steps`, the deductions just made, are highlighted: people
    placed, squares newly crossed out, and whose options narrowed.
    """
    blocked = board.blocked
    furnished = board.squares_of(board.furniture)
    reachable = _reachable(board, model)
    shade = {rid: PALETTE[i % len(PALETTE)] for i, rid in enumerate(board.region_names)}
    placed = {s.var for s in steps if s.asserted}
    eliminated = {s.value for s in steps if not s.asserted}
    at: dict[Square, str] = {}
    for person in board.people:
        square = model.chosen(person)
        if square is not None:
            at[square] = person
    finished = len(at) == len(board.people)  # crosses are a working aid; drop them at the end

    out = [f"\n{BOLD}{title}{RESET}"]
    out.append("   " + "".join(f"{c + 1:^4}" for c in range(board.size)))
    for r in range(board.size):
        line = f"{r + 1:>2} "
        for c in range(board.size):
            sq = Square(r, c)
            colour = _bg(shade[board.region_of(sq)])
            if sq in blocked:
                body = f"{INK} ## "
            elif sq in at:
                person = at[sq]
                tint = NEW if person in placed else INK
                body = f"{tint}{person[:3]:^4}"
            elif sq not in reachable and not finished:
                tint = f"{BOLD}{NEW}" if sq in eliminated else FADED
                body = f"{tint} x  "
            elif sq in furnished:
                body = f"{INK} =  "
            else:
                body = f"{INK} .  "
            line += colour + body + RESET
        out.append(line)

    if not finished:
        open_count = len(reachable - set(at))
        empty_count = len(board.free) - len(at)
        out.append(f"\n  {open_count} of {empty_count} empty squares still possible for someone")
    out += _narrowed(board, model, steps)

    out.append("")
    for rid, name in board.region_names.items():
        swatch = _bg(shade[rid]) + "   " + RESET
        out.append(f"  {swatch} {name}")
    out.append(f"\n  {INK}##{RESET} object   =  furniture   .  open   x  nobody can stand here")
    out.append(f"  {NEW}blue{RESET}: changed by this step")
    for label, things in (("objects", board.objects), ("furniture", board.furniture)):
        if things:
            listed = ", ".join(
                f"{name} {' '.join(map(str, sorted(squares)))}"
                for name, squares in sorted(things.items())
            )
            out.append(f"  {label}: {listed}")
    if board.doors:
        listed = ", ".join(
            f"{name} {' '.join(f'{first}-{second}' for first, second in edges)}"
            for name, edges in sorted(board.doors.items())
        )
        out.append(f"  doors (between cells): {listed}")
    return "\n".join(out)


def _reachable(board: Board, model: Model) -> set[Square]:
    """Squares at least one person can still stand on."""
    return {model.value_of(lit) for p in board.people for lit in model.options(p)}


def _narrowed(board: Board, model: Model, steps: Sequence[Step]) -> list[str]:
    """One line per open person who lost options in `steps`."""
    lost = Counter(s.var for s in steps if not s.asserted and model.chosen(s.var) is None)
    if not lost:
        return []
    lines = ["  narrowed by this step:"]
    for person in board.people:
        if person in lost:
            left = sorted(model.value_of(lit) for lit in model.options(person))
            listed = " ".join(map(str, left[:8])) + (" ..." if len(left) > 8 else "")
            lines.append(f"    {person:<9} -{lost[person]:<3} {len(left):>2} left: {listed}")
    return lines


def open_squares(board: Board, model: Model) -> dict[str, list[Square]]:
    """Remaining candidate squares per person - the working set."""
    return {p: sorted(model.value_of(lit) for lit in model.options(p)) for p in board.people}


def track_person_candidates(
    board: Board, model: Model, person: str
) -> tuple[list[Square], list[str]]:
    """Return a person's live squares and conservative region-overlap companions."""
    if person not in board.people:
        raise ValueError(f"unknown person {person!r}; have {board.people}")

    squares = open_squares(board, model)[person]
    regions = {board.region_of(square) for square in squares}
    companions = [
        candidate
        for candidate in board.people
        if candidate != person
        and any(board.region_of(model.value_of(lit)) in regions for lit in model.options(candidate))
    ]
    return squares, companions


def track_person_status(board: Board, model: Model, person: str) -> str:
    """Describe one person's live squares and region-overlap companions.

    Companion names are a conservative domain-overlap diagnostic, not a test
    that each person-square pair extends to a complete solution.
    """
    squares, companions = track_person_candidates(board, model, person)
    regions = {board.region_of(square) for square in squares}
    region_names = [name for rid, name in board.region_names.items() if rid in regions]

    chosen = model.chosen(person)
    if chosen is not None:
        location = f"{chosen} ({board.region_names[board.region_of(chosen)]})"
    elif not squares:
        location = "no live squares"
    elif len(squares) == 1:
        square = squares[0]
        location = f"1 square {square} ({board.region_names[board.region_of(square)]})"
    else:
        location = f"{len(squares)} squares in {', '.join(region_names)}"
        if len(squares) <= 8:
            location += f" [{', '.join(map(str, squares))}]"

    possible = ", ".join(companions) or "none"
    return f"  tracked {person}: {location}; region-overlap companions: {possible}"
