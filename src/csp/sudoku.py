"""Sudoku puzzle compiler - converts a puzzle to a CSP model."""

from .core import CSPModel, Group, ReasonType, Placement


class SudokuCompiler:
    """Compiles a Sudoku puzzle into a CSP model.

    Sudoku literals: (row, col, digit)
    Sudoku groups:
      - 9 row groups: each row has digits 1-9
      - 9 column groups: each column has digits 1-9
      - 9 box groups: each 3x3 box has digits 1-9
      - 81 cell groups: each cell has exactly one digit
    """

    def __init__(self, puzzle_str: str):
        """Initialize with puzzle string.

        Format: grid with dots for empty cells, | and - for visual separation.
        Example:
            5 3 . | . 7 . | . . .
            6 . . | 1 9 5 | . . .
            ...
        """
        self.puzzle_str = puzzle_str
        self.grid = self._parse_puzzle()

    def _parse_puzzle(self) -> list[list[int]]:
        """Parse puzzle string into 9x9 grid.

        Returns:
            9x9 list with 0 for empty cells, 1-9 for givens
        """
        grid = []
        for line in self.puzzle_str.strip().split('\n'):
            # Skip separator lines
            if '-' in line or line.strip() == '':
                continue

            # Parse row
            row = []
            for char in line:
                if char in '.0':
                    row.append(0)
                elif char.isdigit():
                    row.append(int(char))
                # Skip pipes and spaces

            if row:
                if len(row) != 9:
                    raise ValueError(f"Row has {len(row)} cells, expected 9")
                grid.append(row)

        if len(grid) != 9:
            raise ValueError(f"Grid has {len(grid)} rows, expected 9")

        return grid

    def build(self) -> CSPModel:
        """Build CSP model from puzzle.

        Returns:
            CSPModel ready for solving
        """
        model = CSPModel(num_values=9)

        # Add all cells
        for r in range(9):
            for c in range(9):
                cell_id = self._cell_id(r, c)

                if self.grid[r][c] != 0:
                    # Given clue
                    model.add_cell(cell_id, 1 << (self.grid[r][c] - 1))
                    model.place(
                        cell_id, self.grid[r][c],
                        ReasonType.GIVEN,
                        f"Given clue"
                    )
                else:
                    # Empty cell - all digits possible
                    model.add_cell(cell_id)

        # Add row groups
        for r in range(9):
            members = {self._cell_id(r, c) for c in range(9)}
            model.add_group(Group(f"row_{r}", members))

        # Add column groups
        for c in range(9):
            members = {self._cell_id(r, c) for r in range(9)}
            model.add_group(Group(f"col_{c}", members))

        # Add 3x3 box groups
        for box_r in range(3):
            for box_c in range(3):
                members = set()
                for r in range(3):
                    for c in range(3):
                        members.add(self._cell_id(box_r * 3 + r, box_c * 3 + c))
                model.add_group(Group(f"box_{box_r}_{box_c}", members))

        # Add cell groups (each cell has exactly one digit)
        for r in range(9):
            for c in range(9):
                cell_id = self._cell_id(r, c)
                model.add_group(Group(f"cell_{r}_{c}", {cell_id}))

        return model

    @staticmethod
    def _cell_id(r: int, c: int) -> str:
        """Generate cell identifier (1-indexed)."""
        return f"r{r+1}c{c+1}"

    @staticmethod
    def _from_cell_id(cell_id: str) -> tuple[int, int]:
        """Parse cell identifier back to (row, col) (0-indexed)."""
        parts = cell_id.split('c')
        return int(parts[0][1:]) - 1, int(parts[1]) - 1


class SudokuDisplay:
    """Display Sudoku grid nicely."""

    @staticmethod
    def show(model: CSPModel, title: str = "Sudoku", highlight: set = None):
        """Display current grid state with clean ASCII formatting.

        Args:
            model: CSP model to display
            title: Title to print
            highlight: Set of cell_ids to highlight in green
        """
        if highlight is None:
            highlight = set()

        print(f"\n{title}")
        print("  +------+------+------+")

        for r in range(9):
            if r % 3 == 0 and r != 0:
                print("  +------+------+------+")

            row_str = f"{r+1} |"
            for c in range(9):
                if c % 3 == 0 and c != 0:
                    row_str += "|"

                cell_id = f"r{r+1}c{c+1}"
                candidates = model.get_candidates(cell_id)

                if len(candidates) == 1:
                    value = list(candidates)[0]
                    if cell_id in highlight:
                        # Highlight newly placed cells in blue
                        row_str += f"\033[94m{value}\033[0m "
                    else:
                        row_str += f"{value} "
                else:
                    row_str += ". "

            row_str += "|"
            print(row_str)

        print("  +------+------+------+")
        print("  |1 2 3 |4 5 6 |7 8 9 |")

    @staticmethod
    def show_candidates(model: CSPModel, title: str = "Candidates"):
        """Display candidate counts."""
        print(f"\n{title}")
        for r in range(9):
            if r % 3 == 0 and r != 0:
                print()

            row_str = ""
            for c in range(9):
                if c % 3 == 0 and c != 0:
                    row_str += "  "

                cell_id = f"r{r}c{c}"
                candidates = model.get_candidates(cell_id)
                row_str += f"{len(candidates):2d} "

            print(row_str)

    @staticmethod
    def show_log(model: CSPModel, limit: int = 20):
        """Display recent log entries."""
        print(f"\nRecent steps (last {limit}):")
        for entry in model.log[-limit:]:
            symbol = "→" if isinstance(entry, Placement) else "✗"
            print(f"  {symbol} {entry.cell_id}={entry.value}: {entry.reason_text}")
