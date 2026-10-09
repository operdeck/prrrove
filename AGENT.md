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

**Solving, explaining and drawing are separate layers.** `core` records
*why* each step happened as structure on `Step` (`sources`, `scope`,
`placing`, `trail`), never as wording. `proof` shortens a solve using only
that and the public API. `murdoku` owns the board and what clues mean, and
`board_rules()` is the structured meaning of its constraints — look names
up there, never parse them. Wording (`Language:`, `Words:`, phrasebooks)
lives only in `story`; pictures only in `picture`. Explanation concerns
never go on `Board` or into `core`. `test_modules_only_import_their_own_layer`
enforces the import graph.

## Interfaces

| Boundary | Contract |
|---|---|
| puzzle module -> engine | `compile_puzzle(...) -> Model` |
| engine -> rules | `Rule(name, apply)`, `apply(model) -> bool`; log every deduction under `name` |
| engine -> caller | `Solver(model, rules).solve(on_step) -> Result` |
| progress | `on_step(rule_name, steps)` after each rule that fires |
| CLI -> puzzle | `cli.load(text, kind) -> Puzzle(kind, model, draw)` |
| explanation | `report.describe(model, rules) -> str`, public `Model` API only |
| proof | `Move.of(rule, steps)`, `shortest(start, moves)`, `replay(start, moves, on_step)`, `essential(model, history, step)` |
| worked solution | `story.explain(text) -> str`; Murdoku only, reads `proof` and `murdoku` |
| brute force | `bruteforce.solutions(text, kind, limit) -> list[dict]`; never imports `core` |

Label every constraint with `family=` when compiling a new puzzle type;
`--show-model` groups by it and falls back to the name with digits masked.
The first paragraph of each rule's docstring is what `--show-model` prints
as that rule's summary, so keep it to one plain sentence.

## Committing and publishing

The repo is **public** (`origin` = `github.com/operdeck/prrrove`).

- **Branch, check, merge.** Work on a feature branch in small,
  single-purpose commits. Before merging into `main` (fast-forward only), all
  of these must pass: `uvx ruff check src tests`, `uvx ruff format --check
  src tests`, `uv run mypy src`, `uv run pytest -q`.
- **`prrrdokus/` never leaves this machine.** It holds the private source
  documents; it is gitignored and was removed from all history. Stage files
  by explicit path, never `git add -A`. Before every push, this must print
  `0`: `git rev-list --objects --all | grep -ciE '\.(docx|pdf)$|prrrdokus/'`.
- **Push as `operdeck`, without prompts:** `GIT_TERMINAL_PROMPT=0 git push
  origin main`. The repo's local git config gets the token from
  `gh auth token --user operdeck`; do not switch the global `gh` account, and
  do not rely on the global credential helpers (they hang on a hidden prompt).
- **Never force-push** or rewrite history that is on `origin`.
- **Published puzzles are not copied.** `prrrdoku1-3.txt` are the owner's
  own puzzles. Anything taken from a book or newspaper gets new names or is
  generated instead, as `murdoku_intro.txt` and the graded Sudokus and
  Calcudokus are.
- **README pictures and solutions are generated**, never hand-edited: redraw
  `docs/images/*.png` with `--png` and re-run `--explain` whenever drawing or
  wording changes, and keep the README in step. In the README, "Prrrdoku"
  appears only as the example file names, not as a general term.

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
4. A `render(..., title, steps) -> str` function. `steps` are the deductions
   just made; show what they changed, including eliminations a person would
   mark on paper (Murdoku crosses out squares nobody can reach).
5. Wire into `puzzlefile.detect` and `cli.load`.
6. Add `bruteforce/<family>.py` with `solutions(text, limit) -> list[dict]`,
   a plain search sharing only the reader and the rule definitions. Keep the
   rule definitions (what a clue or cage *means*) in one place that both the
   compiler and the brute force call, as `murdoku.conditions` does.
7. Test against an **independent** source of truth — a published solution,
   the brute force, or a property check (permutation, givens preserved).
   Self-consistency is not verification.

## Current rule coverage, measured

Numbers from actual runs, not estimates:

| Puzzle | Result | Rules that fired |
|---|---|---|
| `sudoku_4x4.txt` | solved, 12 iterations | `single` 11 |
| `sudoku_easy.txt` | solved, 52 iterations | `single` 51 |
| `sudoku_pointing.txt` | solved, 60 iterations | `single` 57, `subsumption` 2 |
| `sudoku_naked_pair.txt` | solved, 65 iterations | `single` 58, `subsumption` 4, `cover2` 2 |
| `sudoku_hidden_pair.txt` | solved, 59 iterations | `single` 56, `cover2` 1, `subsumption` 1 |
| `sudoku_xwing.txt` | solved, 57 iterations | `single` 54, `cover2` 2 |
| `sudoku_swordfish.txt` | solved, 59 iterations | `single` 56, `cover2` 1, `cover3` 1 |
| `sudoku_what_if.txt` | solved, 66 iterations | `single` 55, `subsumption` 6, `cover2` 2, `what_if` 2 |
| `murdoku_intro.txt` | solved, 5 iterations | `single` 4 |
| `murdoku_house.txt` | solved, 11 iterations | `single` 5, `relations` 4, `subsumption` 1 |
| `prrrdoku1.txt` | solved, 14 iterations | `single` 7, `relations` 5, `subsumption` 1 |
| `prrrdoku2.txt` | solved, 22 iterations | `relations` 9, `single` 9, `cover3` 1, `cover2` 1, `what_if` 1 |
| `prrrdoku3.txt` | solved, 41 iterations | `relations` 15, `single` 9, `what_if` 9, `subsumption` 7 |
| `calcudoku_4x4_easy.txt` | solved, 22 iterations | `single` 15, `relations` 6 |
| `calcudoku_6x6_medium.txt` | solved, 57 iterations | `single` 35, `relations` 21 |
| `calcudoku_6x6_hard.txt` | solved, 60 iterations | `single` 36, `relations` 20, `cover2` 3 |
| `calcudoku_6x6_fiendish.txt` | solved, 73 iterations | `single` 35, `relations` 30, `cover2` 4, `what_if` 3 |
| `calcudoku_7x7_hard.txt` | solved, 80 iterations | `single` 47, `relations` 26, `cover2` 4, `cover3` 2 |

The Calcudokus were generated the same way as the graded Sudokus (random
Latin square, random cages, uniqueness checked by brute force) because
newspaper puzzles are copyrighted. `test_every_example_is_unique_and_the_engine_finds_it`
re-checks every example with `csp.bruteforce`. Most random 6x6 Calcudokus need only `relations`; about
one in ten needs `cover2`, and fewer need `what_if`.

The graded Sudokus were generated (random minimal puzzles, uniqueness checked
by backtracking) and picked because each needs its rule: the tests cut the
ladder just before it and assert the puzzle stalls. A single firing can
unlock a whole puzzle, so the counts are small.

On Prrrdoku 2, `cover3` is the document's step "Tim, Jos and Pip fill rows
1-3, so Anna is outside them", and `cover2` is "Pip and Mao fill columns 8
and 9". The document then splits on Otto's square; `what_if` instead rules
out Tim on r2c3 (Jos is left with nowhere to go). Different route, same
answer.

Prrrdoku 3 leans on `what_if` hardest (9 firings). The document's own
solution argues by cases there too ("Waar zit Anna?") rather than with a
single named pattern. Chains would explain that more like a person does.

## Known gaps

- The Prrrdoku documents are in `prrrdokus/`, one per puzzle. Their boards
  are **images**: extract from `word/media/*.png` and read them; the tables
  are colour legends, useful for matching colours to region names (read
  `w:fill`). Always cross-check a transcription against the candidate lists
  in the document's worked solution, and run `--brute-force` on it.
- Puzzle 3 as first published had no solution once "next to" stays within a
  region: the koffer on r1c5 sat in Bankastraat. Its board, solution picture
  and worked solution were corrected (r1c5 now in Helmholtzstraat); puzzle
  1's worked solution listed a cross-region square for Tjitske and was
  corrected too. The answers did not change.
- "Only Luna may stand in the water" is a board rule, written out as one
  `outside` line per other person in the `Rules:` section of
  `prrrdoku3.txt`, so clue numbers still match the document.
- `--explain` follows the solver's own route, shortened. Where the solver
  needs `what_if` (Prrrdoku 3), the story says "X kan niet op ...: dan ..."
  rather than the document's more insightful case splits. Chains would
  help here too.
- `relations` re-scans every relation from scratch on each pass (it prunes
  a whole relation per firing, so there are few passes). Three-way
  relations (`furthest`) make each scan quadratic in domain size. A
  dirty-variable queue would skip relations whose variables did not change.
