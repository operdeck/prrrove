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
- **Relations** — a predicate over two variables' choices, for clues like
  "Jos is somewhere left of Otto".

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
| Relations | — | `same_region`, `left_of`, `above`, `within` |

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
| `relations` | Arc consistency: drop a choice with no surviving partner. |
| `subsumption` | If `live(A) ⊆ live(B)` and A is `EXACTLY_ONE`, every B-literal outside A is false. |
| `cover2`, `cover3` | The same over *k* constraints: *k* disjoint `EXACTLY_ONE`s whose live literals fit inside *k* others use those others up. |

`single` covers Sudoku's naked single *and* hidden single with no
special-casing — they are the same statement about different constraints
("this cell holds one digit" vs "this digit sits once in this row").
`subsumption` is likewise pointing-pairs and box/line reduction at once.

`cover`*k* is naked subsets (As are cells), hidden subsets (As are
digit-in-house), X-Wing (*k*=2) and Swordfish (*k*=3) (As are digit-in-row,
Bs digit-in-column) — one rule, again with no special-casing.

Not implemented: chains, bounded what-if. See `AGENT.md`.

## Verification

```bash
uv run --with pytest pytest tests/ -q      # 29 tests
```

Correctness is checked against ground truth, not self-consistency:

- Sudoku's solution is re-validated independently — every row, column and box
  is a permutation of 1-9, and every given survives.
- The graded Sudokus (`sudoku_pointing`, `_naked_pair`, `_hidden_pair`,
  `_xwing`, `_swordfish`) are compared cell by cell against a plain
  backtracking search that shares no code with the engine. Each must also
  show its named pattern in the log, and must stall when its rule is removed,
  so the example really exercises that rung of the ladder.
- `sudoku_beyond.txt` needs more than the ladder has; the test checks the
  engine stops without a contradiction and every cell it did fill is right.
- Prrrdoku 1 is checked against the published solution in `Prrrdoku.docx`, and
  the post-clue candidate lists are compared against the four lists quoted in
  that document's own worked solution. A mis-transcribed board fails the tests
  rather than quietly solving a different puzzle.

## Puzzle files

Sudoku is a plain grid; `.`/`0` are blanks, and `|`/`-` are ignored.

Murdoku uses named sections — see `examples/prrrdoku1.txt`:

```
Size: 7
Regions:        # id: name
Grid:           # region id per square
Objects:        # name: square — blocks that square
People:         # one per line, count must equal Size
Clues:
  next_to Tim klimwand
  in_region Jos keukenwinkel
  same_region Anna Jos
  above Otto Tjitske 1          # Otto exactly 1 row above Tjitske
  within Tjitske Otto 4         # at most 4 orthogonal steps apart
  left_of Jos Otto
```

## Layout

```
src/csp/
  core.py        engine: literals, constraints, relations, rules, solver
  sudoku.py      Sudoku compiler + renderer
  murdoku.py     Murdoku compiler + renderer + clue vocabulary
  puzzlefile.py  reader for the sectioned Murdoku format
  cli.py         command line
examples/        sudoku_*.txt (graded by the rule they need), prrrdoku1.txt
tests/           test_solver.py
```
