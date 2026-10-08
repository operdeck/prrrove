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

## Adding a rule

Write `fn(model) -> bool` in `core.py`, add it to `DEFAULT_RULES` in
cost order, and add a unit test that exercises it on a hand-built two or
three literal model (see `test_subsumption_prunes_the_wider_constraint`).

Candidates, roughly in order of value:

- ~~Naked / hidden subsets, Fish~~ — done as `rule_cover(k)`, the
  *k*-constraint generalisation of subsumption. One rule covers all four
  Sudoku patterns; only connected groups of anchors are searched. *k*=4
  (quads, Jellyfish) is not in the ladder: no example needs it.
- **Chains.** This is now the gap that most limits the ladder —
  `sudoku_beyond.txt` stalls on it. Build the implication graph over literals (eliminating *x*
  forces *y* when some `EXACTLY_ONE` drops to one option) and look for
  contradictions.
- **Bounded what-if.** Assign a literal, propagate on a copy, keep the
  elimination if it contradicts. Needs model cloning, which does not exist yet.

Keep the ladder honest: if a rule never fires on any example, say so rather
than listing it as working.

## Adding a puzzle family

1. New module with `compile_puzzle(...) -> Model`.
2. Pick the variables carefully — **this is where the real design work is.**
   Ask what the puzzle's constraints quantify over. Murdoku's "one figure per
   row" is about people, so people are the variables; copying Sudoku's
   cell-centric shape produced an unsatisfiable model.
3. Express every rule as `EXACTLY_ONE` / `AT_MOST_ONE` sets, plus relations
   for pairwise clues.
4. A `render(...) -> str` function, and a `touched_*(steps)` helper returning
   the names to highlight.
5. Wire into `cli.detect` and `cli.main`.
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
| `sudoku_beyond.txt` | **stalls**, 13 iterations | `subsumption` 6, `single` 4, `cover2` 2 |
| `prrrdoku1.txt` | solved, 88 iterations | `relations` 79, `single` 7, `subsumption` 1 |

The graded Sudokus were generated (random minimal puzzles, uniqueness checked
by backtracking) and picked because each needs its rule: the tests remove the
rule and assert the puzzle stalls. A single firing can unlock a whole puzzle,
so the counts are small. `cover` never fires on `prrrdoku1.txt`.

## Known gaps

- Only Prrrdoku 1 is transcribed. Puzzles 2 and 3 exist in `Prrrdoku.docx`
  (9x9, more regions, extra clue types). Their boards are **images** in the
  docx — extract from `word/media/*.png` and read them; the tables in that
  file are only colour legends. Always cross-check a transcription against the
  candidate lists in the document's worked solution before trusting it.
- Clue types not yet modelled: "is the only one in their region"
  (a cardinality constraint over a region), "regions do not border each other"
  (needs region adjacency), "X is furthest from Y of anyone" (a global
  optimum, not a pairwise relation). Puzzles 2 and 3 need these.
- No model cloning, so no what-if search.
- `relations` is plain arc consistency and re-scans every relation from
  scratch on each pass; it accounts for most of Prrrdoku 1's iteration count.
  A dirty-variable queue would cut that.
