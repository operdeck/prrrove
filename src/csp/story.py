"""Murdoku solutions written out the way a person would explain them.

`proof` decides *what* to say: a short replay of the solver's own
deductions. This module only decides *how*: one paragraph per placement (or
run of placements), people's options described by region, row, column or
the things on the board wherever that is exact, square numbers only when
they are few.

Wording comes from two optional sections of the puzzle file:

    Language: nl
    Words:
    water: in het water        # a region or group: where it is
    vuurtje: het vuurtje       # an object or furniture: what it is called

Everything here reads the public `Model` API, `Step` provenance and
`murdoku`'s board and clue meaning; nothing here is needed to solve.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from itertools import combinations, groupby
from typing import Any

from .core import Solver, Step
from .murdoku import (
    COUNTING,
    FILTERS,
    Board,
    Clue,
    Condition,
    Square,
    board_rules,
    compile_puzzle,
    conditions,
    counted,
)
from .proof import Move, essential, replay, shortest
from .puzzlefile import load_board, read_sections

PHRASES: dict[str, dict[str, str]] = {
    "en": {
        "square": "r{row}c{col}",
        "and": "and",
        "or": "or",
        "region": "in the {name}",
        "the": "the {name}",
        "a": "a {name}",
        "row": "row {n}",
        "col": "column {n}",
        "rows": "rows {list}",
        "cols": "columns {list}",
        "through": "{a} to {b}",
        "in": "in {what}",
        "on": "on {what}",
        "next_to": "next to {what}",
        "is": "{who} is {where}",
        "is_not": "{who} is not {where}",
        "count": "{who} has {n} squares left",
        "placed": "**{who} on {square}**",
        "so": "so",
        "takes_line": "{who} takes {line}",
        "takes_square": "{who} is already on {square}",
        "only_left": "only {square} is left for {who}",
        "only_one": "only {who} can still fill {lines}",
        "only_many": "only {who} can still fill {lines}",
        "can_only_one": "{who} can only be {where}",
        "can_only_many": "{who} can only be {where}",
        "filled_only_one": "{lines} can only be filled {where}",
        "filled_only_many": "{lines} can only be filled {where}",
        "via": "via {refs}",
        "nobody_else": "nobody else can be there",
        "then_on": "then {who} is on {square}",
        "nowhere": "then {who} has nowhere left",
        "nobody": "then nobody can fill {line}",
        "both": "then {who} are both {where}",
        "breaks": "which clue {n} does not allow",
        "breaks_first": "clue {n} does not allow that",
        "breaks_rule": "which the board does not allow",
        "breaks_rule_first": "the board does not allow that",
        "cannot": "{who} cannot be on {squares}: {chain}.",
        "nor": "Nor on {squares}: {chain}.",
        "direct": "The direct clues",
        "the_rest": "The rest",
        "squares": "{n} squares",
        "one_row": "one row",
        "n_rows": "{n} rows",
        "clue.in_region": "{a} is {where}",
        "clue.outside": "{a} is not {where}",
        "clue.next_to": "{a} is next to {things}",
        "clue.not_next_to": "{a} is not next to {things}",
        "clue.knight_from": "{a} is a knight's move from {things}",
        "clue.on": "{a} is on {things}",
        "clue.same_region": "{a} and {b} are in the same region",
        "clue.different_region": "{a} and {b} are in different regions",
        "clue.apart": "{a} and {b} are in regions that do not touch",
        "clue.left_of": "{a} is somewhere left of {b}",
        "clue.exactly": "exactly {n} of these is true: {list}",
        "clue.above": "{a} is somewhere above {b}",
        "clue.above_n": "{a} is exactly {rows} above {b}",
        "clue.within": "{a} is at most {n} squares from {b}",
        "clue.at_least": "{a} is at least {n} squares from {b}",
        "clue.alone": "nobody else is in {a}'s region",
        "clue.furthest": "{a} is further from {b} than {c} is",
    },
    "nl": {
        "square": "r{row}k{col}",
        "and": "en",
        "or": "of",
        "region": "in de {name}",
        "the": "de {name}",
        "a": "een {name}",
        "row": "rij {n}",
        "col": "kolom {n}",
        "rows": "de rijen {list}",
        "cols": "de kolommen {list}",
        "through": "{a} t/m {b}",
        "in": "in {what}",
        "on": "op {what}",
        "next_to": "naast {what}",
        "is": "{who} zit {where}",
        "is_not": "{who} zit niet {where}",
        "count": "{who} kan nog op {n} vakjes",
        "placed": "**{who} op {square}**",
        "so": "dus",
        "takes_line": "{who} bezet {line}",
        "takes_square": "{who} zit al op {square}",
        "only_left": "voor {who} blijft alleen {square} over",
        "only_one": "{lines} kan alleen nog van {who} zijn",
        "only_many": "{lines} kunnen alleen nog van {who} zijn",
        "can_only_one": "{who} kan alleen {where}",
        "can_only_many": "{who} kunnen alleen {where}",
        "filled_only_one": "{lines} kan alleen nog gevuld worden {where}",
        "filled_only_many": "{lines} kunnen alleen nog gevuld worden {where}",
        "via": "via {refs}",
        "nobody_else": "daar kan verder niemand",
        "then_on": "dan zit {who} op {square}",
        "nowhere": "dan kan {who} nergens meer",
        "nobody": "dan kan niemand meer in {line}",
        "both": "dan zitten {who} allebei {where}",
        "breaks": "en dat mag niet volgens aanwijzing {n}",
        "breaks_first": "dat mag niet volgens aanwijzing {n}",
        "breaks_rule": "en dat mag niet",
        "breaks_rule_first": "dat mag niet",
        "cannot": "{who} kan niet op {squares}: {chain}.",
        "nor": "Ook niet op {squares}: {chain}.",
        "direct": "De directe aanwijzingen",
        "the_rest": "De rest",
        "squares": "{n} vakjes",
        "one_row": "één rij",
        "n_rows": "{n} rijen",
        "clue.in_region": "{a} is {where}",
        "clue.outside": "{a} is niet {where}",
        "clue.next_to": "{a} zit naast {things}",
        "clue.not_next_to": "{a} zit niet naast {things}",
        "clue.knight_from": "{a} staat een paardensprong van {things}",
        "clue.on": "{a} ligt op {things}",
        "clue.same_region": "{a} en {b} zijn in hetzelfde gebied",
        "clue.different_region": "{a} en {b} zijn in verschillende gebieden",
        "clue.apart": "{a} en {b} zijn in gebieden die niet aan elkaar grenzen",
        "clue.left_of": "{a} is ergens links van {b}",
        "clue.exactly": "precies {n} hiervan klopt: {list}",
        "clue.above": "{a} is ergens boven {b}",
        "clue.above_n": "{a} is precies {rows} boven {b}",
        "clue.within": "{a} is hooguit {n} vakjes van {b}",
        "clue.at_least": "{a} is minstens {n} vakjes van {b}",
        "clue.alone": "niemand anders is in het gebied van {a}",
        "clue.furthest": "{a} is verder van {b} dan {c}",
    },
}

NUMBERS = {
    "en": ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
           "ten", "eleven", "twelve"],
    "nl": ["nul", "één", "twee", "drie", "vier", "vijf", "zes", "zeven", "acht", "negen",
           "tien", "elf", "twaalf"],
}  # fmt: skip

MAX_LISTED = 3  # squares named outright alongside, or instead of, a description

# What a relation's other people are worth mentioning for: their rows, columns or regions.
ASPECT = {
    "above": "row",
    "left_of": "col",
    "same_region": "region",
    "different_region": "region",
    "apart": "region",
    "alone": "region",
}


@dataclass(frozen=True)
class Wording:
    """How to say things: a language from `PHRASES`, and names in it."""

    language: str = "en"
    words: dict[str, str] = field(default_factory=dict)

    @classmethod
    def read(cls, text: str) -> "Wording":
        """The `Language:` and `Words:` sections of a puzzle file."""
        section = read_sections(text)
        language = section.get("Language", ["en"])[0]
        if language not in PHRASES:
            raise ValueError(f"no wording for language {language!r}; have {sorted(PHRASES)}")
        words = {}
        for line in section.get("Words", []):
            name, _, phrase = line.partition(":")
            if not phrase.strip():
                raise ValueError(f"Words: {line!r} is not like 'vuurtje: het vuurtje'")
            words[name.strip()] = phrase.strip()
        return cls(language, words)

    def __call__(self, key: str, **fields: Any) -> str:
        return PHRASES[self.language][key].format(**fields)

    def number(self, n: int) -> str:
        names = NUMBERS[self.language]
        return names[n] if n < len(names) else str(n)

    def join(self, items: Sequence[str], word: str = "and") -> str:
        items = list(items)
        if len(items) <= 1:
            return "".join(items)
        return f"{', '.join(items[:-1])} {self(word)} {items[-1]}"


class Places:
    """Describes sets of squares in the board's own terms."""

    def __init__(self, board: Board, say: Wording) -> None:
        self.board = board
        self.say = say
        self.free = set(board.free)
        self.areas = self._areas()

    def square(self, sq: Square) -> str:
        return self.say("square", row=sq.row + 1, col=sq.col + 1)

    def squares(self, squares: Iterable[Square], word: str = "or") -> str:
        return self.say.join([self.square(sq) for sq in sorted(squares)], word)

    def region(self, name: str) -> str:
        return self.say.words.get(name) or self.say("region", name=name.replace("_", " "))

    def thing(self, name: str) -> str:
        if name in self.say.words:
            return self.say.words[name]
        many = len(_pieces(self.board.squares_of([name]))) > 1
        return self.say("a" if many else "the", name=name.replace("_", " "))

    def where_regions(self, names: Iterable[str]) -> str:
        return self.say.join([self.region(n) for n in names], "or")

    def regions(self, ids: set[str]) -> str:
        """'in the moestuin or on kantoor', using a group's name where it fits."""
        names: list[str] = []
        left = set(ids)
        for group, members in self.board.groups.items():
            inside = self.board.region_ids(members)
            if inside <= left:
                names.append(group)
                left -= inside
        names += [self.board.region_names[i] for i in sorted(left)]
        return self.where_regions(names)

    def line(self, kind: str, i: int) -> str:
        return self.say(kind, n=i + 1)

    def lines(self, kind: str, indices: Iterable[int], word: str = "and") -> str:
        """'row 3', or 'rows 3 and 6', 'rows 1 to 3' (with `word` 'or': 'row 3 or 6')."""
        ordered = sorted(indices)
        if len(ordered) == 1:
            return self.line(kind, ordered[0])
        if len(ordered) > 2 and ordered == list(range(ordered[0], ordered[-1] + 1)):
            listed = self.say("through", a=ordered[0] + 1, b=ordered[-1] + 1)
        else:
            listed = self.say.join([str(i + 1) for i in ordered], word)
        if word == "or":
            return self.say(kind, n=listed)
        return self.say(f"{kind}s", list=listed)

    def where(self, chosen: set[Square], within: set[Square], most: int = 2) -> str | None:
        """A short exact description of `chosen` among `within`, if there is one:
        up to `most` of region, row, column, furniture or next-to-object."""
        tests = [(name, test) for name, test in self._tests(chosen) if all(map(test, chosen))]
        found: list[str] = []
        for size in range(1, most + 1):
            for combo in combinations(tests, size):
                if {sq for sq in within if all(test(sq) for _, test in combo)} == chosen:
                    found.append(", ".join(name for name, _ in combo))
            if found:
                break
        return min(found, key=len) if found else None

    def describe(
        self, who: str, chosen: set[Square], within: set[Square], *, placing: bool = True
    ) -> str:
        """The shortest exact way to say where `who` can be, out of `within`:
        'Jos zit op de woonboot (r8k3 of r8k4)', 'Otto zit niet in rij 1'.
        One square left is a placement, in bold, unless not `placing`."""
        if len(chosen) == 1:
            if placing:
                return self.placed(who, min(chosen))
            return self.say("is", who=who, where=self.say("on", what=self.square(min(chosen))))
        ways: list[str] = []
        if (where := self.where(chosen, within)) is not None:
            listed = f" ({self.squares(chosen)})" if len(chosen) <= MAX_LISTED else ""
            ways.append(self.say("is", who=who, where=where) + listed)
        if (gone := self.where(within - chosen, within, most=1)) is not None:
            ways.append(self.say("is_not", who=who, where=gone))
        if len(chosen) <= MAX_LISTED + 1:
            ways.append(self.say("is", who=who, where=self.say("on", what=self.squares(chosen))))
        if ways:
            return min(ways, key=len)
        return self.say("count", who=who, n=self.say.number(len(chosen)))

    def roughly(self, who: str, chosen: set[Square], kind: str) -> str:
        """Where `who` can be as far as one clue cares: the rows, columns or
        regions `chosen` touches (kind 'row', 'col' or 'region')."""
        if len(chosen) < MAX_LISTED:
            return self.say("is", who=who, where=self.say("on", what=self.squares(chosen)))
        if kind == "region":
            where = self.regions({self.board.region_of(sq) for sq in chosen})
        else:
            spans = {sq.row if kind == "row" else sq.col for sq in chosen}
            where = self.say("in", what=self.lines(kind, spans, "or"))
        return self.say("is", who=who, where=where)

    def placed(self, who: str, square: Square) -> str:
        return self.say("placed", who=who, square=self.square(square))

    def _areas(self) -> list[tuple[str, Callable[[Square], bool]]]:
        board = self.board
        areas: list[tuple[str, Callable[[Square], bool]]] = []
        for name in board.furniture:
            spots = board.squares_of([name])
            areas.append((self.say("on", what=self.thing(name)), spots.__contains__))
        for name in board.objects:
            near = {
                sq
                for t in board.squares_of([name])
                for sq in self.free
                if abs(sq.row - t.row) + abs(sq.col - t.col) == 1
                and board.region_of(sq) == board.region_of(t)
            }
            areas.append((self.say("next_to", what=self.thing(name)), near.__contains__))
        return areas

    def _region_of(self, chosen: set[Square]) -> tuple[str, Callable[[Square], bool]]:
        """The test 'in the regions `chosen` lies in'."""
        ids = {self.board.region_of(sq) for sq in chosen}
        board = self.board
        return self.regions(ids), lambda sq: board.region_of(sq) in ids

    def _tests(self, chosen: set[Square]) -> list[tuple[str, Callable[[Square], bool]]]:
        rows = {sq.row for sq in chosen}
        cols = {sq.col for sq in chosen}
        return [
            self._region_of(chosen),
            (self.say("in", what=self.lines("row", rows, "or")), lambda sq: sq.row in rows),
            (self.say("in", what=self.lines("col", cols, "or")), lambda sq: sq.col in cols),
            *self.areas,
        ]


@dataclass
class _State:
    """Where everyone can still be, who is placed (in order), and what the
    reader has been told about the rest."""

    options: dict[str, set[Square]]
    told: dict[str, set[Square]]
    placed: dict[str, Square] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    history: list[Step] = field(default_factory=list)
    announced: list[str] = field(default_factory=list)  # placed in bold so far, in order

    def announce(self, person: str) -> None:
        if person not in self.announced:
            self.announced.append(person)

    def apply(self, steps: Sequence[Step]) -> None:
        for step in steps:
            self.history.append(step)
            if step.asserted:
                self.options[step.var] = {step.value}
                self.placed[step.var] = step.value
                self.order.append(step.var)
            else:
                self.options[step.var].discard(step.value)


class Story:
    """Writes the explanation of one solved Murdoku."""

    def __init__(self, board: Board, clues: Sequence[Clue], say: Wording) -> None:
        self.board = board
        self.say = say
        self.places = Places(board, say)
        self.about = {rule.name: rule.about for rule in board_rules(board)}
        self.conditions = {c.label: c for c in conditions(board, clues)}
        self.model = compile_puzzle(board, clues)

    def tell(self) -> str:
        start = self.model.clone()
        compiled = list(self.model.log)
        moves: list[Move] = []

        def collect(rule: str, steps: Sequence[Step]) -> None:
            if (move := Move.of(rule, steps)) is not None:
                moves.append(move)

        Solver(self.model.clone()).solve(on_step=collect)
        firings: list[tuple[str, Sequence[Step]]] = []
        replay(start, shortest(start, moves), lambda rule, steps: firings.append((rule, steps)))

        options = {p: {start.value_of(lit) for lit in start.options(p)} for p in self.board.people}
        state = _State(options, {p: set(s) for p, s in options.items()})
        state.history = compiled
        paragraphs = [self._opening(compiled, state)]
        sentences: list[str] = []
        placed: list[str] = []
        mark = len(state.announced)  # who the current bullet has placed starts here
        refuted: list[tuple[str, Square, str]] = []  # what_ifs waiting to be said together
        for i, (rule, steps) in enumerate(firings):
            if rule == "what_if":
                refuted.append(self._what_if(steps[0], state))
            else:
                sentences += self._refuted(refuted)
                refuted = []
                said = self._firing(rule, steps, state)
                if said:
                    sentences.append(said)
                    if rule == "single":
                        placed.append(steps[0].var)
            last = i + 1 == len(firings)
            if placed and (last or firings[i + 1][0] != "single"):
                named = state.announced[mark:]
                lead = self.say.join(named)
                if last and len(named) > 3:
                    lead = self.say("the_rest")
                paragraphs.append(f"**{lead}.** {' '.join(sentences)}")
                sentences, placed = [], []
                mark = len(state.announced)
        sentences += self._refuted(refuted)
        if sentences:
            paragraphs.append(" ".join(sentences))
        return "\n\n".join(f"- {p}" for p in paragraphs)

    # --- paragraphs and sentences ------------------------------------------

    def _opening(self, compiled: Sequence[Step], state: _State) -> str:
        """Each clue about one person, with where that leaves them right after it."""
        said: list[str] = []
        left = {p: set(self.places.free) for p in self.board.people}
        for label, group in groupby(compiled, key=lambda s: s.sources[0]):
            steps = list(group)
            for step in steps:
                left[step.var].discard(step.value)
            condition = self.conditions[label]
            if condition.number is None or condition.kind in ("in_region", "outside"):
                continue
            (person,) = condition.people
            squares = left[person]
            if len(squares) == 1:
                where = self.places.placed(person, min(squares))
                state.announce(person)
            elif len(squares) <= MAX_LISTED + 1:
                where = self.places.squares(squares)
            else:
                where = self.say("squares", n=self.say.number(len(squares)))
            said.append(f"{_cap(self._clue(condition))} ({condition.number}): {where}.")
        return f"**{self.say('direct')}.** {' '.join(said)}"

    def _firing(self, rule: str, steps: Sequence[Step], state: _State) -> str:
        before = {p: set(s) for p, s in state.options.items()}
        state.apply(steps)
        if rule == "single":
            return self._placement(steps[0], state)
        changed = [p for p in self.board.people if state.options[p] != before[p]]
        if rule == "relations":
            outcome = self._outcome(changed, before, state)
            return self._relation(steps[0], before, changed, outcome)
        return self._cover(steps[0], changed, before, state)

    def _outcome(self, people: Sequence[str], before: dict[str, set[Square]], state: _State) -> str:
        """Where `people` can be now, out of where they could be `before`."""
        for p in people:
            state.told[p] = set(state.options[p])
            if len(state.options[p]) == 1:
                state.announce(p)
        return self.say.join([self.places.describe(p, state.options[p], before[p]) for p in people])

    def _relation(
        self, step: Step, before: dict[str, set[Square]], changed: list[str], outcome: str
    ) -> str:
        """The clue, where the other people involved were known to be, and the upshot."""
        condition = self.conditions[step.sources[0]]
        clue = _cap(self._clue(condition)) + self._ref(condition)
        aspect = ASPECT.get(condition.kind)
        evidence = [
            self.places.roughly(p, before[p], aspect)
            if aspect
            else self.places.describe(p, before[p], self.places.free, placing=False)
            for p in condition.people
            if p not in changed and before[p] != self.places.free
        ]
        if evidence:
            return f"{clue}. {_cap(self.say.join(evidence))}, {self.say('so')} {outcome}."
        return f"{clue}, {self.say('so')} {outcome}."

    def _cover(
        self, step: Step, changed: list[str], before: dict[str, set[Square]], state: _State
    ) -> str:
        """Some people fill some rows (or columns), or some rows only fit some people."""
        inner = [self.about[n] for n in step.sources]
        outer = [self.about[n] for n in step.scope]
        kinds_in = {k for k, _ in inner}
        kinds_out = {k for k, _ in outer}
        if len(kinds_in) == 1 and len(kinds_out) == 1 and kinds_out <= {"row", "col"}:
            ((kind_in,), (kind,)) = (kinds_in, kinds_out)
            where = self.say("in", what=self.places.lines(kind, [i for _, i in outer], "or"))
            many = "_many" if len(inner) > 1 else "_one"
            if kind_in == "person":
                text = self.say(
                    "can_only" + many, who=self.say.join([p for _, p in inner]), where=where
                )
            else:
                lines = self.places.lines(kind_in, [i for _, i in inner])
                text = self.say("filled_only" + many, lines=lines, where=where)
            text = f"{_cap(text)}, {self.say('nobody_else')}"
            # Being shut out of those lines goes without saying; only news is worth a word.
            news = [p for p in changed if len(state.options[p]) <= MAX_LISTED]
            if news:
                return f"{text}: {self._outcome(news, before, state)}."
            return f"{text}."
        outcome = self._outcome(changed, before, state)
        if kinds_out == {"person"} and len(kinds_in) == 1 and kinds_in <= {"row", "col"}:
            (kind,) = kinds_in
            lines = self.places.lines(kind, [i for _, i in inner])
            key = "only_one" if len(inner) == 1 else "only_many"
            text = self.say(key, lines=lines, who=self.say.join([p for _, p in outer]))
            return f"{_cap(text)}, {self.say('so')} {outcome}."
        return f"{_cap(outcome)}."

    def _placement(self, step: Step, state: _State) -> str:
        who, square = step.var, step.value
        if who in state.announced:
            return ""
        state.announce(who)
        placed = self.places.placed(who, square)
        kind, what = self.about[step.sources[0]]
        gone = state.told[who] - {square}
        state.told[who] = {square}
        if kind in ("row", "col"):
            text = self.say("only_one", lines=self.places.line(kind, what), who=who)
            return f"{_cap(text)}: {placed}."
        reasons = self._blockers(who, gone, state)
        if reasons is None:
            text = self.say("only_left", who=who, square=self.places.square(square))
            return f"{_cap(text)}: {placed}."
        if reasons:
            return f"{_cap(self.say.join(reasons))}, {self.say('so')} {placed}."
        return f"{placed}."

    def _blockers(self, who: str, gone: set[Square], state: _State) -> list[str] | None:
        """Who took the squares the reader still had for `who`, fewest people
        first; None if that takes more than two."""
        takers: dict[str, set[Square]] = {}
        for sq in gone:
            for other, there in state.placed.items():
                if other != who and (there.row == sq.row or there.col == sq.col):
                    takers.setdefault(other, set()).add(sq)
        chosen: list[str] = []
        left = set(gone)
        while left:
            best = max(
                takers, key=lambda p: (len(takers[p] & left), state.order.index(p)), default=None
            )
            if best is None or not takers[best] & left:
                return None
            chosen.append(best)
            left -= takers[best]
        if len(chosen) > 2:
            return None
        said = []
        for other in chosen:
            there = state.placed[other]
            covered = takers[other] & gone
            if all(sq.row == there.row for sq in covered):
                line = self.places.line("row", there.row)
            elif all(sq.col == there.col for sq in covered):
                line = self.places.line("col", there.col)
            else:
                line = self.say.join(
                    [self.places.line("row", there.row), self.places.line("col", there.col)]
                )
            said.append(self.say("takes_line", who=other, line=line))
        return said

    def _what_if(self, step: Step, state: _State) -> tuple[str, Square, str]:
        """Who could not be where, and the chain of events that rules it out."""
        who, square = step.var, step.value
        needed = essential(self.model, state.history, step)
        state.apply([step])
        state.told[who].discard(square)
        parts: list[str] = []
        refs: list[int] = []
        for j in needed:
            inner = step.trail[j]
            if inner.asserted and j > 0:
                parts.append(
                    self.say("then_on", who=inner.var, square=self.places.square(inner.value))
                )
            for name in inner.sources:
                condition = self.conditions.get(name)
                if condition is not None and condition.number is not None:
                    refs.append(condition.number)
        parts.append(self._broken(step, first=not parts))
        broken = self.conditions.get(step.sources[0]) if step.sources else None
        cited = sorted(set(refs) - {broken.number if broken else None})
        if not cited:
            return who, square, ", ".join(parts)
        listed = self.say.join([str(n) for n in cited])
        ref = self.say("via", refs=listed) if broken else listed
        return who, square, f"{', '.join(parts)} ({ref})"

    def _refuted(self, refuted: Sequence[tuple[str, Square, str]]) -> list[str]:
        """Consecutive what_ifs, one sentence per person and reason."""
        sentences: list[str] = []
        previous = None
        for (who, chain), group in groupby(refuted, key=lambda r: (r[0], r[2])):
            squares = self.places.squares([sq for _, sq, _ in group])
            key = "nor" if who == previous else "cannot"
            sentences.append(self.say(key, who=who, squares=squares, chain=chain))
            previous = who
        return sentences

    def _broken(self, step: Step, first: bool) -> str:
        """The contradiction a what_if ran into."""
        source = step.sources[0] if step.sources else None
        if source in self.conditions:
            condition = self.conditions[source]
            suffix = "_first" if first else ""
            if condition.number is None:
                return self.say(f"breaks_rule{suffix}")
            return self.say(f"breaks{suffix}", n=condition.number)
        if source in self.about:
            kind, what = self.about[source]
            if kind == "person":
                return self.say("nowhere", who=what)
            placed = [s for s in step.trail if s.asserted]
            inside = [s.var for s in placed if self._in(kind, what, s.value)]
            if kind == "square":
                where = self.say("on", what=self.places.square(what))
                return self.say("both", who=self.say.join(inside), where=where)
            if len(inside) > 1:
                where = self.say("in", what=self.places.line(kind, what))
                return self.say("both", who=self.say.join(inside), where=where)
            return self.say("nobody", line=self.places.line(kind, what))
        return ""

    @staticmethod
    def _in(kind: str, what: Any, sq: Square) -> bool:
        return bool({"row": sq.row, "col": sq.col, "square": sq}[kind] == what)

    # --- clues ---------------------------------------------------------------

    def _clue(self, condition: Condition) -> str:
        return self._clue_text(condition.kind, condition.args, condition.people)

    def _clue_text(self, kind: str, args: Sequence[str], people: Sequence[str]) -> str:
        if kind == COUNTING:
            n, parts = counted(args)
            listed = "; ".join(
                self._clue_text(k, rest, rest[: 1 if k in FILTERS else 2]) for k, rest in parts
            )
            return self.say("clue.exactly", n=self.say.number(n), list=listed)
        fields: dict[str, Any] = dict(zip("abc", people, strict=False))
        rest = args[1:] if kind in FILTERS else ()
        if kind in ("in_region", "outside"):
            fields["where"] = self.places.where_regions(rest)
        elif rest:
            fields["things"] = self.say.join([self.places.thing(t) for t in rest], "or")
        if kind == "above" and len(args) > 2:
            n = int(args[2])
            kind = "above_n"
            fields["rows"] = self.say("one_row") if n == 1 else self.say("n_rows", n=n)
        elif kind in ("within", "at_least"):
            fields["n"] = self.say.number(int(args[2]))
        return self.say(f"clue.{kind}", **fields)

    def _ref(self, condition: Condition) -> str:
        return "" if condition.number is None else f" ({condition.number})"


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _pieces(squares: set[Square]) -> list[set[Square]]:
    """`squares` split into side-by-side pieces, such as the separate benches."""
    left, pieces = set(squares), []
    while left:
        piece, todo = set(), [left.pop()]
        while todo:
            sq = todo.pop()
            piece.add(sq)
            near = {s for s in left if abs(s.row - sq.row) + abs(s.col - sq.col) == 1}
            left -= near
            todo += near
        pieces.append(piece)
    return pieces


def explain(text: str) -> str:
    """The worked solution of a Murdoku puzzle file, as Markdown bullets."""
    board, clues = load_board(text)
    return Story(board, clues, Wording.read(text)).tell()
