"""Exact-cover constraint engine.

A puzzle is compiled into a `Model` of

* literals    - atomic choices, such as ``r3c4=7`` or ``Tim=r1c2``,
* constraints - sets of literals of which exactly one, or at most one, holds,
* relations   - predicates over the values of two or more variables.

`Solver` applies named deduction `Rule`s until nothing more follows. Every
deduction is logged as a `Step` with a human-readable reason.

Nothing in this module knows about any particular puzzle.
"""

import copy
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from enum import Enum
from itertools import product
from typing import Any, NamedTuple, Self

type LiteralId = int
type ConstraintId = int


class Truth(Enum):
    UNKNOWN = 0
    TRUE = 1
    FALSE = 2


class Kind(Enum):
    """Whether a constraint must be satisfied, or merely may not be violated."""

    EXACTLY_ONE = "exactly one"
    AT_MOST_ONE = "at most one"


class Contradiction(Exception):
    """The current state cannot be extended to any solution.

    `source` names the constraint or relation that broke, when known.
    """

    def __init__(self, message: str, source: str | None = None) -> None:
        super().__init__(message)
        self.source = source


@dataclass(frozen=True)
class Literal:
    """The choice "variable `var` takes `value`"."""

    index: LiteralId
    var: str
    value: Any

    def __str__(self) -> str:
        return f"{self.var}={self.value}"


@dataclass(frozen=True)
class Constraint:
    """A set of literals of which exactly one, or at most one, may hold.

    `family` names the rule of the puzzle it is one instance of, such as
    "each digit once per row"; it only matters for explaining the model.
    """

    index: ConstraintId
    name: str
    kind: Kind
    literals: tuple[LiteralId, ...]
    family: str | None = None


@dataclass(frozen=True)
class Relation:
    """`holds(*values)` must be true in any solution, values in `variables` order."""

    name: str
    variables: tuple[str, ...]
    holds: Callable[..., bool]


@dataclass(frozen=True)
class Step:
    """One logged deduction: `var=value` was asserted or ruled out, and why.

    `reason` says why for people; the other fields say it for programs.
    `sources` names the constraints or relations the deduction rests on, and
    `scope` the constraints whose other options it pruned (subsumption,
    cover). `placing` is the var=value whose placement ruled this one out.
    `trail` holds what_if's steps from the assumption to the contradiction.
    """

    var: str
    value: Any
    asserted: bool
    rule: str
    reason: str
    sources: tuple[str, ...] = ()
    scope: tuple[str, ...] = ()
    placing: tuple[str, Any] | None = None
    trail: tuple["Step", ...] = ()

    @property
    def literal(self) -> str:
        return f"{self.var}={self.value}"

    def __str__(self) -> str:
        arrow = "=" if self.asserted else "x"
        return f"{arrow} {self.literal}  ({self.reason})"


class Model:
    """Literals, the constraints over them, and their current truth state.

    Build it with `literal`, `constrain` and `relate`; rules then read it
    through the inspection methods and change it only via `assign` and
    `eliminate`, which log every change.
    """

    def __init__(self) -> None:
        self._literals: list[Literal] = []
        self._by_key: dict[tuple[str, Any], LiteralId] = {}
        self._state: list[Truth] = []
        self._in_constraints: list[list[ConstraintId]] = []
        self._constraints: list[Constraint] = []
        self._relations: list[Relation] = []
        self._domain_of: dict[str, ConstraintId] = {}
        self.log: list[Step] = []

    # --- construction -----------------------------------------------------

    def literal(self, var: str, value: Any) -> LiteralId:
        """The literal `var=value`, created on first use."""
        key = (var, value)
        if key in self._by_key:
            return self._by_key[key]
        index = len(self._literals)
        self._literals.append(Literal(index, var, value))
        self._state.append(Truth.UNKNOWN)
        self._in_constraints.append([])
        self._by_key[key] = index
        return index

    def constrain(
        self,
        name: str,
        kind: Kind,
        literals: Iterable[LiteralId],
        *,
        defines: str | None = None,
        family: str | None = None,
    ) -> ConstraintId:
        """Add a constraint. `defines` marks it as that variable's whole domain."""
        index = len(self._constraints)
        constraint = Constraint(index, name, kind, tuple(literals), family)
        self._constraints.append(constraint)
        for lit in constraint.literals:
            self._in_constraints[lit].append(index)
        if defines is not None:
            self._domain_of[defines] = index
        return index

    def relate(self, name: str, variables: Iterable[str], holds: Callable[..., bool]) -> None:
        """Require `holds(*values)` of the named variables' values, in order."""
        self._relations.append(Relation(name, tuple(variables), holds))

    def clone(self) -> Self:
        """A copy with its own truth state and an empty log.

        Structure is shared, so only clone a model that is fully built.
        """
        twin = copy.copy(self)
        twin._state = list(self._state)
        twin.log = []
        return twin

    # --- inspection -------------------------------------------------------

    @property
    def num_literals(self) -> int:
        return len(self._literals)

    @property
    def constraints(self) -> Sequence[Constraint]:
        return self._constraints

    @property
    def relations(self) -> Sequence[Relation]:
        return self._relations

    @property
    def variables(self) -> list[str]:
        return list(self._domain_of)

    def domain_of(self, var: str) -> ConstraintId:
        """The EXACTLY_ONE constraint listing every value `var` could take."""
        return self._domain_of[var]

    def describe(self, lit: LiteralId) -> str:
        return str(self._literals[lit])

    def value_of(self, lit: LiteralId) -> Any:
        return self._literals[lit].value

    def var_of(self, lit: LiteralId) -> str:
        return self._literals[lit].var

    def is_true(self, lit: LiteralId) -> bool:
        return self._state[lit] is Truth.TRUE

    def is_false(self, lit: LiteralId) -> bool:
        return self._state[lit] is Truth.FALSE

    def constraints_of(self, lit: LiteralId) -> Sequence[ConstraintId]:
        return self._in_constraints[lit]

    def live(self, constraint: ConstraintId) -> list[LiteralId]:
        """Literals of a constraint that are still undecided."""
        literals = self._constraints[constraint].literals
        return [lit for lit in literals if self._state[lit] is Truth.UNKNOWN]

    def satisfied(self, constraint: ConstraintId) -> bool:
        return any(self.is_true(lit) for lit in self._constraints[constraint].literals)

    def options(self, var: str) -> list[LiteralId]:
        """Literals for `var` that are not ruled out (undecided or true)."""
        domain = self._constraints[self._domain_of[var]]
        return [lit for lit in domain.literals if not self.is_false(lit)]

    def chosen(self, var: str) -> Any | None:
        """The value `var` has been assigned, or None while it is open."""
        domain = self._constraints[self._domain_of[var]]
        for lit in domain.literals:
            if self.is_true(lit):
                return self._literals[lit].value
        return None

    def assignment(self) -> dict[str, Any]:
        """Variables decided so far."""
        decided = {var: self.chosen(var) for var in self._domain_of}
        return {var: value for var, value in decided.items() if value is not None}

    def solution(self) -> dict[str, Any] | None:
        """The full assignment, or None if any variable is still open."""
        decided = self.assignment()
        return decided if len(decided) == len(self._domain_of) else None

    # --- mutation ---------------------------------------------------------

    def eliminate(
        self,
        lit: LiteralId,
        rule: str,
        reason: str,
        *,
        sources: tuple[str, ...] = (),
        scope: tuple[str, ...] = (),
        placing: tuple[str, Any] | None = None,
        trail: tuple[Step, ...] = (),
    ) -> bool:
        """Rule `lit` out. Returns whether that changed anything.

        The keywords become the logged `Step`'s fields of the same names.
        """
        match self._state[lit]:
            case Truth.FALSE:
                return False
            case Truth.TRUE:
                raise Contradiction(
                    f"{self.describe(lit)} is already true; {reason}",
                    sources[0] if sources else None,
                )
        self._state[lit] = Truth.FALSE
        literal = self._literals[lit]
        self.log.append(
            Step(literal.var, literal.value, False, rule, reason, sources, scope, placing, trail)
        )
        return True

    def assign(
        self, lit: LiteralId, rule: str, reason: str, *, sources: tuple[str, ...] = ()
    ) -> bool:
        """Make `lit` true and rule out every literal it shares a constraint with."""
        match self._state[lit]:
            case Truth.TRUE:
                return False
            case Truth.FALSE:
                raise Contradiction(
                    f"{self.describe(lit)} is already ruled out; {reason}",
                    sources[0] if sources else None,
                )
        self._state[lit] = Truth.TRUE
        literal = self._literals[lit]
        self.log.append(Step(literal.var, literal.value, True, rule, reason, sources))
        # Both kinds cap a constraint at one truth, so siblings go either way.
        for ci in self._in_constraints[lit]:
            constraint = self._constraints[ci]
            for other in constraint.literals:
                if other != lit and self._state[other] is Truth.UNKNOWN:
                    self.eliminate(
                        other,
                        rule,
                        f"{literal} holds in {constraint.name}",
                        sources=(constraint.name,),
                        placing=(literal.var, literal.value),
                    )
        return True

    def check(self) -> None:
        """Raise Contradiction if the state is already unsatisfiable."""
        for constraint in self._constraints:
            states = [self._state[lit] for lit in constraint.literals]
            if states.count(Truth.TRUE) > 1:
                raise Contradiction(
                    f"{constraint.name}: more than one literal true", constraint.name
                )
            if constraint.kind is Kind.EXACTLY_ONE and all(s is Truth.FALSE for s in states):
                raise Contradiction(f"{constraint.name}: every option eliminated", constraint.name)


# --- rules ----------------------------------------------------------------
# A rule inspects the model, makes one deduction (which may rule out several
# literals at once), and returns whether it changed anything. Every rule must
# be sound for any model, and must log its deductions under its own
# `Rule.name`.


class Rule(NamedTuple):
    name: str
    apply: Callable[[Model], bool]


def rule_single(model: Model) -> bool:
    """An EXACTLY_ONE constraint with one option left forces that option.

    This covers Sudoku's naked single (the constraint is "this cell holds one
    digit") and its hidden single (the constraint is "this digit sits once in
    this row") with no special-casing.
    """
    for constraint in model.constraints:
        if constraint.kind is not Kind.EXACTLY_ONE or model.satisfied(constraint.index):
            continue
        live = model.live(constraint.index)
        if len(live) == 1:
            model.assign(
                live[0],
                "single",
                f"only option left in {constraint.name}",
                sources=(constraint.name,),
            )
            return True
    return False


def rule_relations(model: Model) -> bool:
    """Generalised arc consistency: drop every value that no combination of the
    other variables' values can satisfy, one relation at a time.

    All unsupported values of a relation go together. That is sound: support
    is checked against the options before any are removed, and removing
    options never creates support.
    """
    return any(prune_relation(model, relation) for relation in model.relations)


def prune_relation(model: Model, relation: Relation) -> bool:
    """Drop the values `relation` leaves without support; whether any went."""
    domains = [model.options(var) for var in relation.variables]
    unsupported = _unsupported(model, relation, domains)
    for lit in unsupported:
        model.eliminate(
            lit, "relations", f"nothing satisfies {relation.name}", sources=(relation.name,)
        )
    return bool(unsupported)


def _unsupported(
    model: Model, relation: Relation, domains: list[list[LiteralId]]
) -> list[LiteralId]:
    """Options that appear in no combination satisfying `relation`.

    One pass over the combinations serves every variable at once, skipping
    combinations that could not support anything new, and stopping as soon
    as every option has support.
    """
    lacking = [set(options) for options in domains]
    for combo in product(*domains):
        if not any(lit in lacking[i] for i, lit in enumerate(combo)):
            continue
        if relation.holds(*(model.value_of(lit) for lit in combo)):
            for i, lit in enumerate(combo):
                lacking[i].discard(lit)
            if not any(lacking):
                return []
    return [lit for i, options in enumerate(domains) for lit in options if lit in lacking[i]]


def rule_subsumption(model: Model) -> bool:
    """If one constraint's options all sit inside another's, prune the rest.

    Let A be EXACTLY_ONE with live(A) contained in live(B). Exactly one
    literal of A holds, it also belongs to B, and B admits at most one
    truth - so every literal of B outside A is false.

    In Sudoku this is the pointing pair and box/line reduction at once; in
    Murdoku it prunes rows against regions. Nothing here is puzzle-specific.
    """
    for a in model.constraints:
        if a.kind is not Kind.EXACTLY_ONE or model.satisfied(a.index):
            continue
        candidates: set[ConstraintId] = set()
        for lit in model.live(a.index):
            candidates.update(model.constraints_of(lit))
        candidates.discard(a.index)
        if any(cover(model, [a.index], [b]) for b in sorted(candidates)):
            return True
    return False


def cover(model: Model, inner: Sequence[ConstraintId], outer: Sequence[ConstraintId]) -> bool:
    """If the `inner` EXACTLY_ONE constraints, with disjoint options, fit
    inside as many `outer` ones, rule out the rest of `outer`.

    Whether anything was ruled out. This is the step behind both
    `rule_subsumption` (one of each) and `rule_cover`; see those for why it
    is sound.
    """
    constraints = model.constraints
    if len(outer) > len(inner) or any(constraints[a].kind is not Kind.EXACTLY_ONE for a in inner):
        return False
    if any(model.satisfied(ci) for ci in (*inner, *outer)):
        return False
    lives = [set(model.live(a)) for a in inner]
    union = set().union(*lives)
    if not all(lives) or len(union) != sum(map(len, lives)):
        return False
    around = set().union(*(model.live(b) for b in outer))
    if not union < around:
        return False
    a_names = tuple(constraints[a].name for a in inner)
    b_names = tuple(constraints[b].name for b in outer)
    if len(inner) == 1:
        rule, reason = "subsumption", f"{a_names[0]} already uses one of {b_names[0]}"
    else:
        rule, reason = f"cover{len(inner)}", f"{', '.join(a_names)} use up {', '.join(b_names)}"
    for lit in sorted(around - union):
        model.eliminate(lit, rule, reason, sources=a_names, scope=b_names)
    return True


def rule_cover(k: int) -> Callable[[Model], bool]:
    """Subsumption over k constraints at once: if k disjoint EXACTLY_ONE
    constraints fit inside k others, those others are used up.

    Let A1..Ak be EXACTLY_ONE with pairwise disjoint live sets, and B1..Bk be
    other constraints whose live literals together contain every live literal
    of the As. The As make k distinct literals true, each lying in some B.
    The Bs hold at most k truths between them, so those k use up every B -
    any B-literal outside the As is false.

    In Sudoku, As as cells and Bs as digit-in-house give naked subsets;
    swapped, hidden subsets; As as digit-in-row and Bs as digit-in-column
    give X-Wing (k=2) and Swordfish (k=3). The rule sees none of that.
    """

    def apply(model: Model) -> bool:
        return _CoverSearch(model, k).run()

    apply.__doc__ = (rule_cover.__doc__ or "").replace(" k ", f" {k} ")
    return apply


class _CoverSearch:
    """One pass of `rule_cover(k)`: grow groups of As, look for covering Bs.

    Only connected groups of As are grown: a disconnected group splits into
    smaller ones that a lower k already handles.
    """

    def __init__(self, model: Model, k: int) -> None:
        self.model = model
        self.k = k
        self.live = {
            c.index: frozenset(model.live(c.index))
            for c in model.constraints
            if not model.satisfied(c.index)
        }
        self.anchors = {
            ci
            for ci, lits in self.live.items()
            if lits and model.constraints[ci].kind is Kind.EXACTLY_ONE
        }
        self.seen: set[frozenset[ConstraintId]] = set()

    def run(self) -> bool:
        return any(self._grow(frozenset([a]), self.live[a], a) for a in sorted(self.anchors))

    def _grow(
        self, group: frozenset[ConstraintId], union: frozenset[LiteralId], first: ConstraintId
    ) -> bool:
        if group in self.seen:
            return False
        self.seen.add(group)
        if next(self._covers(union, (), group), None) is None:
            return False
        if len(group) < self.k:
            return any(
                self._grow(group | {ci}, union | self.live[ci], first)
                for ci in self._neighbours(group, union, first)
            )
        return any(cover(self.model, sorted(group), bs) for bs in self._covers(union, (), group))

    def _covers(
        self,
        need: frozenset[LiteralId],
        used: tuple[ConstraintId, ...],
        group: frozenset[ConstraintId],
    ) -> Iterator[tuple[ConstraintId, ...]]:
        """Every way to pick at most k constraints outside `group` containing `need`."""
        if not need:
            yield used
            return
        if len(used) == self.k:
            return
        for b in self.model.constraints_of(min(need)):
            if b not in group and b not in used and b in self.live:
                yield from self._covers(need - self.live[b], (*used, b), group)

    def _neighbours(
        self, group: frozenset[ConstraintId], union: frozenset[LiteralId], first: ConstraintId
    ) -> list[ConstraintId]:
        """Anchors that share a constraint with `union` and are disjoint from it.

        Only anchors after `first` are offered, so each group is grown from
        its lowest-numbered member and found once.
        """
        near: set[ConstraintId] = set()
        for lit in union:
            for ci in self.model.constraints_of(lit):
                for other in self.live.get(ci, ()):
                    near.update(self.model.constraints_of(other))
        return sorted(
            ci
            for ci in near
            if ci in self.anchors and ci > first and ci not in group and not self.live[ci] & union
        )


_WHAT_IF_INNER = (rule_single, rule_relations, rule_subsumption)


def rule_what_if(model: Model) -> bool:
    """Assume a literal on a copy; if the cheap rules then contradict, it is false.

    Sound because every rule used on the copy is sound: a contradiction
    reached from "x holds" proves x cannot hold. Only cheap rules run on the
    copy, never what-if itself, so the search stays one level deep. Variables
    with the fewest options are tried first, as a person would.
    """
    undecided = [var for var in model.variables if model.chosen(var) is None]
    for var in sorted(undecided, key=lambda v: len(model.options(v))):
        if any(refute(model, lit) for lit in model.options(var)):
            return True
    return False


def refute(model: Model, lit: LiteralId) -> bool:
    """Rule `lit` out if assuming it leads the cheap rules to a contradiction."""
    if model.is_true(lit) or model.is_false(lit):
        return False
    refutation = _refute(model, lit)
    if refutation is None:
        return False
    reason, trail, broken = refutation
    sources = () if broken is None else (broken,)
    model.eliminate(lit, "what_if", reason, sources=sources, trail=trail)
    return True


def _refute(model: Model, lit: LiteralId) -> tuple[str, tuple[Step, ...], str | None] | None:
    """Why assuming `lit` leads to a contradiction, or None if it does not:
    the reason, the steps taken on the way, and what broke."""
    twin = model.clone()
    try:
        twin.assign(lit, "what_if", "assumed")
        twin.check()
        while any(rule(twin) for rule in _WHAT_IF_INNER):
            twin.check()
    except Contradiction as exc:
        reason = f"assuming it leads, in {len(twin.log)} steps, to: {exc}"
        return reason, tuple(twin.log), exc.source
    return None


DEFAULT_RULES: tuple[Rule, ...] = (
    Rule("single", rule_single),
    Rule("relations", rule_relations),
    Rule("subsumption", rule_subsumption),
    Rule("cover2", rule_cover(2)),
    Rule("cover3", rule_cover(3)),
    Rule("what_if", rule_what_if),
)


# --- solver ---------------------------------------------------------------

type StepCallback = Callable[[str, Sequence[Step]], None]


@dataclass(frozen=True)
class Result:
    """Outcome of `Solver.solve`.

    `assignment` is the full solution when `solved`, otherwise whatever had
    been decided when the rules ran out or hit `contradiction`.
    """

    solved: bool
    assignment: dict[str, Any]
    iterations: int
    contradiction: str | None = None


class Solver:
    """Applies rules cheapest-first, restarting after each success, until
    nothing more can be deduced."""

    def __init__(self, model: Model, rules: Iterable[Rule] = DEFAULT_RULES) -> None:
        self.model = model
        self.rules = tuple(rules)

    def solve(self, on_step: StepCallback | None = None) -> Result:
        """Run to a fixed point.

        `on_step` receives the rule name and the steps it produced, so callers
        can render progress without this module knowing how to draw.
        """
        iterations = 0
        try:
            self.model.check()
            while True:
                iterations += 1
                fired = self._apply_cheapest_progress()
                if fired is None:
                    break
                if on_step is not None:
                    on_step(*fired)
        except Contradiction as exc:
            return Result(False, self.model.assignment(), iterations, str(exc))

        solution = self.model.solution()
        if solution is None:
            return Result(False, self.model.assignment(), iterations)
        return Result(True, solution, iterations)

    def _apply_cheapest_progress(self) -> tuple[str, Sequence[Step]] | None:
        """Apply the first rule that changes something; its name and new steps."""
        for rule in self.rules:
            mark = len(self.model.log)
            if rule.apply(self.model):
                self.model.check()
                return rule.name, self.model.log[mark:]
        return None
