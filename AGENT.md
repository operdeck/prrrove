# Agent Guide: CSP Puzzle Solver

This document provides guidance for agents (and humans) working on this repository.

## Project Overview

A **generic constraint satisfaction solver** using exact cover with propagation. Solves puzzles by modeling them as:
- **Literals**: candidate assignments (e.g., "cell R3C4 = 7", "Ann is in kitchen")
- **Groups**: constraints that exactly one (or at most one) literal is true

This implementation uses **human-style reasoning rules** instead of brute force, making solutions explainable step-by-step.

## Architecture

### Core Components

```
src/csp/
├── core.py          # CSP engine: model, solver, propagation rules
├── sudoku.py        # Sudoku puzzle compiler and display
└── cli.py           # Command-line interface
```

### Key Classes

- **CSPModel**: Holds candidates (bitmasks) and groups (constraints)
- **CSPSolver**: Applies reasoning rules in order of cost until fixed point
- **SudokuCompiler**: Converts puzzle text to CSP model (Sudoku-specific)
- **SudokuDisplay**: Pretty-printing of grids and diagnostics

## How It Works

### 1. Model Building (Sudoku Example)
- **Literals**: 81 cells × 9 values = 729 candidate pairs
- **Groups**: 
  - 9 row groups (each has digits 1-9)
  - 9 column groups (each has digits 1-9)  
  - 9 box groups (each has digits 1-9)
  - 81 cell groups (each cell has exactly one digit)

### 2. Candidate Tracking
Each cell stores a bitmask: `0b111111111` = all 9 values possible.
- Bit 0 = value 1, Bit 1 = value 2, etc.
- Fast: eliminates a value in one bit operation

### 3. Constraint Propagation
After any placement or elimination:
- `_propagate_placements()` eliminates the value from all peer cells
- This cascades conflicts upstream and reduces candidate sets

### 4. Reasoning Rules (Cheapest First)
Rules fire in order, restart from cheapest on success:

1. **Naked Single** (Level 1): Cell with only one candidate → place it
2. **Hidden Single** (Level 1): Value with only one cell in group → place it
3. **Naked Pairs** (Level 2): Two cells with same candidates (Hall's marriage theorem)
4. **Intersections** (Level 3): Value confined to group overlap → eliminate from rest
5. **[Future]** Fish (X-Wing), Chains, Bounded what-if

Each rule returns `True` if it made progress, triggering restart and re-propagation.

### 5. Reason Logging
Every placement/elimination is logged with human-readable reasoning:
```
→ r0c2=4: Only place for 4 in row_0
✗ r1c3=1: 1 already placed in col_3
```

## Adding New Puzzle Types

### 1. Create a Compiler
```python
class MurdokuCompiler:
    def build(self) -> CSPModel:
        model = CSPModel(num_values=N)
        
        # Add cells
        for suspect_id in suspects:
            model.add_cell(suspect_id)
        
        # Add groups: "each suspect in exactly one cell"
        for suspect_id in suspects:
            members = {cell for cell in cells}
            model.add_group(Group(f"suspect_{suspect_id}", members))
        
        # Add groups: "each cell holds at most one suspect"  
        for cell_id in cells:
            members = {cell_id}
            model.add_group(Group(f"cell_{cell_id}", members, cardinality=1))
        
        return model
```

### 2. Apply Clues
Clues delete literals (set candidates to 0):
```python
# "Ann was in the kitchen"
for cell_id in non_kitchen_cells:
    model.eliminate(ann_cell_id, ..., "given clue")
```

### 3. Test
```bash
python3 -m csp.cli my_puzzle.txt --verbose
```

## Usage Examples

### Command Line
```bash
# Solve with verbose output
python3 -m csp.cli examples/sudoku_easy.txt --verbose

# Show candidate counts
python3 -m csp.cli examples/sudoku_easy.txt --show-candidates

# Interactive step-through
python3 -m csp.cli examples/sudoku_easy.txt --step
```

### Python API
```python
from csp.sudoku import SudokuCompiler
from csp.core import CSPSolver

compiler = SudokuCompiler(puzzle_str)
model = compiler.build()
solver = CSPSolver(model)
solution = solver.solve(verbose=True)

if solution:
    # Display grid
    print(solution)
```

## Testing

```bash
python3 tests/test_sudoku.py
```

Tests verify:
- Parsing
- Model building
- Propagation (no crashes, valid state)

## Common Issues & Fixes

### "Contradiction found"
Model state became invalid (cell has no candidates).
- Check constraint definition (group members list)
- Verify clues don't over-constrain

### "Reached fixed point" (not fully solved)
Propagation finished but puzzle unsolved.
- Need higher-level rules (Level 4+)
- Or bounded what-if search (Level 6)

### All cells placed as value 1
**Root cause**: Missing `_propagate_placements()` after each placement.
- Check that solve() calls propagation after rule fires
- Verify placements eliminate value from peer groups

## Generic Algorithm Design

All reasoning rules are **completely generic**—they work on any CSP, not just Sudoku.

### Level 3: Intersection Rule (Already Implemented)

**How it works:**
- If a value appears only in the intersection of two groups
- Eliminate that value from the rest of each group

**Why it's generic:**
```python
# Sudoku: intersection of row 3 and box 5
# But same logic for:
# - Murdoku: intersection of suspect set and room
# - Kakuro: intersection of row sum and column sum
# - Any CSP with overlapping groups
```

The code in `_rule_intersections()` makes NO assumptions about:
- Cell layout (grid, list, graph)
- Problem domain (Sudoku, puzzles, scheduling, etc.)
- What groups represent

It only uses group membership (`group1.members & group2.members`).

### Future Generic Rules

All can be implemented the same way:

| Level | Rule | Generic Principle |
|-------|------|-------------------|
| 4 | Fish (X-Wing) | Value appears in exactly N cells across M groups (M>N) → eliminate elsewhere |
| 5 | Chains | Build implication graph: "if A=X then B=Y" → find contradictions |
| 6 | What-if | Bounded backtracking: guess + propagate + detect contradiction |

Each operates only on:
- Groups (sets of cells)
- Candidate bitmasks
- Implication logic

## Extension Points

### New Rules
Add in `CSPSolver._setup_default_rules()`:
```python
self.add_rule("my_rule", self._rule_my_technique)
```

Example: Level 4 Fish
```python
def _rule_fish(self, model: CSPModel) -> bool:
    """Generic fish rule (X-Wing, Swordfish, etc.)"""
    # Same pattern: iterate groups, find values, eliminate candidates
    # No Sudoku-specific code needed
```

### New Puzzle Types
Create new compiler + display class following Sudoku pattern.

### Diagnostics
- `model.log`: Full trace of all placements/eliminations
- `model.get_candidates(cell_id)`: Current candidates for a cell
- `model.placements`: Definitive placements

## Performance Notes

- Bitmask operations: O(1) per bit
- Propagation cascade: O(groups × cells)
- Sudoku typical: 50 iterations to solve (easy-medium)
- No backtracking needed for human-solvable puzzles

## Future Work

- [ ] Level 3: Intersection rules
- [ ] Level 4: Fish (X-Wing, Swordfish)
- [ ] Level 5: Chains (implication graphs)
- [ ] Level 6: Bounded what-if search
- [ ] New puzzle types: Murdoku, Kakuro, Futoshiki, Nonograms
- [ ] Performance optimization (group indexing)
- [ ] Explanation export (LaTeX/HTML)
