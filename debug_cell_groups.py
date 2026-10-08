#!/usr/bin/env python3
"""Visualize how a single cell connects to its constraint groups."""

import sys
sys.path.insert(0, 'src')

from csp.sudoku import SudokuCompiler

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

print("=" * 80)
print("HOW A SINGLE CELL RELATES TO CONSTRAINT GROUPS")
print("=" * 80)

# Pick a cell and show all its constraints
cell_id = "r5c5"  # Row 5, Col 5 (middle of puzzle)
r, c = int(cell_id[1]), int(cell_id[3])

print(f"\n📍 Cell: {cell_id} (row {r}, col {c})")
print(f"   Value: {compiler.grid[r-1][c-1] if compiler.grid[r-1][c-1] else 'empty (51 candidates)'}")

# Find all groups this cell belongs to
cell_groups = [g for g in model.groups if cell_id in g.members]

print(f"\n🔗 This cell belongs to {len(cell_groups)} groups:\n")

# Show row group
row_group = next(g for g in cell_groups if g.group_id.startswith("row_"))
print(f"1️⃣  ROW GROUP: {row_group.group_id}")
print(f"   Cells:     {sorted(row_group.members)}")
print(f"   Constraint: Exactly one instance of each digit (1-9)")
print(f"   Effect: If this cell is 5, then 5 is eliminated from")
print(f"           all other cells in the row\n")

# Show column group
col_group = next(g for g in cell_groups if g.group_id.startswith("col_"))
print(f"2️⃣  COLUMN GROUP: {col_group.group_id}")
print(f"   Cells:     {sorted(col_group.members)}")
print(f"   Constraint: Exactly one instance of each digit (1-9)")
print(f"   Effect: If this cell is 5, then 5 is eliminated from")
print(f"           all other cells in the column\n")

# Show box group
box_group = next(g for g in cell_groups if g.group_id.startswith("box_"))
print(f"3️⃣  BOX GROUP: {box_group.group_id} (3×3 region)")
print(f"   Cells:     {sorted(box_group.members)}")
print(f"   Constraint: Exactly one instance of each digit (1-9)")
print(f"   Effect: If this cell is 5, then 5 is eliminated from")
print(f"           all other cells in this 3×3 box\n")

# Show cell group
cell_group = next(g for g in cell_groups if g.group_id.startswith("cell_"))
print(f"4️⃣  CELL GROUP: {cell_group.group_id} (1 cell)")
print(f"   Cells:     {sorted(cell_group.members)}")
print(f"   Constraint: This cell must have exactly one digit")
print(f"   Effect: Ensures cell doesn't end up with multiple values\n")

# Show intersection example
print("\n" + "=" * 80)
print("INTERSECTION RULE EXAMPLE")
print("=" * 80)

print(f"\nIf digit 5 appears only in cells at ROW ∩ BOX intersection:")
print(f"   ROW cells:  {sorted(row_group.members)}")
print(f"   BOX cells:  {sorted(box_group.members)}")
print(f"   Intersection: {sorted(row_group.members & box_group.members)}")

intersection = row_group.members & box_group.members
rest_of_row = row_group.members - intersection
rest_of_box = box_group.members - intersection

print(f"\n   Then eliminate 5 from:")
print(f"     • Rest of row: {sorted(rest_of_row)}")
print(f"     • Rest of box: {sorted(rest_of_box)}")

# Visual representation
print("\n\nVISUAL: Cell r5c5 and its constraints")
print("-" * 80)

print("\nROW 5:")
for c in range(1, 10):
    cell = f"r5c{c}"
    if cell == cell_id:
        print(f"  [{cell}]  ", end="")
    else:
        print(f"   {cell}   ", end="")
print()

print("\nCOLUMN 5:")
for r in range(1, 10):
    cell = f"r{r}c5"
    if cell == cell_id:
        print(f"  [{cell}]  ", end="")
    else:
        print(f"   {cell}   ", end="")
print()

print("\nBOX 5 (3×3, rows 4-6, cols 4-6):")
for r in range(4, 7):
    for c in range(4, 7):
        cell = f"r{r}c{c}"
        if cell == cell_id:
            print(f"[{cell}] ", end="")
        else:
            print(f" {cell}  ", end="")
    print()

print("\n" + "=" * 80)
print("KEY INSIGHT")
print("=" * 80)
print("""
A cell is NOT independent. Every placement cascades:

   1. Assign r5c5 = 5
   2. Constraint: row_4 must have all digits 1-9 (except 5)
      → Eliminate 5 from: r5c1, r5c2, ..., r5c9
   3. Constraint: col_4 must have all digits 1-9 (except 5)
      → Eliminate 5 from: r1c5, r2c5, ..., r9c5
   4. Constraint: box_1_1 must have all digits 1-9 (except 5)
      → Eliminate 5 from: r4c4, r4c5, r4c6, r5c4, r5c6, r6c4, r6c5, r6c6
   5. Propagate: If any cell now has 1 candidate → place it
      (triggers cascade for that cell)

This is why CSP solvers are powerful: constraints naturally
propagate through the group structure.
""")
