# Notes for agents working on this repo

Read `README.md` first for the model and how the two puzzles map onto it.
This file covers intent, invariants, and the things that are easy to get
wrong.

## Intent

A single constraint engine that solves many puzzle families **the way a person
would** — by named deduction rules that can explain themselves — rather than
by search. Adding a puzzle should mean writing a compiler, not touching the
solver.

Explainability is a goal, not a side effect: every deduction lands in
`model.log` with a rule name and a human-readable reason, which is what
`--verbose` and `--step` print.

## Invariants — do not break these

**`AT_MOST_ONE` must never force a value.** It forbids a second truth; it does
not require a first. Only `EXACTLY_ONE` licenses "one option left, therefore
it holds". An earlier version of this code had one `Group` type doing both
jobs, which is sound for Sudoku (9 cells, 9 digits, each used once) and
unsound for Murdoku (7 people, 43 squares, most empty). It concluded things
like "square 37 only fits Vladimir, so Vladimir is there". There is a
regression test for this: `test_at_most_one_does_not_force`.

**Rules return `True` only if they changed something**, and the solver
restarts the ladder on any success. A rule that reports change without
changing state loops forever.

**`core.py` imports nothing from puzzle modules.** Progress is reported via
the `on_step` callback so the engine never learns how to draw a board. If you
find yourself importing a renderer into core, the callback is what you want.

**Every rule must be sound for any model**, not just the puzzles in
`examples/`. Prove it before adding it. `rule_subsumption` carries its proof
in the docstring; follow that pattern.

**Only `core` touches model internals.** Puzzle modules, the CLI and the
tests use the public `Model` API (`literal`, `constrain`, `relate`, the
inspection methods, `assign`/`eliminate`). Renderers learn what changed from
`Step.var`/`Step.value`, never by parsing strings.

## Interfaces

| Boundary | Contract |
|---|---|
| puzzle module -> engine | `compile_puzzle(...) -> Model` |
| engine -> rules | `Rule(name, apply)`, `apply(model) -> bool`; log every deduction under `name` |
| engine -> caller | `Solver(model, rules).solve(on_step) -> Result` |
| progress | `on_step(rule_name, steps)` after each rule that fires |
| CLI -> puzzle | `cli.load(text, kind) -> Puzzle(kind, model, draw)` |

## Adding a rule

Write `rule_x(model) -> bool` in `core.py`, add `Rule("x", rule_x)` to
`DEFAULT_RULES` in cost order, and add a unit test that exercises it on a
hand-built model of a few literals (see
`test_subsumption_prunes_the_wider_constraint`).
`test_every_step_is_logged_under_its_rule_name` fails if the name passed to
`assign`/`eliminate` does not match the `Rule` name.

Candidates, roughly in order of value:

- ~~Naked / hidden subsets, Fish~~ — done as `rule_cover(k)`, the
  *k*-constraint generalisation of subsumption. One rule covers all four
  Sudoku patterns; only connected groups of anchors are searched. *k*=4
  (quads, Jellyfish) is not in the ladder: no example needs it.
- **Chains.** Build the implication graph over literals (eliminating *x*
  forces *y* when some `EXACTLY_ONE` drops to one option) and look for
  contradictions. `what_if` already finds what short chains would, at more
  cost; chains would explain the same deduction more like a person does.
- ~~Bounded what-if~~ — done as `rule_what_if`, using `Model.clone()`. It
  runs only `single`/`relations`/`subsumption` on the copy, never itself,
  so it stays one level deep.

Keep the ladder honest: if a rule never fires on any example, say so rather
than listing it as working.

## Adding a puzzle family

1. New module with `compile_puzzle(...) -> Model`.
2. Pick the variables carefully — **this is where the real design work is.**
   Ask what the puzzle's constraints quantify over. Murdoku's "one figure per
   row" is about people, so people are the variables; copying Sudoku's
   cell-centric shape produced an unsatisfiable model.
3. Express every rule as `EXACTLY_ONE` / `AT_MOST_ONE` sets, plus relations
   (over two or more variables) for clues that link people.
4. A `render(..., title, highlight) -> str` function; `highlight` is a set
   of variable names.
5. Wire into `cli.detect` and `cli.load`.
6. Test against an **independent** source of truth — a published solution, or
   a property check (permutation, givens preserved). Self-consistency is not
   verification.

## Current rule coverage, measured

Numbers from actual runs, not estimates:

| Puzzle | Result | Rules that fired |
|---|---|---|
| `sudoku_easy.txt` | solved, 52 iterations | `single` 51 |
| `sudoku_pointing.txt` | solved, 60 iterations | `single` 57, `subsumption` 2 |
| `sudoku_naked_pair.txt` | solved, 65 iterations | `single` 58, `subsumption` 4, `cover2` 2 |
| `sudoku_hidden_pair.txt` | solved, 59 iterations | `single` 56, `cover2` 1, `subsumption` 1 |
| `sudoku_xwing.txt` | solved, 57 iterations | `single` 54, `cover2` 2 |
| `sudoku_swordfish.txt` | solved, 59 iterations | `single` 56, `cover2` 1, `cover3` 1 |
| `sudoku_what_if.txt` | solved, 66 iterations | `single` 55, `subsumption` 6, `cover2` 2, `what_if` 2 |
| `prrrdoku1.txt` | solved, 88 iterations | `relations` 79, `single` 7, `subsumption` 1 |
| `prrrdoku2.txt` | solved, 162 iterations | `relations` 149, `single` 9, `cover3` 1, `cover2` 1, `what_if` 1 |
| `prrrdoku3.txt` | solved, 178 iterations | `relations` 167, `single` 9, `subsumption` 1 |

The graded Sudokus were generated (random minimal puzzles, uniqueness checked
by backtracking) and picked because each needs its rule: the tests cut the
ladder just before it and assert the puzzle stalls. A single firing can
unlock a whole puzzle, so the counts are small.

On Prrrdoku 2, `cover3` is the document's step "Tim, Jos and Pip fill rows
1-3, so Anna is outside them", and `cover2` is "Pip and Mauw fill columns 8
and 9". The document then splits on Otto's square; `what_if` instead rules
out Tim on r2c3 (Jos is left with nowhere to go). Different route, same
answer.

## Known gaps

- Prrrdoku boards are **images** in `Prrrdoku.docx` — extract from
  `word/media/*.png` and read them; the tables in that file are colour
  legends, useful for matching colours to region names (read `w:fill`).
  Always cross-check a transcription against the candidate lists in the
  document's worked solution before trusting it.
- "Only Luna may stand in the water" is a board rule, written out as one
  `outside` clue per other person in `prrrdoku3.txt`.
- `relations` is plain arc consistency and re-scans every relation from
  scratch on each pass; it accounts for most Prrrdoku iterations. Three-way
  relations (`furthest`) make each scan quadratic in domain size. A
  dirty-variable queue would cut both.
