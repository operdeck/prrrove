#!/usr/bin/env python3
"""Debug script: visualize how Sudoku compiles to CSP model."""

import sys
sys.path.insert(0, 'src')

from csp.sudoku import SudokuCompiler
from csp.core import CSPModel

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

print("=" * 70)
print("SUDOKU → CSP COMPILATION WALKTHROUGH")
print("=" * 70)

# Step 1: Parse puzzle
print("\n1️⃣  INPUT: Sudoku puzzle")
print("-" * 70)
compiler = SudokuCompiler(puzzle_str)
print("\nGrid after parsing (0-indexed internally):")
for r in range(9):
    if r % 3 == 0 and r > 0:
        print()
    row = " ".join(str(compiler.grid[r][c]) if compiler.grid[r][c] else "."
                   for c in range(9))
    print(f"Row {r}: {row}")

# Step 2: Build model
print("\n\n2️⃣  CSP MODEL BUILDING")
print("-" * 70)
model = compiler.build()

print(f"\n📊 Model Statistics:")
print(f"   • Total cells: {len(model.candidates)}")
print(f"   • Total groups: {len(model.groups)}")
print(f"   • Num values per cell: {model.num_values}")

# Step 3: Show givens (placed cells)
print(f"\n📌 Given clues (initial placements): {len(model.placements)} cells")
print("   Cell ID    | Value | Group constraining it")
print("   " + "-" * 50)
for cell_id in sorted(model.placements.keys())[:5]:
    value = model.placements[cell_id]
    # Find which groups this cell belongs to
    groups = [g.group_id for g in model.groups if cell_id in g.members and "cell_" not in g.group_id]
    print(f"   {cell_id:10} | {value:5} | {', '.join(groups[:3])}")
print("   ...")

# Step 4: Show groups
print(f"\n👥 Constraint Groups ({len(model.groups)} total):")
print("\n   Row groups (9):")
for g in model.groups[:9]:
    print(f"     {g.group_id:15} | {len(g.members)} cells | members: {sorted(g.members)[:3]}...")

print("\n   Column groups (9):")
for g in model.groups[9:18]:
    print(f"     {g.group_id:15} | {len(g.members)} cells | members: {sorted(g.members)[:3]}...")

print("\n   Box groups (9):")
for g in model.groups[18:27]:
    print(f"     {g.group_id:15} | {len(g.members)} cells | members: {sorted(g.members)[:3]}...")

print("\n   Cell groups (81, showing first 3):")
for g in model.groups[27:30]:
    print(f"     {g.group_id:15} | {len(g.members)} cell  | members: {g.members}")

# Step 5: Show a sample cell's candidates
print(f"\n🎯 Sample Cell Candidates:")
print("\n   BEFORE propagation:")
sample_empty = None
sample_given = None

# Find a given cell
for cell in sorted(model.placements.keys())[:1]:
    sample_given = cell

# Find an empty cell
for r in range(1, 10):
    for c in range(1, 10):
        cell_id = f"r{r}c{c}"
        if cell_id not in model.placements:
            sample_empty = cell_id
            break
    if sample_empty:
        break

if sample_given:
    value = model.placements[sample_given]
    candidates = model.get_candidates(sample_given)
    print(f"\n   Given cell {sample_given}:")
    print(f"     Value: {value}")
    print(f"     Candidates: {candidates}")

if sample_empty:
    candidates = model.get_candidates(sample_empty)
    mask = model.candidates[sample_empty]
    print(f"\n   Empty cell {sample_empty}:")
    print(f"     Candidates (bitmask {bin(mask)}): {candidates}")
    print(f"     Belongs to groups: row_{int(sample_empty[1])}, col_{int(sample_empty[3])}, ...")

# Step 6: Show constraint examples
print(f"\n⚙️  CONSTRAINTS IN ACTION:")
print("\n   Example: r1c1 (given = 5)")
given_cell = "r1c1"
groups_for_cell = [g for g in model.groups if given_cell in g.members and "cell_" not in g.group_id]
print(f"     Belongs to {len(groups_for_cell)} groups:")
for g in groups_for_cell:
    print(f"       • {g.group_id:15} | {len(g.members)} members: {sorted(g.members)}")
    print(f"         Constraint: exactly one cell has each digit 1-9")
    print(f"         Effect: digit 5 eliminated from all other cells in this group")

# Step 7: Summary
print(f"\n\n📋 TRANSLATION SUMMARY:")
print("-" * 70)
print(f"""
Sudoku Puzzle              →  Generic CSP Model
─────────────────────────────────────────────────
81 cells (9×9)             →  81 cell IDs: r1c1, r1c2, ..., r9c9
Digits 1-9 per cell        →  Bitmask per cell: 9 bits (1 per value)
                              Initially: 0b111111111 (all values possible)

Givens (30 cells)          →  Placements: 30 cells with fixed values
Empty cells (51)           →  51 cells with candidate set

Sudoku rules:              →  Constraint groups:
• Row has 1-9              →    9 row groups
• Col has 1-9              →    9 column groups
• Box has 1-9              →    9 box groups (3×3)
• Each cell has 1 digit     →    81 cell groups

Solving = Group constraint propagation + reasoning rules
""")

print("=" * 70)
