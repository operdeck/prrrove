# Exact-cover puzzle solver

One constraint engine, several puzzles. Each puzzle family is compiled down to
literals and constraints; the solving rules never learn anything about the
puzzle they are solving.

Currently solved: **Sudoku** (9x9) and **Murdoku/Prrrdoku** (any size).

```bash
./solve.sh examples/sudoku_easy.txt
./solve.sh examples/prrrdoku1.txt --verbose
./solve.sh examples/prrrdoku1.txt --step      # redraw and pause each deduction
```

## The model

Three ingredients, defined in `src/csp/core.py`:

- **Literals** — atomic choices. `r3c4=7` for Sudoku, `Tim=r1c1` for Murdoku.
- **Constraints** — a set of literals tagged `EXACTLY_ONE` or `AT_MOST_ONE`.
- **Relations** — a predicate over two or more variables' choices, for clues
  like "Jos is somewhere left of Otto" or "Luna is furthest from Mauw".

A *variable* is just a constraint flagged as owning a whole domain, so
`model.chosen("Tim")` can report what Tim settled on.

The `EXACTLY_ONE` / `AT_MOST_ONE` split is load-bearing, not decoration.
`AT_MOST_ONE` forbids a second truth but never forces a first. Collapsing the
two is exactly the bug that made an earlier version of this code unsound on
Murdoku: with 7 people over 43 squares, most squares stay empty, so "this
square is only possible for Vladimir" says nothing at all.

## How the two puzzles map

| | Sudoku | Murdoku |
|---|---|---|
| Variable | a cell | a **person** |
| Literal | cell holds digit | person stands on square |
| `EXACTLY_ONE` | cell holds one digit | person stands somewhere |
| | digit once per row / col / box | one person per row; one per column |
| `AT_MOST_ONE` | — | square holds at most one person |
| Relations | — | position, distance and region clues; see [Puzzle files](#puzzle-files) |

Murdoku's variables are people rather than squares because that is the shape
of the rules: "exactly one figure per row" puts seven figures on a 7x7 board,
it does not put all seven in every row. Modelling it the Sudoku way (squares
choosing people) demands all seven people in each row and is unsatisfiable the
moment an object blocks a square.

## The rules

Applied cheapest-first; any success restarts the ladder.

| Rule | What it does |
|---|---|
| `single` | An `EXACTLY_ONE` with one option left forces it. |
| `relations` | Arc consistency: drop a choice no combination of the other variables supports. |
| `subsumption` | If `live(A) ⊆ live(B)` and A is `EXACTLY_ONE`, every B-literal outside A is false. |
| `cover2`, `cover3` | The same over *k* constraints: *k* disjoint `EXACTLY_ONE`s whose live literals fit inside *k* others use those others up. |
| `what_if` | Assume a literal on a copy, run `single`/`relations`/`subsumption`; if that contradicts, the literal is false. |

`single` covers Sudoku's naked single *and* hidden single with no
special-casing — they are the same statement about different constraints
("this cell holds one digit" vs "this digit sits once in this row").
`subsumption` is likewise pointing-pairs and box/line reduction at once.

`cover`*k* is naked subsets (As are cells), hidden subsets (As are
digit-in-house), X-Wing (*k*=2) and Swordfish (*k*=3) (As are digit-in-row,
Bs digit-in-column) — one rule, again with no special-casing.

`what_if` is the case split a person does when stuck ("if Tim were on r2c3,
Jos would have nowhere to go"). It is last on the ladder and bounded: one
assumption, cheap rules only, no nested guessing.

Not implemented: chains. See `AGENT.md`.

## Verification

```bash
uv run --with pytest pytest tests/ -q      # 40 tests
```

Correctness is checked against ground truth, not self-consistency:

- Sudoku's solution is re-validated independently — every row, column and box
  is a permutation of 1-9, and every given survives.
- The graded Sudokus (`sudoku_pointing`, `_naked_pair`, `_hidden_pair`,
  `_xwing`, `_swordfish`, `_what_if`) are compared cell by cell against a
  plain backtracking search that shares no code with the engine. Each must
  also show its named pattern in the log, and must stall when the ladder is
  cut just before its rule, so the example really exercises that rung.
- All three Prrrdokus are checked against the published solutions and the
  puzzle's question (who is in Vladimir's region) in `Prrrdoku.docx`, and the
  post-clue candidate lists are compared against the lists quoted in that
  document's own worked solutions. A mis-transcribed board fails the tests
  rather than quietly solving a different puzzle.

## Puzzle files

Sudoku is a plain grid; `.`/`0` are blanks, and `|`/`-` are ignored.

Murdoku uses named sections — see `examples/prrrdoku*.txt`:

```
Size: 7
Regions:        # id: name (no spaces)
Groups:         # optional; name: region region ...
Grid:           # region id per square
Objects:        # name: square — blocks that square
People:         # one per line, count must equal Size
Clues:
  next_to Tim klimwand
  in_region Jos keukenwinkel         # any number of regions or groups
  outside Pip water                  # none of the given regions or groups
  same_region Anna Jos
  different_region Anna Pip
  apart Luna Mauw               # different regions that do not share a side
  above Otto Tjitske 1          # exactly 1 row above; omit n for anywhere above
  left_of Jos Otto
  within Tjitske Otto 4         # at most 4 orthogonal steps apart
  at_least Tim Pip 6            # at least 6 steps apart
  alone Luna                    # nobody else in Luna's region
  furthest Luna Mauw            # Luna is strictly further from Mauw than anyone
```

`alone` and `furthest` expand to one relation per other person; `furthest`
is a three-way relation (Luna, Mauw, that person).

## Layout

```
src/csp/
  core.py        engine: literals, constraints, relations, rules, solver
  sudoku.py      Sudoku compiler + renderer
  murdoku.py     Murdoku compiler + renderer + clue vocabulary
  puzzlefile.py  reader for the sectioned Murdoku format
  cli.py         command line
examples/        sudoku_*.txt (graded by the rule they need), prrrdoku1-3.txt
tests/           test_solver.py
```
