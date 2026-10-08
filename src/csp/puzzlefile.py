"""Reader for the sectioned puzzle-file format used by Murdoku boards.

A file is a series of `Section:` headers followed by indented-free lines.
Blank lines and `#` comments are ignored everywhere.
"""

from .murdoku import Board, Square


def _sections(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current = None
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
    body = token.strip().lower()
    if not body.startswith("r") or "c" not in body:
        raise ValueError(f"bad square {token!r}, expected like r2c5")
    row, _, col = body[1:].partition("c")
    return Square(int(row) - 1, int(col) - 1)


def load_board(text: str) -> tuple[Board, list[tuple[str, list[str]]]]:
    section = _sections(text)
    for required in ("Size", "Regions", "Grid", "People"):
        if required not in section:
            raise ValueError(f"puzzle file is missing a {required}: section")

    size = int(section["Size"][0])

    region_names = {}
    for line in section["Regions"]:
        rid, _, name = line.partition(":")
        region_names[int(rid)] = name.strip()

    grid = [[int(x) for x in line.split()] for line in section["Grid"]]
    if len(grid) != size or any(len(row) != size for row in grid):
        raise ValueError(f"Grid is not {size}x{size}")
    unknown = {r for row in grid for r in row} - set(region_names)
    if unknown:
        raise ValueError(f"Grid uses region ids with no name: {sorted(unknown)}")

    objects = {}
    for line in section.get("Objects", []):
        name, _, where = line.partition(":")
        objects[name.strip()] = parse_square(where)

    people = list(section["People"])

    clues = []
    for line in section.get("Clues", []):
        parts = line.split()
        clues.append((parts[0], parts[1:]))

    board = Board(size, grid, region_names, objects, people)

    known = set(people)
    for kind, args in clues:
        who = [a for a in args[:2] if a in known or kind in ("in_region", "next_to")]
        if args[0] not in known:
            raise ValueError(f"clue {line!r} names unknown person {args[0]!r}")
        if kind in ("same_region", "left_of", "above", "within") and args[1] not in known:
            raise ValueError(f"clue mentions unknown person {args[1]!r}")

    return board, clues
