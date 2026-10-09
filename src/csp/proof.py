"""A short proof of a solution, for explaining it the way a person would.

The solver logs everything it rules out, including much that turns out not
to matter.

1. `shortest` keeps as few of the solver's deductions as it can. Each
   deduction is a `Move` that can be replayed on its own; placing someone
   who has one option left (or the one person left for a row) is free.
   Moves are dropped one at a time, hardest first, as long as the rest
   still solve the puzzle.
2. `essential` trims a what_if: of the steps it took from its assumption,
   it keeps those the contradiction needed. A step needs

   * a placement: every other option of its constraint ruled out;
   * a consequence of a placement: that placement;
   * a relation's ruling: for each way the relation could still have held,
     one of the values involved ruled out (the earliest);
   * subsumption and cover: the ruled-out options of the constraints that
     were found to fit inside the others.

Uses only the public `Model` API and `Step` provenance, so it works for
every puzzle family and knows nothing about wording.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from itertools import product
from typing import Any

from .core import (
    Kind,
    LiteralId,
    Model,
    Step,
    StepCallback,
    cover,
    prune_relation,
    refute,
    rule_single,
)

type Key = tuple[int, int]  # (0, i): main log step i; (1, j): step j of a trail

HARDEST_FIRST = ("what_if", "cover3", "cover2", "relations", "subsumption")


@dataclass(frozen=True)
class Move:
    """One deduction the solver made, as something that can be made again."""

    rule: str
    sources: tuple[str, ...]
    scope: tuple[str, ...] = ()
    target: tuple[str, Any] | None = None  # what_if: the value refuted

    @classmethod
    def of(cls, rule: str, steps: Sequence[Step]) -> "Move | None":
        """The move behind one rule firing, or None for a free placement."""
        if rule == "single":
            return None
        first = steps[0]
        target = (first.var, first.value) if rule == "what_if" else None
        return cls(rule, first.sources, first.scope, target)

    def apply(self, model: Model) -> bool:
        if self.target is not None:
            return refute(model, model.literal(*self.target))
        if self.scope:
            index = {c.name: c.index for c in model.constraints}
            return cover(model, [index[n] for n in self.sources], [index[n] for n in self.scope])
        (relation,) = (r for r in model.relations if r.name == self.sources[0])
        return prune_relation(model, relation)


def replay(start: Model, moves: Iterable[Move], on_step: StepCallback | None = None) -> Model:
    """A copy of `start` after `moves`, each followed by every free placement.

    `on_step` hears of each move that changed something and each placement,
    as `Solver.solve` reports them.
    """
    model = start.clone()

    def run(rule: str, apply: Callable[[Model], bool]) -> bool:
        mark = len(model.log)
        changed = apply(model)
        if changed and on_step is not None:
            on_step(rule, model.log[mark:])
        return changed

    def settle() -> None:
        while model.solution() is None and run("single", rule_single):
            pass

    settle()
    for move in moves:
        run(move.rule, move.apply)
        settle()
    return model


def shortest(start: Model, moves: Sequence[Move]) -> list[Move]:
    """As few of `moves` as still solve the puzzle from `start`."""
    kept = list(moves)
    for rule in HARDEST_FIRST:
        for move in reversed([m for m in kept if m.rule == rule]):
            fewer = [m for m in kept if m is not move]
            if replay(start, fewer).solution() is not None:
                kept = fewer
    return kept


def essential(model: Model, history: Sequence[Step], step: Step) -> list[int]:
    """Indices into what_if `step`'s trail that its contradiction needed.

    `history` is every step logged before `step`, compile time included.
    """
    state = _Replay(model)
    for i, earlier in enumerate(history):
        state.mark(earlier, (0, i))
    deps = [state.record(s, (1, j)) for j, s in enumerate(step.trail)]
    root = state.broken(step.sources[0] if step.sources else None, len(step.trail))
    return sorted(j for kind, j in _close(root, deps) if kind == 1)


def _close(start: set[Key], trail: list[set[Key]]) -> set[Key]:
    """Everything `start` reaches through a trail's dependencies."""
    seen: set[Key] = set()
    todo = list(start)
    while todo:
        key = todo.pop()
        if key in seen:
            continue
        seen.add(key)
        if key[0] == 1:
            todo += trail[key[1]]
    return seen


class _Replay:
    """The truth state as the log is replayed, and what each step needed."""

    def __init__(self, model: Model) -> None:
        self.model = model
        self.out: dict[LiteralId, Key] = {}  # ruled out, by which step
        self.placed: dict[LiteralId, Key] = {}
        self.constraints = {c.name: c for c in model.constraints}
        self.relations = {r.name: r for r in model.relations}
        self.supports: dict[tuple[str, LiteralId], list[tuple[LiteralId, ...]]] = {}

    def lit(self, var: str, value: Any) -> LiteralId:
        return self.model.literal(var, value)

    def mark(self, step: Step, key: Key) -> None:
        target = self.placed if step.asserted else self.out
        target[self.lit(step.var, step.value)] = key

    def record(self, step: Step, key: Key) -> set[Key]:
        """What `step` needed, given the state so far; then apply it."""
        needs = self._needs(step)
        self.mark(step, key)
        return needs

    def _needs(self, step: Step) -> set[Key]:
        lit = self.lit(step.var, step.value)
        if step.placing is not None:
            return {self.placed[self.lit(*step.placing)]}
        if not step.sources:
            return set()
        if step.scope:
            outside = {x for name in step.scope for x in self.constraints[name].literals}
            return self._out_of(
                x for name in step.sources for x in self.constraints[name].literals
                if x not in outside
            )  # fmt: skip
        (source,) = step.sources[:1]
        if source in self.relations:
            return self._unsupported(source, lit)
        if source in self.constraints and step.asserted:
            return self._out_of(x for x in self.constraints[source].literals if x != lit)
        return set()

    def _out_of(self, literals: Iterable[LiteralId]) -> set[Key]:
        return {self.out[x] for x in literals if x in self.out}

    def _unsupported(self, name: str, lit: LiteralId) -> set[Key]:
        """For each way `name` could hold with `lit`, the earliest ruling that ended it."""
        needs: set[Key] = set()
        for combo in self._supports(name, lit):
            killers = [self.out[x] for x in combo if x in self.out]
            if killers:
                needs.add(min(killers))
        return needs

    def _supports(self, name: str, lit: LiteralId) -> list[tuple[LiteralId, ...]]:
        """Every combination of the other variables' literals that satisfies
        relation `name` together with `lit`, ignoring the current state."""
        key = (name, lit)
        if key not in self.supports:
            relation = self.relations[name]
            mine = self.model.var_of(lit)
            domains = [
                [lit] if var == mine else self.model.constraints[self.model.domain_of(var)].literals
                for var in relation.variables
            ]
            self.supports[key] = [
                tuple(x for x in combo if x != lit)
                for combo in product(*domains)
                if relation.holds(*(self.model.value_of(x) for x in combo))
            ]
        return self.supports[key]

    def broken(self, source: str | None, trail_length: int) -> set[Key]:
        """What the contradiction that ended a trail needed."""
        if source in self.constraints:
            constraint = self.constraints[source]
            true = {self.placed[x] for x in constraint.literals if x in self.placed}
            if len(true) > 1:
                return true
            if constraint.kind is Kind.EXACTLY_ONE:
                return self._out_of(constraint.literals)
        if source in self.relations:
            relation = self.relations[source]
            needs: set[Key] = set()
            for x, key in self.placed.items():
                if self.model.var_of(x) in relation.variables:
                    needs |= {key} | self._unsupported(source, x)
            return needs
        return {(1, j) for j in range(trail_length)}
