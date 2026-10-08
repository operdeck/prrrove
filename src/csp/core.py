"""Exact-cover constraint engine.

Every puzzle is expressed as:
  * literals  - atomic choices, e.g. "r3c4 = 7" or "Tim = r1c2"
  * constraints - sets of literals tagged EXACTLY_ONE or AT_MOST_ONE
  * relations  - pairwise predicates between two variables' choices

Nothing in this module knows about any particular puzzle.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Optional

UNKNOWN, TRUE, FALSE = 0, 1, -1


class Kind(Enum):
    """Whether a constraint must be satisfied, or merely may not be violated."""

    EXACTLY_ONE = "exactly one"
    AT_MOST_ONE = "at most one"


class Contradiction(Exception):
    """The current state cannot be extended to any solution."""


@dataclass(frozen=True)
class Literal:
    index: int
    var: str
    value: Any

    def __str__(self) -> str:
        return f"{self.var}={self.value}"


@dataclass(frozen=True)
class Constraint:
    index: int
    name: str
    kind: Kind
    literals: tuple[int, ...]


@dataclass(frozen=True)
class Relation:
    """`holds(value_of_a, value_of_b)` must be true in any solution."""

    name: str
    var_a: str
    var_b: str
    holds: Callable[[Any, Any], bool]


@dataclass(frozen=True)
class Step:
    literal: str
    asserted: bool
    rule: str
    reason: str

    def __str__(self) -> str:
        arrow = "=" if self.asserted else "x"
        return f"{arrow} {self.literal}  ({self.reason})"


class Model:
    """Literals, the constraints over them, and their current truth state."""

    def __init__(self) -> None:
        self._literals: list[Literal] = []
        self._by_key: dict[tuple[str, Any], int] = {}
        self._state: list[int] = []
        self._in_constraints: list[list[int]] = []
        self.constraints: list[Constraint] = []
        self.relations: list[Relation] = []
        self._domain_of: dict[str, int] = {}
        self.log: list[Step] = []

    # --- construction -----------------------------------------------------

    def literal(self, var: str, value: Any) -> int:
        key = (var, value)
        if key in self._by_key:
            return self._by_key[key]
        index = len(self._literals)
        self._literals.append(Literal(index, var, value))
        self._state.append(UNKNOWN)
        self._in_constraints.append([])
        self._by_key[key] = index
        return index

    def constrain(
        self,
        name: str,
        kind: Kind,
        literals: Iterable[int],
        *,
        defines: Optional[str] = None,
    ) -> int:
        """Add a constraint. `defines` marks it as a variable's whole domain."""
        index = len(self.constraints)
        self.constraints.append(Constraint(index, name, kind, tuple(literals)))
        for lit in self.constraints[index].literals:
            self._in_constraints[lit].append(index)
        if defines is not None:
            self._domain_of[defines] = index
        return index

    def relate(self, name: str, var_a: str, var_b: str, holds) -> None:
        self.relations.append(Relation(name, var_a, var_b, holds))

    # --- inspection -------------------------------------------------------

    def describe(self, lit: int) -> str:
        return str(self._literals[lit])

    def value_of(self, lit: int) -> Any:
        return self._literals[lit].value

    def is_true(self, lit: int) -> bool:
        return self._state[lit] == TRUE

    def is_false(self, lit: int) -> bool:
        return self._state[lit] == FALSE

    def constraints_of(self, lit: int) -> list[int]:
        return self._in_constraints[lit]

    def live(self, constraint: int) -> list[int]:
        """Literals of a constraint that are still undecided."""
        return [l for l in self.constraints[constraint].literals if self._state[l] == UNKNOWN]

    def satisfied(self, constraint: int) -> bool:
        return any(self._state[l] == TRUE for l in self.constraints[constraint].literals)

    @property
    def variables(self) -> list[str]:
        return list(self._domain_of)

    def options(self, var: str) -> list[int]:
        """Literals for `var` that are not ruled out (undecided or true)."""
        domain = self.constraints[self._domain_of[var]]
        return [l for l in domain.literals if self._state[l] != FALSE]

    def chosen(self, var: str) -> Optional[Any]:
        domain = self.constraints[self._domain_of[var]]
        for lit in domain.literals:
            if self._state[lit] == TRUE:
                return self._literals[lit].value
        return None

    def assignment(self) -> dict[str, Any]:
        """Variables decided so far."""
        decided = {}
        for var in self._domain_of:
            value = self.chosen(var)
            if value is not None:
                decided[var] = value
        return decided

    def solution(self) -> Optional[dict[str, Any]]:
        """Full assignment, or None if any variable is still open."""
        out: dict[str, Any] = {}
        for var in self._domain_of:
            value = self.chosen(var)
            if value is None:
                return None
            out[var] = value
        return out

    # --- mutation ---------------------------------------------------------

    def eliminate(self, lit: int, rule: str, reason: str) -> bool:
        if self._state[lit] == FALSE:
            return False
        if self._state[lit] == TRUE:
            raise Contradiction(f"{self.describe(lit)} is already true; {reason}")
        self._state[lit] = FALSE
        self.log.append(Step(self.describe(lit), False, rule, reason))
        return True

    def assign(self, lit: int, rule: str, reason: str) -> bool:
        if self._state[lit] == TRUE:
            return False
        if self._state[lit] == FALSE:
            raise Contradiction(f"{self.describe(lit)} is already ruled out; {reason}")
        self._state[lit] = TRUE
        self.log.append(Step(self.describe(lit), True, rule, reason))
        # One literal true in a constraint rules out every sibling, whatever
        # the kind: EXACTLY_ONE and AT_MOST_ONE both cap the count at one.
        for ci in self._in_constraints[lit]:
            constraint = self.constraints[ci]
            for other in constraint.literals:
                if other != lit and self._state[other] == UNKNOWN:
                    self.eliminate(
                        other, rule, f"{self.describe(lit)} holds in {constraint.name}"
                    )
        return True

    def check(self) -> None:
        """Raise Contradiction if the state is already unsatisfiable."""
        for constraint in self.constraints:
            truths = sum(1 for l in constraint.literals if self._state[l] == TRUE)
            if truths > 1:
                raise Contradiction(f"{constraint.name}: more than one literal true")
            if constraint.kind is Kind.EXACTLY_ONE and truths == 0:
                if not any(self._state[l] == UNKNOWN for l in constraint.literals):
                    raise Contradiction(f"{constraint.name}: every option eliminated")


# --- rules ----------------------------------------------------------------
# A rule inspects the model, applies at most one deduction, and reports
# whether it changed anything. All are sound for any model.


def rule_single(model: Model) -> bool:
    """An EXACTLY_ONE constraint with one option left forces that option.

    This covers Sudoku's naked single (the constraint is "this cell holds one
    digit") and its hidden single (the constraint is "this digit sits once in
    this row") with no special-casing.
    """
    for constraint in model.constraints:
        if constraint.kind is not Kind.EXACTLY_ONE:
            continue
        if model.satisfied(constraint.index):
            continue
        live = model.live(constraint.index)
        if len(live) == 1:
            model.assign(live[0], "single", f"only option left in {constraint.name}")
            return True
    return False


def rule_relations(model: Model) -> bool:
    """Drop choices that no longer have a partner satisfying some relation."""
    for relation in model.relations:
        for forward in (True, False):
            this = relation.var_a if forward else relation.var_b
            other = relation.var_b if forward else relation.var_a
            supports = model.options(other)
            for lit in model.options(this):
                if model.is_true(lit):
                    continue
                mine = model.value_of(lit)
                ok = False
                for partner in supports:
                    theirs = model.value_of(partner)
                    pair = (mine, theirs) if forward else (theirs, mine)
                    if relation.holds(*pair):
                        ok = True
                        break
                if not ok:
                    model.eliminate(
                        lit, "relation", f"no partner for {relation.name}"
                    )
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
    """Subsumption over k constraints at once.

    Let A1..Ak be EXACTLY_ONE with pairwise disjoint live sets, and B1..Bk be
    other constraints whose live literals together contain every live literal
    of the As. The As make k distinct literals true, each lying in some B.
    The Bs hold at most k truths between them, so those k use up every B -
    any B-literal outside the As is false.

    In Sudoku, As as cells and Bs as digit-in-house give naked subsets;
    swapped, hidden subsets; As as digit-in-row and Bs as digit-in-column
    give X-Wing (k=2) and Swordfish (k=3). The rule sees none of that.

    Only connected groups of As are tried: a disconnected group splits into
    smaller groups that a lower k already finds.
    """

    def rule(model: Model) -> bool:
        live = {
            c.index: frozenset(model.live(c.index))
            for c in model.constraints
            if not model.satisfied(c.index)
        }
        anchors = [
            ci for ci, lits in live.items()
            if lits and model.constraints[ci].kind is Kind.EXACTLY_ONE
        ]
        anchor_set = set(anchors)

        def covers(need: frozenset, used: tuple, excluded: frozenset):
            if not need:
                yield used
                return
            if len(used) == k:
                return
            for bi in model.constraints_of(min(need)):
                if bi in excluded or bi in used or bi not in live:
                    continue
                yield from covers(need - live[bi], used + (bi,), excluded)

        def neighbours(group: frozenset, union: frozenset, first: int) -> set[int]:
            near: set[int] = set()
            for lit in union:
                for ci in model.constraints_of(lit):
                    for other in live.get(ci, ()):
                        near.update(model.constraints_of(other))
            return {
                ci for ci in near
                if ci in anchor_set and ci > first and ci not in group
                and not (live[ci] & union)
            }

        seen: set[frozenset] = set()

        def grow(group: frozenset, union: frozenset, first: int) -> bool:
            if group in seen:
                return False
            seen.add(group)
            if next(covers(union, (), group), None) is None:
                return False
            if len(group) == k:
                for bs in covers(union, (), group):
                    extra = set().union(*(live[b] for b in bs)) - union
                    if extra:
                        a_names = ", ".join(model.constraints[a].name for a in sorted(group))
                        b_names = ", ".join(model.constraints[b].name for b in bs)
                        for lit in sorted(extra):
                            model.eliminate(
                                lit,
                                f"cover{k}",
                                f"{a_names} use up {b_names}",
                            )
                        return True
                return False
            for ci in sorted(neighbours(group, union, first)):
                if grow(group | {ci}, union | live[ci], first):
                    return True
            return False

        for a in anchors:
            if grow(frozenset([a]), live[a], a):
                return True
        return False

    rule.__name__ = f"rule_cover{k}"
    return rule


DEFAULT_RULES: list[tuple[str, Callable[[Model], bool]]] = [
    ("single", rule_single),
    ("relations", rule_relations),
    ("subsumption", rule_subsumption),
    ("cover2", rule_cover(2)),
    ("cover3", rule_cover(3)),
]


@dataclass
class Result:
    solved: bool
    contradiction: Optional[str]
    assignment: dict[str, Any]
    iterations: int


class Solver:
    """Applies rules cheapest-first until nothing more can be deduced."""

    def __init__(self, model: Model, rules=None) -> None:
        self.model = model
        self.rules = list(rules if rules is not None else DEFAULT_RULES)

    def add_rule(self, name: str, rule: Callable[[Model], bool]) -> None:
        self.rules.append((name, rule))

    def solve(self, on_step: Optional[Callable[[str, list[Step]], None]] = None) -> Result:
        """Run to a fixed point.

        `on_step` is called with the rule name and the log entries it produced,
        so callers can render progress without core knowing how to draw.
        """
        iterations = 0
        try:
            self.model.check()
            while True:
                iterations += 1
                for name, rule in self.rules:
                    mark = len(self.model.log)
                    if rule(self.model):
                        self.model.check()
                        if on_step is not None:
                            on_step(name, self.model.log[mark:])
                        break
                else:
                    break
        except Contradiction as exc:
            return Result(False, str(exc), self.model.assignment(), iterations)

        solution = self.model.solution()
        return Result(
            solution is not None, None, solution or self.model.assignment(), iterations
        )
