# Constraint Satisfaction Puzzle Solver

A clean, human-readable Python implementation of a generic constraint satisfaction solver using **exact cover with propagation**.

This solver works on puzzles that can be modeled as:
- **Literals**: candidate assignments (e.g., "cell r3c4 = 7", "Ann is in the kitchen")
- **Groups**: constraints saying "exactly one" or "at most one" of these literals is true

## Supported Puzzles

- **Sudoku** ✓ (starting point)
- Murdoku, Kakuro, Killer Sudoku, Futoshiki, Nonograms (planned)

## Architecture

```
┌─────────────────────────────────────────┐
│ Puzzle (e.g., Sudoku grid)              │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│ Compiler: Build literals & groups       │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│ CSP Model:                              │
│  - Candidates (bitmasks per cell)       │
│  - Groups (constraints)                 │
│  - Reason log                           │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│ Rule Engine:                            │
│  1. Singles        (Level 1)            │
│  2. Subsets        (Level 2)            │
│  3. Intersections  (Level 3)            │
│  4. Fish           (Level 4)            │
│  5. Chains         (Level 5)            │
│  6. What-if        (Level 6)            │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│ Solution (with explanation)             │
└─────────────────────────────────────────┘
```

## Usage

### Command Line

```bash
python -m csp.cli examples/sudoku_simple.txt --verbose
```

Options:
- `--verbose`: Show each elimination step
- `--step`: Interactive step-through mode
- `--no-rules`: Disable a specific rule (e.g., `--no-rules 3`)

### Python API

```python
from csp.sudoku import SudokuCompiler
from csp.core import CSPSolver

puzzle_str = """
5 3 . | . 7 . | . . .
6 . . | 1 9 5 | . . .
. 9 8 | . . . | . 6 .
------+-------+------
8 . . | . 6 . | . . 3
4 . . | 8 . 3 | . . 1
7 . . | . 2 . | . . 6
------+-------+------
. 6 . | . . . | 2 8 .
. . . | 4 1 9 | . . 5
. . . | . 8 . | . 7 9
"""

compiler = SudokuCompiler(puzzle_str)
model = compiler.build()

solver = CSPSolver(model)
solution = solver.solve(verbose=True)

if solution:
    print(solution.grid())
```

## Key Design Principles

1. **Bitmask candidates**: Each cell tracks possible values as bits (e.g., `0b111111111` = digits 1-9 possible)
2. **Fast propagation**: Rules eliminate candidates and restart cheapest-first
3. **Human reasoning**: Rules mirror human techniques (singles, subsets, intersections, etc.)
4. **Complete logging**: Every elimination has a reason for explainability
5. **Extensible**: New puzzle types need only a compiler; rules are generic

## File Structure

```
src/csp/
├── core.py       # CSPModel, CSPSolver, Rules engine
├── sudoku.py     # Sudoku-specific compiler
└── cli.py        # Command-line interface

examples/
└── sudoku_simple.txt  # Example puzzles

tests/
└── test_sudoku.py
```
