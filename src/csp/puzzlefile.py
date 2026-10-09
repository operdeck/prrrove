"""Reader for the sectioned puzzle-file format used by Murdoku and Calcudoku.

A file is a series of `Section:` headers, each followed by its lines. A
one-line section can be written inline before the first header, as in
`Size: 7`. Blank lines and `#` comments are ignored everywhere.
"""

import re

from .murdoku import Board, Clue, Square


def read_sections(text: str) -> dict[str, list[str]]:
    """Section name -> its non-blank, non-comment lines."""
    out: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith(":") and " " not in line[:-1]:
            current = line[:-1]
            out[current] = []
        elif current is not None:
            out[current].append(line)
        else:
            head, _, rest = line.partition(":")
            if rest.strip():
                out[head.strip()] = [rest.strip()]
    return out


def parse_square(token: str) -> Square:
    """'r2c5' -> Square(1, 4)."""
    match = re.fullmatch(r"r(\d+)c(\d+)", token.strip().lower())
    if match is None:
        raise ValueError(f"bad square {token!r}, expected like r2c5")
    return Square(int(match[1]) - 1, int(match[2]) - 1)


def load_board(text: str) -> tuple[Board, list[Clue]]:
    """Read a Murdoku puzzle file into its board and its list of clues."""
    section = read_sections(text)
    for required in ("Size", "Regions", "Grid", "People"):
        if required not in section:
            raise ValueError(f"puzzle file is missing a {required}: section")

    size = int(section["Size"][0])

    region_names = {}
    for line in section["Regions"]:
        rid, _, name = line.partition(":")
        region_names[rid.strip()] = name.strip()

    grid = [line.split() for line in section["Grid"]]
    if len(grid) != size or any(len(row) != size for row in grid):
        raise ValueError(f"Grid is not {size}x{size}")
    unknown = {r for row in grid for r in row} - set(region_names)
    if unknown:
        raise ValueError(f"Grid uses region ids with no name: {sorted(unknown)}")

    objects = _placements(section.get("Objects", []))
    furniture = _placements(section.get("Furniture", []))
    if overlap := _overlap(objects, furniture):
        raise ValueError(f"furniture placed on an object at {sorted(overlap)}")

    people = list(section["People"])

    groups = {}
    for line in section.get("Groups", []):
        name, _, members = line.partition(":")
        groups[name.strip()] = members.split()

    clues: list[Clue] = []
    for line in section.get("Clues", []):
        kind, *args = line.split()
        clues.append((kind, args))

    board = Board(size, grid, region_names, objects, people, groups, furniture)
    board.region_ids(groups)  # fails now, not mid-solve, if a group names an unknown region
    return board, clues


def _placements(lines: list[str]) -> dict[str, list[Square]]:
    """'koffer: r1c5 r4c7' lines -> {'koffer': [Square(0, 4), Square(3, 6)]}."""
    placed: dict[str, list[Square]] = {}
    for line in lines:
        name, _, where = line.partition(":")
        placed.setdefault(name.strip(), []).extend(parse_square(t) for t in where.split())
    return placed


def _overlap(*layers: dict[str, list[Square]]) -> set[Square]:
    """Squares claimed by more than one layer."""
    seen: set[Square] = set()
    overlap: set[Square] = set()
    for layer in layers:
        squares = {sq for group in layer.values() for sq in group}
        overlap |= seen & squares
        seen |= squares
    return overlap
