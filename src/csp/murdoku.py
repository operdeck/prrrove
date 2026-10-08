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
    """Display Murdoku grid with colored regions and suspects."""

    # ANSI color codes for regions
    REGION_COLORS = {
        0: '\033[41m',  # Red background
        1: '\033[42m',  # Green background
        2: '\033[43m',  # Yellow background
        3: '\033[44m',  # Blue background
        4: '\033[45m',  # Magenta background
        5: '\033[46m',  # Cyan background
        6: '\033[47m',  # White background
    }
    RESET = '\033[0m'
    BOLD = '\033[1m'

    @staticmethod
    def show(model: CSPModel, grid, regions, suspects, title: str = "Murdoku", highlight: set = None):
        """Display current grid state with colored regions.

        Args:
            model: CSP model
            grid: NxN grid of region IDs
            regions: dict of region_id -> region_name
            suspects: list of suspect names
            title: display title
            highlight: set of cell_ids to highlight in blue
        """
        if highlight is None:
            highlight = set()

        n = len(grid)
        print(f"\n{MurdokuDisplay.BOLD}{title} ({n}×{n}){MurdokuDisplay.RESET}")

        # Top border
        print("  ", end="")
        for c in range(n):
            region_id = grid[0][c]
            color = MurdokuDisplay.REGION_COLORS.get(region_id, '')
            print(f"{color}───{MurdokuDisplay.RESET}", end="")
        print()

        # Grid
        for r in range(n):
            # Row number and left border
            print(f"{r+1} ", end="")

            for c in range(n):
                region_id = grid[r][c]
                color = MurdokuDisplay.REGION_COLORS.get(region_id, '')

                cell_id = f"r{r+1}c{c+1}"
                candidates = model.get_candidates(cell_id)

                if len(candidates) == 1:
                    value_idx = list(candidates)[0]
                    suspect = suspects[value_idx - 1]
                    name = suspect[:3]  # First 3 letters

                    if cell_id in highlight:
                        # Highlight in blue
                        print(f"{color}\033[94m{name}{MurdokuDisplay.RESET}", end="")
                    else:
                        print(f"{color}{name}{MurdokuDisplay.RESET}", end="")
                elif len(candidates) == 0:
                    # Object cell
                    print(f"{color} ● {MurdokuDisplay.RESET}", end="")
                else:
                    # Empty cell
                    print(f"{color} · {MurdokuDisplay.RESET}", end="")

            print()  # End of row

            # Bottom border / separator
            if r < n - 1:
                print("  ", end="")
                for c in range(n):
                    print(f"───", end="")
                print()

        # Bottom border
        print("  ", end="")
        for c in range(n):
            print(f"───", end="")
        print()

        # Legend
        print(f"\n{MurdokuDisplay.BOLD}Regions:{MurdokuDisplay.RESET}")
        for rid in sorted(regions.keys()):
            color = MurdokuDisplay.REGION_COLORS.get(rid, '')
            print(f"  {color}   {MurdokuDisplay.RESET} {rid}: {regions[rid]}")

        print(f"\n{MurdokuDisplay.BOLD}Suspects:{MurdokuDisplay.RESET} {', '.join(suspects)}")


class MurdokuConstraints:
    """Apply Murdoku-specific constraints to the CSP model."""

    @staticmethod
    def adjacent(model: CSPModel, grid: list, cell1_id: str, cell2_id: str, value: int) -> bool:
        """Apply constraint: if cell1 has value, cell2 cannot (cells are adjacent).

        Args:
            model: CSP model
            grid: NxN grid for reference
            cell1_id: first cell ID (1-indexed)
            cell2_id: second cell ID (1-indexed)
            value: the value in question

        Returns:
            True if any elimination occurred
        """
        r1, c1 = MurdokuCompiler._from_cell_id(cell1_id)
        r2, c2 = MurdokuCompiler._from_cell_id(cell2_id)

        # Check if cells are orthogonally adjacent
        manhattan = abs(r1 - r2) + abs(c1 - c2)
        if manhattan != 1:
            return False  # Not adjacent

        # If cell1 has value placed, eliminate from cell2
        if cell1_id in model.placements and model.placements[cell1_id] == value:
            bit = 1 << (value - 1)
            if cell2_id not in model.placements and model.candidates[cell2_id] & bit:
                model.eliminate(cell2_id, value, ReasonType.SINGLE, f"Not adjacent to {cell1_id}={value}")
                return True

        # If cell2 has value placed, eliminate from cell1
        if cell2_id in model.placements and model.placements[cell2_id] == value:
            bit = 1 << (value - 1)
            if cell1_id not in model.placements and model.candidates[cell1_id] & bit:
                model.eliminate(cell1_id, value, ReasonType.SINGLE, f"Not adjacent to {cell2_id}={value}")
                return True

        return False

    @staticmethod
    def next_to_object(model: CSPModel, grid: list, suspect_cell_id: str,
                      object_pos: tuple, value: int) -> bool:
        """Apply constraint: suspect with value must be next to object.

        Args:
            model: CSP model
            grid: NxN grid for reference
            suspect_cell_id: where suspect could be (1-indexed)
            object_pos: (row, col) of object (0-indexed)
            value: value (1-indexed) representing the suspect

        Returns:
            True if constraint eliminated candidates
        """
        r, c = MurdokuCompiler._from_cell_id(suspect_cell_id)
        obj_r, obj_c = object_pos

        # Convert object to 1-indexed for comparison
        obj_r += 1
        obj_c += 1

        manhattan = abs(r - obj_r) + abs(c - obj_c)

        bit = 1 << (value - 1)

        # If this cell must have value but is NOT adjacent to object, eliminate it
        if manhattan != 1:
            if suspect_cell_id not in model.placements and model.candidates[suspect_cell_id] & bit:
                model.eliminate(suspect_cell_id, value, ReasonType.SINGLE,
                              f"Must be next to object at ({obj_r},{obj_c})")
                return True

        return False

    @staticmethod
    def left_of(model: CSPModel, grid: list, left_cell_id: str, right_cell_id: str, value: int) -> bool:
        """Apply constraint: if right_cell has value, left_cell cannot (left must be left of right).

        Args:
            model: CSP model
            grid: NxN grid for reference
            left_cell_id: cell that should be left (1-indexed)
            right_cell_id: cell that should be right (1-indexed)
            value: value to check

        Returns:
            True if constraint eliminated candidates
        """
        r_left, c_left = MurdokuCompiler._from_cell_id(left_cell_id)
        r_right, c_right = MurdokuCompiler._from_cell_id(right_cell_id)

        # If right cell has value, left must be to its left
        if right_cell_id in model.placements and model.placements[right_cell_id] == value:
            if c_left >= c_right:  # Not actually to the left
                bit = 1 << (value - 1)
                if left_cell_id not in model.placements and model.candidates[left_cell_id] & bit:
                    model.eliminate(left_cell_id, value, ReasonType.SINGLE,
                                  f"Must be left of {right_cell_id}")
                    return True

        return False

    @staticmethod
    def above(model: CSPModel, grid: list, above_cell_id: str, below_cell_id: str, distance: int = 1) -> bool:
        """Apply constraint: cell must be exactly distance rows above another.

        Args:
            model: CSP model
            grid: NxN grid for reference
            above_cell_id: cell that should be above (1-indexed)
            below_cell_id: cell that should be below (1-indexed)
            distance: row distance (default 1 for exactly one row above)

        Returns:
            True if constraint eliminated candidates
        """
        r_above, c_above = MurdokuCompiler._from_cell_id(above_cell_id)
        r_below, c_below = MurdokuCompiler._from_cell_id(below_cell_id)

        # For each suspect value
        changed = False
        for value in range(1, len(model.candidates[list(model.candidates.keys())[0]].bit_length())):
            bit = 1 << (value - 1)

            # If below_cell has value, above_cell must have correct row
            if below_cell_id in model.placements and model.placements[below_cell_id] == value:
                expected_r = r_below - distance
                if r_above != expected_r:
                    if above_cell_id not in model.placements and model.candidates[above_cell_id] & bit:
                        model.eliminate(above_cell_id, value, ReasonType.SINGLE,
                                      f"Must be {distance} row(s) above {below_cell_id}")
                        changed = True

            # If above_cell has value, below_cell must have correct row
            if above_cell_id in model.placements and model.placements[above_cell_id] == value:
                expected_r = r_above + distance
                if r_below != expected_r:
                    if below_cell_id not in model.placements and model.candidates[below_cell_id] & bit:
                        model.eliminate(below_cell_id, value, ReasonType.SINGLE,
                                      f"Must be {distance} row(s) below {above_cell_id}")
                        changed = True

        return changed
