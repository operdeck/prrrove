"""Murdoku puzzle compiler - converts a Murdoku puzzle to a CSP model."""

from .core import CSPModel, Group, ReasonType


class MurdokuCompiler:
    """Compiles a Murdoku puzzle into a CSP model.

    Murdoku is like Sudoku but with arbitrary regions and named entities.

    Murdoku literals: (suspect, cell)
    Murdoku groups:
      - N row groups: each row has all N suspects exactly once
      - N column groups: each column has all N suspects exactly once
      - K region groups: each region has all N suspects exactly once (or a subset)
      - N cell groups: each cell has exactly one suspect (or is empty/occupied by object)
    """

    def __init__(self, grid, regions, suspects, objects_positions):
        """Initialize with puzzle specification.

        Args:
            grid: NxN list of region IDs (0-indexed)
            regions: dict of region_id -> region_name
            suspects: list of suspect names (N elements)
            objects_positions: dict of object_name -> (row, col) - cells blocked by objects
        """
        self.n = len(grid)
        self.grid = grid
        self.regions = regions
        self.suspects = suspects
        self.objects_positions = objects_positions

        if len(suspects) != self.n:
            raise ValueError(f"Number of suspects ({len(suspects)}) must equal grid size ({self.n})")

    def build(self) -> CSPModel:
        """Build CSP model from Murdoku puzzle.

        Returns:
            CSPModel ready for solving
        """
        model = CSPModel(num_values=self.n)

        # Add all cells (identified by suspect)
        for r in range(self.n):
            for c in range(self.n):
                cell_id = self._cell_id(r, c)

                # Check if this cell is occupied by an object
                is_object_cell = (r, c) in self.objects_positions.values()

                if is_object_cell:
                    # Object cells are blocked - no suspect can go there
                    model.add_cell(cell_id, 0)  # No candidates
                else:
                    # All suspects possible
                    model.add_cell(cell_id)

        # Add row groups (each row must have all suspects once)
        for r in range(self.n):
            members = {self._cell_id(r, c) for c in range(self.n)}
            model.add_group(Group(f"row_{r}", members))

        # Add column groups (each column must have all suspects once)
        for c in range(self.n):
            members = {self._cell_id(r, c) for r in range(self.n)}
            model.add_group(Group(f"col_{c}", members))

        # Add region groups (each region must have all suspects once)
        for region_id, region_name in self.regions.items():
            members = set()
            for r in range(self.n):
                for c in range(self.n):
                    if self.grid[r][c] == region_id:
                        members.add(self._cell_id(r, c))
            if members:  # Only add if region has cells
                model.add_group(Group(f"region_{region_id}_{region_name}", members))

        # Add cell groups (each non-object cell has exactly one suspect)
        for r in range(self.n):
            for c in range(self.n):
                cell_id = self._cell_id(r, c)
                model.add_group(Group(f"cell_{r}_{c}", {cell_id}))

        return model

    @staticmethod
    def _cell_id(r: int, c: int) -> str:
        """Generate cell identifier (1-indexed for display)."""
        return f"r{r+1}c{c+1}"

    @staticmethod
    def _from_cell_id(cell_id: str) -> tuple:
        """Parse cell identifier back to (row, col) (0-indexed)."""
        parts = cell_id.split('c')
        return int(parts[0][1:]) - 1, int(parts[1]) - 1


class MurdokuDisplay:
    """Display Murdoku grid with regions and suspects."""

    @staticmethod
    def show(model: CSPModel, grid, regions, suspects, title: str = "Murdoku"):
        """Display current grid state with regions.

        Args:
            model: CSP model
            grid: NxN grid of region IDs
            regions: dict of region_id -> region_name
            suspects: list of suspect names
            title: display title
        """
        n = len(grid)
        print(f"\n{title} ({n}×{n})")

        # Build region names for lookup
        region_names = {rid: rname for rid, rname in regions.items()}

        print("  +" + "+".join("---" for _ in range(n)) + "+")

        for r in range(n):
            row_str = f"{r+1} |"

            for c in range(n):
                cell_id = f"r{r+1}c{c+1}"
                candidates = model.get_candidates(cell_id)

                if len(candidates) == 1:
                    value_idx = list(candidates)[0]
                    suspect = suspects[value_idx - 1]
                    row_str += f"{suspect[0]:2}|"
                elif len(candidates) == 0:
                    # Object cell
                    row_str += " ○|"
                else:
                    row_str += " . |"

            print(row_str)

            # Show region separator if grid changes
            if r < n - 1:
                print("  +" + "+".join("---" for _ in range(n)) + "+")

        print("  +" + "+".join("---" for _ in range(n)) + "+")

        # Show region legend
        print("\nRegions:")
        for rid in sorted(regions.keys()):
            print(f"  {rid}: {regions[rid]}")

        print(f"\nSuspects: {', '.join(suspects)}")
