# Quick Start

## Setup

```bash
cd /Users/perdo/div/solver
```

No installation needed—just set `PYTHONPATH` or use uv.

## Solve a Puzzle

### Simplest:
```bash
./solve.sh examples/sudoku_easy.txt
```

### Watch reasoning step-by-step:
```bash
./solve.sh examples/sudoku_easy.txt --verbose
```

### Show candidate counts:
```bash
./solve.sh examples/sudoku_easy.txt --show-candidates
```

### Or use PYTHONPATH directly:
```bash
PYTHONPATH=src python3 -m csp.cli examples/sudoku_easy.txt --verbose
```


## Verify It Works

```bash
python3 tests/test_sudoku.py
```

Should see:
```
✓ test_parse_simple_puzzle
✓ test_build_model  
✓ test_solver_propagation

All tests passed!
```

## Puzzle File Format

Create a `.txt` file with a 9×9 grid:
- Digits `1-9` for givens
- `.` or `0` for empty cells
- `|` and `-` are optional visual separators (ignored)

Example:
```
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
```

## Next Steps

1. **Read AGENT.md** for architecture and extension guide
2. **Read README.md** for full feature overview
3. **Explore the code**: `src/csp/core.py` is the engine
4. **Add new rules**: See AGENT.md "Extension Points"
5. **Add new puzzle types**: See AGENT.md "Adding New Puzzle Types"

## Solving Details

The solver uses **human-style reasoning**, not brute force:

1. **Initial propagation**: Given values eliminate candidates from peer cells
2. **Reasoning loop**: Apply rules in order (naked single, hidden single, pairs...)
3. **Constraint cascade**: Each placement triggers elimination sweep
4. **Human explanation**: Every step logged with reasoning

For this example puzzle:
- 30 givens (out of 81 cells)
- ~30 iterations to solve
- All steps explained in plain language
