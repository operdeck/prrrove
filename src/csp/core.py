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
    """The current state cannot be extended to any solution."""


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
    """One logged deduction: `var=value` was asserted or ruled out, and why."""

    var: str
    value: Any
    asserted: bool
    rule: str
    reason: str

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

    def eliminate(self, lit: LiteralId, rule: str, reason: str) -> bool:
        """Rule `lit` out. Returns whether that changed anything."""
        match self._state[lit]:
            case Truth.FALSE:
                return False
            case Truth.TRUE:
                raise Contradiction(f"{self.describe(lit)} is already true; {reason}")
        self._state[lit] = Truth.FALSE
        self._record(lit, False, rule, reason)
        return True

    def assign(self, lit: LiteralId, rule: str, reason: str) -> bool:
        """Make `lit` true and rule out every literal it shares a constraint with."""
        match self._state[lit]:
            case Truth.TRUE:
                return False
            case Truth.FALSE:
                raise Contradiction(f"{self.describe(lit)} is already ruled out; {reason}")
        self._state[lit] = Truth.TRUE
        self._record(lit, True, rule, reason)
        # Both kinds cap a constraint at one truth, so siblings go either way.
        for ci in self._in_constraints[lit]:
            constraint = self._constraints[ci]
            for other in constraint.literals:
                if other != lit and self._state[other] is Truth.UNKNOWN:
                    self.eliminate(other, rule, f"{self.describe(lit)} holds in {constraint.name}")
        return True

    def check(self) -> None:
        """Raise Contradiction if the state is already unsatisfiable."""
        for constraint in self._constraints:
            states = [self._state[lit] for lit in constraint.literals]
            if states.count(Truth.TRUE) > 1:
                raise Contradiction(f"{constraint.name}: more than one literal true")
            if constraint.kind is Kind.EXACTLY_ONE and all(s is Truth.FALSE for s in states):
                raise Contradiction(f"{constraint.name}: every option eliminated")

    def _record(self, lit: LiteralId, asserted: bool, rule: str, reason: str) -> None:
        literal = self._literals[lit]
        self.log.append(Step(literal.var, literal.value, asserted, rule, reason))


# --- rules ----------------------------------------------------------------
# A rule inspects the model, makes at most one deduction, and returns whether
# it changed anything. Every rule must be sound for any model, and must log
# its deductions under its own `Rule.name`.


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
            model.assign(live[0], "single", f"only option left in {constraint.name}")
            return True
    return False


def rule_relations(model: Model) -> bool:
    """Generalised arc consistency: drop a value that no combination of the
    other variables' values can satisfy."""
    for relation in model.relations:
        domains = [model.options(var) for var in relation.variables]
        for position, candidates in enumerate(domains):
            others = domains[:position] + domains[position + 1 :]
            for lit in candidates:
                if not _supported(model, relation, position, lit, others):
                    model.eliminate(lit, "relations", f"nothing satisfies {relation.name}")
                    return True
    return False


def _supported(
    model: Model,
    relation: Relation,
    position: int,
    lit: LiteralId,
    others: list[list[LiteralId]],
) -> bool:
    """Whether some choice for the other variables makes `relation` hold."""
    for combo in product(*others):
        values = [model.value_of(other) for other in combo]
        values.insert(position, model.value_of(lit))
        if relation.holds(*values):
            return True
    return False


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
        inner = set(model.live(a.index))
        if not inner:
            continue
        candidates: set[int] = set()
        for lit in inner:
            candidates.update(model.constraints_of(lit))
        for bi in candidates:
            if bi == a.index or model.satisfied(bi):
                continue
            outer = set(model.live(bi))
            if inner <= outer and len(outer) > len(inner):
                b = model.constraints[bi]
                for lit in sorted(outer - inner):
                    model.eliminate(
                        lit,
                        "subsumption",
                        f"{a.name} already uses one of {b.name}",
                    )
                return True
    return False


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
        for bs in self._covers(union, (), group):
            extra = frozenset().union(*(self.live[b] for b in bs)) - union
            if extra:
                self._eliminate(group, bs, extra)
                return True
        return False

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

    def _eliminate(
        self,
        group: frozenset[ConstraintId],
        bs: tuple[ConstraintId, ...],
        extra: frozenset[LiteralId],
    ) -> None:
        constraints = self.model.constraints
        a_names = ", ".join(constraints[a].name for a in sorted(group))
        b_names = ", ".join(constraints[b].name for b in bs)
        for lit in sorted(extra):
            self.model.eliminate(lit, f"cover{self.k}", f"{a_names} use up {b_names}")


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
        for lit in model.options(var):
            refutation = _refute(model, lit)
            if refutation is not None:
                model.eliminate(lit, "what_if", refutation)
                return True
    return False


def _refute(model: Model, lit: LiteralId) -> str | None:
    """Why assuming `lit` leads to a contradiction, or None if it does not."""
    twin = model.clone()
    try:
        twin.assign(lit, "what_if", "assumed")
        twin.check()
        while any(rule(twin) for rule in _WHAT_IF_INNER):
            twin.check()
    except Contradiction as exc:
        return f"assuming it leads, in {len(twin.log)} steps, to: {exc}"
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
