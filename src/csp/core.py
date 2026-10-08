"""Core constraint satisfaction engine with propagation rules."""

from dataclasses import dataclass, field
from typing import Callable, Optional, Set, Dict, List, Tuple
from enum import Enum


class ReasonType(Enum):
    """Type of reasoning that led to an elimination or placement."""
    INITIAL = "initial"
    SINGLE = "single"  # Only one place left in group
    SUBSET = "subset"  # Subset confined to fewer places (Hall's marriage)
    INTERSECTION = "intersection"  # Confined to overlap of groups
    FISH = "fish"  # Same literal confined across multiple groups (X-Wing)
    CHAIN = "chain"  # Implication path led to contradiction
    GIVEN = "given"  # User-provided clue


@dataclass
class Elimination:
    """Record of a candidate being eliminated."""
    cell_id: str
    value: int
    reason_type: ReasonType
    reason_text: str


@dataclass
class Placement:
    """Record of a value being definitively placed."""
    cell_id: str
    value: int
    reason_type: ReasonType
    reason_text: str


@dataclass
class Group:
    """A constraint group (row, column, box, etc).

    A group enforces that exactly one (or at most one) of its members
    can hold certain values.
    """
    group_id: str
    members: Set[str]  # Set of cell_ids in this group
    cardinality: int = 1  # How many members should be satisfied (typically 1)

    def __hash__(self):
        return hash(self.group_id)


class CSPModel:
    """Constraint Satisfaction Problem model.

    Tracks candidates (possible values per cell) and groups (constraints).
    """

    def __init__(self, num_values: int = 9):
        """Initialize CSP model.

        Args:
            num_values: Maximum value (e.g., 9 for Sudoku = values 1-9)
        """
        self.num_values = num_values
        self.candidates: Dict[str, int] = {}  # cell_id -> bitmask of candidates
        self.groups: List[Group] = []
        self.log: List[Elimination | Placement] = []
        self.placements: Dict[str, int] = {}  # cell_id -> final value (once determined)

    def add_cell(self, cell_id: str, initial_candidates: int = None):
        """Add a cell with initial candidates (as bitmask).

        Args:
            cell_id: Unique cell identifier
            initial_candidates: Bitmask of possible values (default: all values)
        """
        if initial_candidates is None:
            # All values possible: 0b111111111 for 9 values, etc.
            initial_candidates = (1 << self.num_values) - 1
        self.candidates[cell_id] = initial_candidates

    def add_group(self, group: Group):
        """Add a constraint group."""
        self.groups.append(group)

    def eliminate(
        self,
        cell_id: str,
        value: int,
        reason_type: ReasonType,
        reason_text: str,
    ) -> bool:
        """Eliminate a candidate from a cell.

        Args:
            cell_id: Cell to modify
            value: Value to eliminate (1-indexed)
            reason_type: Why we're eliminating
            reason_text: Human-readable explanation

        Returns:
            True if changed, False if already absent
        """
        bit = 1 << (value - 1)
        if self.candidates[cell_id] & bit:
            self.candidates[cell_id] &= ~bit
            self.log.append(Elimination(cell_id, value, reason_type, reason_text))
            return True
        return False

    def place(
        self,
        cell_id: str,
        value: int,
        reason_type: ReasonType,
        reason_text: str,
    ) -> bool:
        """Place a value in a cell (must eliminate all other candidates).

        Args:
            cell_id: Cell to place value in
            value: Value to place (1-indexed)
            reason_type: Why we're placing
            reason_text: Human-readable explanation

        Returns:
            True if changed, False if already placed
        """
        if cell_id in self.placements:
            return False

        bit = 1 << (value - 1)
        self.placements[cell_id] = value
        self.log.append(Placement(cell_id, value, reason_type, reason_text))

        # Eliminate all other values
        changed = False
        for v in range(1, self.num_values + 1):
            if v != value:
                changed |= self.eliminate(
                    cell_id, v,
                    ReasonType.SINGLE,
                    f"only {value} remains"
                )

        return True

    def get_candidates(self, cell_id: str) -> Set[int]:
        """Get set of possible values for a cell.

        Args:
            cell_id: Cell to query

        Returns:
            Set of possible values (1-indexed)
        """
        if cell_id in self.placements:
            return {self.placements[cell_id]}

        candidates = set()
        mask = self.candidates[cell_id]
        for v in range(1, self.num_values + 1):
            if mask & (1 << (v - 1)):
                candidates.add(v)
        return candidates

    def is_valid(self) -> bool:
        """Check if current state is still valid (no contradictions)."""
        for cell_id, mask in self.candidates.items():
            if cell_id in self.placements:
                continue
            if mask == 0:  # No candidates left for this cell
                return False
        return True


class CSPSolver:
    """Solver that applies propagation rules to solve CSP."""

    def __init__(self, model: CSPModel):
        self.model = model
        self.rules: List[Tuple[str, Callable]] = []
        self._setup_default_rules()

    def _setup_default_rules(self):
        """Set up standard propagation rules in order of cost."""
        self.add_rule("naked_single", self._rule_naked_single)
        self.add_rule("hidden_single", self._rule_hidden_single)
        self.add_rule("naked_pairs", self._rule_naked_pairs)
        self.add_rule("intersections", self._rule_intersections)

    def add_rule(self, name: str, rule_func: Callable[[CSPModel], bool]):
        """Add a propagation rule.

        Rule function should return True if it made a change.
        """
        self.rules.append((name, rule_func))

    def _propagate_placements(self, model: CSPModel, verbose: bool = False):
        """Eliminate candidates conflicting with placed values."""
        for cell_id, value in list(model.placements.items()):
            bit = 1 << (value - 1)

            # Find all groups containing this cell
            for group in model.groups:
                if cell_id not in group.members:
                    continue

                # Eliminate this value from all other cells in the group
                for other_cell_id in group.members:
                    if other_cell_id == cell_id:
                        continue
                    if other_cell_id in model.placements:
                        continue

                    if model.candidates[other_cell_id] & bit:
                        model.eliminate(
                            other_cell_id, value,
                            ReasonType.SINGLE,
                            f"{value} already placed in {group.group_id}"
                        )

    def solve(self, verbose: bool = False, step_through: bool = False) -> Optional[Dict]:
        """Solve the puzzle using propagation.

        Args:
            verbose: Print each step
            step_through: Pause after each rule application

        Returns:
            Dictionary of cell_id -> value if solved, None if unsolvable
        """
        # Initial constraint propagation: placed values eliminate from peers
        self._propagate_placements(self.model, verbose)

        iteration = 0
        while True:
            iteration += 1
            if verbose:
                print(f"\n--- Iteration {iteration} ---")

            if not self.model.is_valid():
                if verbose:
                    print("❌ Contradiction found!")
                return None

            # Try each rule in order
            any_changed = False
            for rule_name, rule_func in self.rules:
                placements_before = set(self.model.placements.keys())
                log_before = len(self.model.log)

                if rule_func(self.model):
                    any_changed = True
                    placements_after = set(self.model.placements.keys())
                    new_placement_keys = placements_after - placements_before
                    new_eliminations = len(self.model.log) - log_before - len(new_placement_keys)

                    if verbose:
                        print(f"✓ {rule_name}")
                        for cell_id in sorted(new_placement_keys):
                            value = self.model.placements[cell_id]
                            print(f"  → {cell_id} = {value}")
                        if new_eliminations > 0:
                            print(f"  ✗ Eliminated {new_eliminations} candidate{'s' if new_eliminations > 1 else ''}")

                    # After any placement, propagate constraints
                    self._propagate_placements(self.model, verbose=False)

                    # Display board with highlights if verbose
                    if verbose and step_through:
                        from .sudoku import SudokuDisplay
                        SudokuDisplay.show(self.model, title="Current state", highlight=new_placement_keys)

                    if step_through:
                        input("Press Enter to continue...")
                    break  # Restart from cheapest rule

            if not any_changed:
                # Fixed point reached
                break

        # Check if solved
        if len(self.model.placements) == len(self.model.candidates):
            if verbose:
                print("\n✅ Solved!")
            return self.model.placements
        else:
            unsolved = len(self.model.candidates) - len(self.model.placements)
            if verbose:
                print(f"\n⏸ Propagation complete. {unsolved} cells remain unsolved.")
            return None

    def _rule_naked_single(self, model: CSPModel) -> bool:
        """Level 1: If a cell has only one candidate, place it.

        Naked single: cell has exactly one possible value.
        """
        for cell_id in model.candidates:
            if cell_id in model.placements:
                continue
            candidates = model.get_candidates(cell_id)
            if len(candidates) == 1:
                value = list(candidates)[0]
                model.place(
                    cell_id, value,
                    ReasonType.SINGLE,
                    f"Only {value} possible"
                )
                return True
        return False

    def _rule_hidden_single(self, model: CSPModel) -> bool:
        """Level 1: If a group has only one place for a value, place it there.

        Hidden single: value can only go in one cell within a group.
        """
        for group in model.groups:
            for value in range(1, model.num_values + 1):
                bit = 1 << (value - 1)
                possible_cells = []

                for cell_id in group.members:
                    if cell_id not in model.placements:
                        if model.candidates[cell_id] & bit:
                            possible_cells.append(cell_id)

                if len(possible_cells) == 1:
                    cell_id = possible_cells[0]
                    model.place(
                        cell_id, value,
                        ReasonType.SINGLE,
                        f"Only place for {value} in group {group.group_id}"
                    )
                    return True
                elif len(possible_cells) == 0 and any(
                    model.candidates[c] & bit for c in group.members
                    if c not in model.placements
                ):
                    # Check if any cell USED to have this value
                    # This shouldn't happen - groups should be consistent
                    pass

        return False

    def _rule_naked_pairs(self, model: CSPModel) -> bool:
        """Level 2: If two cells in a group have the same two candidates,
        eliminate those values from other cells in the group.

        Hall's marriage theorem: n values confined to n cells.
        """
        for group in model.groups:
            active_cells = [c for c in group.members if c not in model.placements]

            # Find pairs (cells with exactly 2 candidates)
            pairs = {}
            for cell_id in active_cells:
                candidates_mask = model.candidates[cell_id]
                count = bin(candidates_mask).count('1')
                if count == 2:
                    if candidates_mask not in pairs:
                        pairs[candidates_mask] = []
                    pairs[candidates_mask].append(cell_id)

            # If two cells share same mask, eliminate from others
            for mask, cells in pairs.items():
                if len(cells) >= 2:
                    other_cells = [c for c in active_cells if c not in cells]
                    changed = False
                    for cell_id in other_cells:
                        # Eliminate all candidates that are in the pair mask
                        for value in range(1, model.num_values + 1):
                            bit = 1 << (value - 1)
                            if (mask & bit) and (model.candidates[cell_id] & bit):
                                model.eliminate(
                                    cell_id, value,
                                    ReasonType.SUBSET,
                                    f"Naked pair in {group.group_id}"
                                )
                                changed = True
                    if changed:
                        return True

        return False

    def _rule_intersections(self, model: CSPModel) -> bool:
        """Level 3: Intersection rule (Pointing Pairs).

        If a value is confined to the intersection of two groups,
        eliminate it from the rest of each group.

        COMPLETELY GENERIC — works on any CSP with overlapping groups:

        Sudoku: If 5 appears only at intersection of row 3 & box 5,
                eliminate 5 from rest of row 3 AND rest of box 5
        Murdoku: If Ann appears only at intersection of "kitchen" & "left",
                 eliminate Ann from rest of kitchen AND rest of left

        The algorithm is identical; only group names differ.
        """
        # For each pair of groups
        for i, group1 in enumerate(model.groups):
            for group2 in model.groups[i+1:]:
                # Find intersection of two groups
                intersection = group1.members & group2.members
                if not intersection:
                    continue

                # For each value
                for value in range(1, model.num_values + 1):
                    bit = 1 << (value - 1)

                    # Find where value appears in each group
                    cells_g1 = {c for c in group1.members
                               if c not in model.placements and model.candidates[c] & bit}
                    cells_g2 = {c for c in group2.members
                               if c not in model.placements and model.candidates[c] & bit}

                    # If value confined to intersection in group1,
                    # eliminate from rest of group2
                    if cells_g1 and cells_g1 <= intersection:  # subset of intersection
                        rest_of_g2 = group2.members - intersection
                        changed = False
                        for cell_id in rest_of_g2:
                            if cell_id not in model.placements and model.candidates[cell_id] & bit:
                                model.eliminate(
                                    cell_id, value,
                                    ReasonType.INTERSECTION,
                                    f"{value} confined to {group1.group_id}∩{group2.group_id}"
                                )
                                changed = True
                        if changed:
                            return True

                    # If value confined to intersection in group2,
                    # eliminate from rest of group1
                    if cells_g2 and cells_g2 <= intersection:  # subset of intersection
                        rest_of_g1 = group1.members - intersection
                        changed = False
                        for cell_id in rest_of_g1:
                            if cell_id not in model.placements and model.candidates[cell_id] & bit:
                                model.eliminate(
                                    cell_id, value,
                                    ReasonType.INTERSECTION,
                                    f"{value} confined to {group1.group_id}∩{group2.group_id}"
                                )
                                changed = True
                        if changed:
                            return True

        return False
