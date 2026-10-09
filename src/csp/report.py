"""A plain-text account of a compiled model: what the engine actually sees.

Uses only the public `Model` API, so every puzzle family is explained the
same way. `csp --show-model` prints it.
"""

import inspect
import re
import textwrap
from collections import Counter
from collections.abc import Iterable, Sequence
from itertools import product
from math import prod

from .core import DEFAULT_RULES, Constraint, Kind, LiteralId, Model, Rule, Step

ROWS = 12  # longest list printed before eliding the rest
MAX_COMBINATIONS = 250_000  # relations with more value combinations are not counted
WIDTH = 78


def describe(model: Model, rules: Sequence[Rule] = DEFAULT_RULES) -> str:
    """The model, then the algorithm that will run on it."""
    sections = (
        _overview(model),
        _variables(model),
        _constraints(model),
        _connections(model),
        _compile_time(model),
        _relations(model),
        _algorithm(rules),
    )
    return "\n\n".join(s for s in sections if s)


def grade(fired: Iterable[str], rules: Sequence[Rule] = DEFAULT_RULES) -> str:
    """The hardest rule a solve used, as the puzzle's grade.

    Cheaper rules are always tried first, so the hardest rule only fired
    when everything below it had stalled: this solver could not do without it.
    """
    order = [rule.name for rule in rules]
    used = {name for name in fired if name in order}
    return max(used, key=order.index) if used else "none"


def rules_used(fired: Iterable[str], rules: Sequence[Rule] = DEFAULT_RULES) -> str:
    """'rules used: single 51, cover2 2; grade: cover2', ladder order."""
    counts = Counter(fired)
    listed = ", ".join(f"{r.name} {counts[r.name]}" for r in rules if counts[r.name])
    return f"rules used: {listed or 'none'}; grade: {grade(counts, rules)}"


# --- sections -------------------------------------------------------------


def _overview(model: Model) -> str:
    kinds = Counter(c.kind for c in model.constraints)
    lines = _heading("The model")
    lines.append(
        f"{len(model.variables)} variables, {model.num_literals} literals, "
        f"{len(model.constraints)} constraints, {len(model.relations)} relations."
    )
    lines.append("")
    lines += _define(
        "literal",
        "one possible choice, written variable=value. Each is true, false, or not yet known.",
    )
    lines += _define(
        "constraint",
        f"a set of literals. EXACTLY_ONE ({kinds[Kind.EXACTLY_ONE]} here): exactly one of "
        f"them must end up true. AT_MOST_ONE ({kinds[Kind.AT_MOST_ONE]} here): no two may "
        "be true, but none is fine.",
    )
    lines += _define("relation", "a yes/no test on the values of two or more variables.")
    lines.append("")
    lines += _wrap(
        "Solving only ever marks literals true or false. Nothing below knows what "
        "puzzle it came from."
    )
    return "\n".join(lines)


def _variables(model: Model) -> str:
    decided = [v for v in model.variables if model.chosen(v) is not None]
    undecided = sorted(
        (v for v in model.variables if model.chosen(v) is None),
        key=lambda v: len(model.options(v)),
    )
    lines = _heading(f"Variables ({len(model.variables)})")
    lines += _wrap(
        "A variable is the EXACTLY_ONE constraint over all its literals, so it ends "
        "up with exactly one value."
    )
    if decided:
        values = [f"{v}={model.chosen(v)}" for v in decided]
        lines.append(_fit(f"Decided before solving ({len(decided)}): ", values))
    if undecided:
        lines.append(f"Open ({len(undecided)}), fewest options first:")
        width = max(len(v) for v in undecided)
        for var in undecided[:ROWS]:
            options = model.options(var)
            domain = len(model.constraints[model.domain_of(var)].literals)
            prefix = f"  {var:<{width}}  {len(options):>3} of {domain:<3}  "
            lines.append(_fit(prefix, [str(model.value_of(lit)) for lit in options]))
        if len(undecided) > ROWS:
            lines.append(f"  ... and {len(undecided) - ROWS} more")
    return "\n".join(lines)


def _constraints(model: Model) -> str:
    families: dict[str, list[Constraint]] = {}
    for c in model.constraints:
        families.setdefault(_family(c), []).append(c)
    domains = {model.domain_of(v) for v in model.variables}

    lines = _heading(f"Constraints ({len(model.constraints)}) in {len(families)} families")
    width = max(len(f) for f in families)
    lines.append(f"  {'family':<{width}}  {'kind':<11}  count  size")
    for family, members in families.items():
        sizes = sorted({len(c.literals) for c in members})
        size = str(sizes[0]) if len(sizes) == 1 else f"{sizes[0]}-{sizes[-1]}"
        mark = "*" if all(c.index in domains for c in members) else " "
        kind = members[0].kind.name
        lines.append(f"{mark} {family:<{width}}  {kind:<11}  {len(members):>5}  {size}")
    lines.append("* defines the variables. size = literals per constraint.")
    lines += ["", "One example of each:"]
    for members in families.values():
        c = members[0]
        lines.append(_fit(f"  {c.name}: ", [model.describe(lit) for lit in c.literals]))
    return "\n".join(lines)


def _connections(model: Model) -> str:
    """How constraints overlap: the part that makes deduction possible."""
    membership = Counter(lit for c in model.constraints for lit in c.literals)
    spread = Counter(membership.values())
    lines = _heading("How literals and constraints connect")
    if len(spread) == 1:
        (n,) = spread
        lines.append(f"Every literal sits in exactly {n} constraints.")
    else:
        parts = [f"{count} literals in {n}" for n, count in sorted(spread.items())]
        lines += _wrap(f"Literals by number of constraints they sit in: {', '.join(parts)}.")

    lit = _example_literal(model)
    if lit is None:
        return "\n".join(lines)
    lines += ["", f"For example, {model.describe(lit)} sits in:"]
    rivals: set[LiteralId] = set()
    for ci in model.constraints_of(lit):
        c = model.constraints[ci]
        live = model.live(ci)
        rivals.update(other for other in live if other != lit)
        lines.append(f"  {c.kind.name:<11}  {c.name:<30} {len(live):>3} literals open")
    lines.append("")
    lines += _wrap(
        f"Making it true rules out the {len(rivals)} other open literals in those "
        "constraints. Ruling it out leaves each of them one option fewer, and an "
        "EXACTLY_ONE left with one option forces it. Every rule is a way of "
        "exploiting these overlaps."
    )
    return "\n".join(lines)


def _compile_time(model: Model) -> str:
    if not model.log:
        return ""
    by_rule: dict[str, list[Step]] = {}
    for step in model.log:
        by_rule.setdefault(step.rule, []).append(step)

    lines = _heading("Settled while compiling")
    lines += _wrap(
        "Givens and clues about a single variable are applied as the model is "
        "built, through the same assign/eliminate the rules use:"
    )
    for rule, steps in by_rule.items():
        made = sum(s.asserted for s in steps)
        lines.append(f"  {rule}: {made} set true, {len(steps) - made} ruled out")
        reasons = Counter(s.reason for s in steps if not s.asserted)
        if len(reasons) <= 2 * ROWS:
            width = max(len(r) for r in reasons)
            lines += [f"    {r:<{width}}  {n:>4} ruled out" for r, n in reasons.items()]
    return "\n".join(lines)


def _relations(model: Model) -> str:
    if not model.relations:
        return ""
    lines = _heading(f"Relations ({len(model.relations)})")
    lines += _wrap(
        "The engine treats each test as a black box and only calls it on values. "
        "Allowed: how many combinations of the still-open values pass."
    )
    width = max(len(r.name) for r in model.relations)
    for relation in model.relations:
        domains = [model.options(var) for var in relation.variables]
        total = prod(len(d) for d in domains)
        if total <= MAX_COMBINATIONS:
            allowed = sum(
                relation.holds(*(model.value_of(lit) for lit in combo))
                for combo in product(*domains)
            )
            stat = f"{allowed:>6} of {total}"
        else:
            stat = f"{total} combinations, too many to count"
        lines.append(f"  {relation.name:<{width}}  {stat}")
    return "\n".join(lines)


def _algorithm(rules: Sequence[Rule]) -> str:
    lines = _heading("How the solver will run")
    lines += _wrap(
        "Try the rules below in order. As soon as one changes something, check that "
        "no constraint is broken and start again from the top. Stop when no rule "
        "applies (solved, or stuck) or a constraint can no longer be met "
        "(contradiction). Cheap rules come first, so the expensive ones only run "
        "when nothing simpler works."
    )
    lines.append("")
    width = max(len(r.name) for r in rules)
    for i, rule in enumerate(rules, 1):
        doc = inspect.getdoc(rule.apply) or ""
        summary = " ".join(doc.split("\n\n")[0].split())
        prefix = f"  {i}. {rule.name:<{width}}  "
        lines.append(
            textwrap.fill(
                summary,
                WIDTH,
                initial_indent=prefix,
                subsequent_indent=" " * len(prefix),
            )
        )
    return "\n".join(lines)


# --- helpers --------------------------------------------------------------


def _heading(title: str) -> list[str]:
    return [title, "-" * len(title)]


def _wrap(text: str) -> list[str]:
    return textwrap.wrap(text, WIDTH)


def _define(term: str, meaning: str) -> list[str]:
    prefix = f"  {term:<11} "
    return textwrap.wrap(meaning, WIDTH, initial_indent=prefix, subsequent_indent=" " * len(prefix))


def _fit(prefix: str, items: Sequence[str]) -> str:
    """`prefix` and as many items as fit on one line, counting the rest."""
    line = prefix
    for shown, item in enumerate(items):
        rest = len(items) - shown
        tail = f"... (+{rest})"
        if len(line) + len(item) + 1 + (len(tail) + 1 if rest > 1 else 0) > WIDTH:
            return line + tail
        line += item + " "
    return line.rstrip()


def _family(constraint: Constraint) -> str:
    """The constraint's family, or its name with numbers masked if it has none."""
    return constraint.family or re.sub(r"\d+", "#", constraint.name)


def _example_literal(model: Model) -> LiteralId | None:
    """An open literal of the most constrained open variable."""
    for var in sorted(model.variables, key=lambda v: len(model.options(v))):
        if model.chosen(var) is None:
            return model.options(var)[0]
    return None
