"""PNG pictures of puzzles, drawn from the puzzle itself.

Murdoku follows the style of the printed puzzles: region fills (darker where
an object stands), optional diagonal hatching, thick dark lines between
regions and thin white lines inside them, an icon per object or piece of
furniture, name tags for people, and a legend. Icons come from `csp.icons`;
an object without one gets its name written in the square.

Sudoku and Calcudoku share the look: thick lines around boxes or cages, thin
ones inside, givens in black and solved numbers in blue. Calcudoku cages get
pastel fills, no two touching cages alike, and their target in the corner.

Needs Pillow (`uv sync --extra png`).
"""

from collections.abc import Callable, Hashable, Iterable, Mapping
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont

from . import icons
from .calcudoku import Puzzle as Calcudoku
from .calcudoku import cell_name as calcudoku_cell
from .futoshiki import Puzzle as Futoshiki
from .futoshiki import cell_name as futoshiki_cell
from .murdoku import Board, Square
from .sudoku import Puzzle as Sudoku
from .sudoku import box_size
from .sudoku import cell_name as sudoku_cell

INK = (26, 26, 26)
WHITE = (255, 255, 255)
SOLVED = (33, 90, 200)  # numbers the solver filled in
DIAGONAL = (255, 241, 196)  # X-Sudoku's diagonal houses
THIN = (190, 190, 190)
# Used for regions the puzzle file gives no colour.
PALETTE = ["#F3C8C0", "#FADFB5", "#CBE6B9", "#D8D2F0", "#C4DCF2", "#BEE5D6", "#F3EDA2",
           "#DCDCDC", "#E0A79C", "#A9D6F0"]  # fmt: skip

type RGB = tuple[int, int, int]
type Box = tuple[int, int, int, int]
type Cell = tuple[int, int]


def murdoku_picture(
    board: Board,
    placed: Mapping[str, Square] | None = None,
    *,
    cell: int = 120,
    coordinates: bool = True,
    legend: bool = True,
) -> Image.Image:
    """The board, with `placed` people drawn on their squares if given.

    Without `legend` the picture is square, for documents with their own legend.
    """
    margin = cell // 2 if coordinates else cell // 6
    side = board.size * cell
    key = _Legend(board, cell) if legend else None
    height = side + 2 * margin + (key.height if key else 0)
    image = Image.new("RGB", (side + 2 * margin, height), WHITE)
    draw = ImageDraw.Draw(image)
    fills = _fills(board)

    def box(sq: Square) -> Box:
        x, y = margin + sq.col * cell, margin + sq.row * cell
        return x, y, x + cell, y + cell

    blocked = board.blocked
    for r in range(board.size):
        for c in range(board.size):
            sq = Square(r, c)
            fill = fills[board.region_of(sq)]
            draw.rectangle(box(sq), fill=_darker(fill) if sq in blocked else fill)
    _hatch(image, board, box, cell)
    _walls(
        draw,
        board.size,
        margin,
        cell,
        lambda a, b: board.regions[a[0]][a[1]] == board.regions[b[0]][b[1]],
    )

    for name, squares in board.objects.items():
        for sq in squares:
            _icon(image, draw, name, box(sq), cell)
    occupied = set((placed or {}).values())
    for name, squares in board.furniture.items():
        for piece in _pieces(squares):
            x0, y0, _, _ = box(min(piece))
            _, _, x1, y1 = box(max(piece))
            stretch = len(piece) > 1
            if occupied & set(piece) and not stretch:
                y1 = y0 + int(cell * 0.62)  # leave room for the name tag below
                _icon(image, draw, name, (x0, y0, x1, y1), cell, scale=0.95)
            else:
                _icon(image, draw, name, (x0, y0, x1, y1), cell, stretch=stretch)
    furnished = board.squares_of(board.furniture)
    for person, sq in (placed or {}).items():
        _name_tag(draw, person, box(sq), cell, low=sq in furnished)

    if coordinates:
        _coordinates(draw, board.size, margin, cell)
    if key:
        key.draw(image, draw, margin, margin + side + cell // 3)
    return image


def sudoku_picture(
    puzzle: Sudoku, solution: Mapping[str, int] | None = None, *, cell: int = 100
) -> Image.Image:
    """The grid with its givens, and the solved numbers in blue if given.

    Square boxes are shaded alternately; jigsaw boxes get a pastel each. In
    X-Sudoku the two diagonals are tinted.
    """
    n, grid, boxes = puzzle.size, puzzle.grid, puzzle.boxes
    fills = _group_fills({(r, c): boxes[r][c] for r in range(n) for c in range(n)})
    box = box_size(n)

    def shade(r: int, c: int) -> RGB:
        if puzzle.diagonals and (r == c or r + c == n - 1):
            return DIAGONAL
        if puzzle.jigsaw:
            return fills[boxes[r][c]]
        return (238, 242, 250) if (r // box + c // box) % 2 else WHITE

    def number(r: int, c: int) -> tuple[int | None, RGB]:
        if grid[r][c]:
            return grid[r][c], INK
        return (solution or {}).get(sudoku_cell(r, c)), SOLVED

    return _number_grid(n, cell, shade, number, lambda a, b: boxes[a[0]][a[1]] == boxes[b[0]][b[1]])


def calcudoku_picture(
    puzzle: Calcudoku, solution: Mapping[str, int] | None = None, *, cell: int = 100
) -> Image.Image:
    """The cages with their targets, and the solved numbers if given."""
    fills = _cage_fills(puzzle)
    cage_at = puzzle.cage_at

    def number(r: int, c: int) -> tuple[int | None, RGB]:
        return (solution or {}).get(calcudoku_cell((r, c))), SOLVED

    image = _number_grid(
        puzzle.size,
        cell,
        lambda r, c: fills[cage_at[r, c]],
        number,
        lambda a, b: cage_at[a] is cage_at[b],
    )
    draw = ImageDraw.Draw(image)
    margin = cell // 2
    font = _font(cell // 5)
    for cage in puzzle.cages:
        r, c = min(cage.cells)
        corner = (margin + c * cell + cell // 10, margin + r * cell + cell // 14)
        draw.text(corner, cage.label, fill=INK, font=font, anchor="la")
    return image


def futoshiki_picture(
    puzzle: Futoshiki, solution: Mapping[str, int] | None = None, *, cell: int = 100
) -> Image.Image:
    """The grid with its givens and signs, and the solved numbers in blue if given.

    Each sign is a chevron on the edge between its two cells, its point
    towards the smaller number.
    """
    grid = puzzle.grid

    def number(r: int, c: int) -> tuple[int | None, RGB]:
        if grid[r][c]:
            return grid[r][c], INK
        return (solution or {}).get(futoshiki_cell((r, c))), SOLVED

    image = _number_grid(puzzle.size, cell, lambda r, c: WHITE, number, lambda a, b: True)
    draw = ImageDraw.Draw(image)
    margin, arm = cell // 2, cell // 9
    for sign in puzzle.signs:
        (r0, c0), (r1, c1) = sign.smaller, sign.larger
        dx, dy = c0 - c1, r0 - r1  # one step towards the smaller cell
        mx = margin + (c0 + c1 + 1) * cell / 2
        my = margin + (r0 + r1 + 1) * cell / 2
        tip = (mx + dx * arm / 2, my + dy * arm / 2)
        back = (mx - dx * arm / 2, my - dy * arm / 2)
        ends = [(back[0] + dy * arm, back[1] + dx * arm), (back[0] - dy * arm, back[1] - dx * arm)]
        pad = arm + cell // 25
        draw.rectangle((mx - pad, my - pad, mx + pad, my + pad), fill=WHITE)
        draw.line([ends[0], tip, ends[1]], fill=INK, width=max(3, cell // 25), joint="curve")
    return image


def _number_grid(
    n: int,
    cell: int,
    shade: Callable[[int, int], RGB],
    number: Callable[[int, int], tuple[int | None, RGB]],
    together: Callable[[Cell, Cell], bool],
) -> Image.Image:
    """A square grid of numbers: shaded cells, walls between groups, coordinates."""
    margin = cell // 2
    side = n * cell
    image = Image.new("RGB", (side + 2 * margin, side + 2 * margin), WHITE)
    draw = ImageDraw.Draw(image)
    font = _font(int(cell * 0.5))
    for r in range(n):
        for c in range(n):
            x, y = margin + c * cell, margin + r * cell
            draw.rectangle((x, y, x + cell, y + cell), fill=shade(r, c))
    _walls(draw, n, margin, cell, together, thin_colour=THIN)
    for r in range(n):
        for c in range(n):
            value, colour = number(r, c)
            if value:
                middle = (margin + c * cell + cell / 2, margin + r * cell + cell * 0.56)
                draw.text(middle, str(value), fill=colour, font=font, anchor="mm")
    _coordinates(draw, n, margin, cell)
    return image


def _cage_fills(puzzle: Calcudoku) -> dict[object, RGB]:
    """A pastel per cage, never the same as a cage it touches."""
    return _group_fills(dict(puzzle.cage_at))


def _group_fills(group_at: Mapping[Cell, Hashable]) -> dict[Any, RGB]:
    """A pastel per group of cells, never the same as a group it touches."""
    colours = [_rgb(p) for p in PALETTE]
    fills: dict[Any, RGB] = {}
    for _, group in sorted(group_at.items()):
        if group in fills:
            continue
        touching = {
            fills.get(group_at[nb])
            for (gr, gc), g in group_at.items()
            if g == group
            for nb in ((gr, gc + 1), (gr + 1, gc), (gr, gc - 1), (gr - 1, gc))
            if nb in group_at and group_at[nb] != group
        }
        fills[group] = next((x for x in colours if x not in touching), colours[0])
    return fills


# --- regions --------------------------------------------------------------


def _fills(board: Board) -> dict[str, RGB]:
    out = {}
    for i, rid in enumerate(board.region_names):
        colour = board.colours.get(rid) or PALETTE[i % len(PALETTE)]
        out[rid] = _rgb(colour)
    return out


def _rgb(hex_colour: str) -> RGB:
    value = hex_colour.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _darker(colour: RGB, factor: float = 0.9) -> RGB:
    r, g, b = colour
    return round(r * factor), round(g * factor), round(b * factor)


def _hatch(image: Image.Image, board: Board, box: Callable[[Square], Box], cell: int) -> None:
    """Thin diagonal lines over hatched regions, as on the printed boards.

    Stripes follow one global pattern (constant x + y), so they run on
    unbroken from square to square.
    """
    if not board.hatched:
        return
    step = max(6, cell // 7)
    width = max(2, cell // 30)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    for r in range(board.size):
        for c in range(board.size):
            sq = Square(r, c)
            if board.region_of(sq) not in board.hatched:
                continue
            x0, y0, x1, y1 = box(sq)
            tile = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
            stripes = ImageDraw.Draw(tile)
            first = (x0 + y0) // step * step
            for k in range(first, x1 + y1 + step, step):
                # The line x + y = k, in tile coordinates.
                stripes.line([(k - x0 - y0, 0), (k - x0 - y1, y1 - y0)],
                             fill=(60, 60, 60, 60), width=width)  # fmt: skip
            overlay.paste(tile, (x0, y0))
    image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"))


def _walls(
    draw: ImageDraw.ImageDraw,
    n: int,
    margin: int,
    cell: int,
    together: Callable[[Cell, Cell], bool],
    thin_colour: RGB = WHITE,
) -> None:
    """Thin lines between cells that are `together`, thick walls elsewhere."""
    thin = max(2, cell // 40)
    thick = max(5, cell // 22) | 1  # odd, so Pillow centres both directions alike
    walls: list[tuple[int, int, int, int]] = []
    for r in range(n):
        for c in range(n):
            x, y = margin + c * cell, margin + r * cell
            if c + 1 < n:
                line = (x + cell, y, x + cell, y + cell)
                same = together((r, c), (r, c + 1))
                (draw.line(line, fill=thin_colour, width=thin) if same else walls.append(line))
            if r + 1 < n:
                line = (x, y + cell, x + cell, y + cell)
                same = together((r, c), (r + 1, c))
                (draw.line(line, fill=thin_colour, width=thin) if same else walls.append(line))
    side = n * cell
    low, high = margin, margin + side
    horizontal_ends = {p for x0, y0, x1, y1 in walls if y0 == y1 for p in ((x0, y0), (x1, y1))}
    vertical_ends = {p for x0, y0, x1, y1 in walls if x0 == x1 for p in ((x0, y0), (x1, y1))}
    for x0, y0, x1, y1 in walls:
        # Extend an end by half the width only where a crossing wall meets it, so
        # corners close squarely and no wall pokes into a cell.
        across = vertical_ends if y0 == y1 else horizontal_ends
        grow = [thick // 2 if end in across else 0 for end in ((x0, y0), (x1, y1))]
        if y0 == y1:
            x0, x1 = max(low, x0 - grow[0]), min(high, x1 + grow[1])
        else:
            y0, y1 = max(low, y0 - grow[0]), min(high, y1 + grow[1])
        draw.line((x0, y0, x1, y1), fill=INK, width=thick)
    draw.rectangle((low, low, high, high), outline=INK, width=thick)


def _pieces(squares: Iterable[Square]) -> list[list[Square]]:
    """Group squares of one furniture name into connected pieces."""
    remaining = set(squares)
    pieces = []
    while remaining:
        frontier = [remaining.pop()]
        piece = []
        while frontier:
            sq = frontier.pop()
            piece.append(sq)
            for nb in (Square(sq.row + 1, sq.col), Square(sq.row - 1, sq.col),
                       Square(sq.row, sq.col + 1), Square(sq.row, sq.col - 1)):  # fmt: skip
                if nb in remaining:
                    remaining.remove(nb)
                    frontier.append(nb)
        pieces.append(piece)
    return pieces


# --- things on the board --------------------------------------------------


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _icon(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    name: str,
    area: Box,
    cell: int,
    scale: float = 0.72,
    stretch: bool = False,
) -> None:
    """Draw `name`'s icon centred in `area`; `stretch` fills the area instead."""
    x0, y0, x1, y1 = area
    path = icons.icon(name)
    if path is None:
        _centred_text(draw, name[:6], area, cell // 5, INK)
        return
    picture = Image.open(path).convert("RGBA")
    fix = ICON_FIXES.get(icons.code_for(name) or "")
    if fix:
        picture = fix(picture)
    if stretch:
        picture = picture.crop(picture.getchannel("A").getbbox())
        pad = cell // 10
        size = (x1 - x0 - 2 * pad, y1 - y0 - 2 * pad)
        picture = picture.resize(size, Image.Resampling.LANCZOS)
    else:
        side = int(min(x1 - x0, y1 - y0) * scale)
        picture.thumbnail((side, side), Image.Resampling.LANCZOS)
    left = x0 + (x1 - x0 - picture.width) // 2
    top = y0 + (y1 - y0 - picture.height) // 2
    image.paste(picture, (left, top), picture)


def _drop_floor_lamp(picture: Image.Image) -> Image.Image:
    """Noto's U+1F6CB is 'couch and lamp': keep the blue couch, drop the lamp.

    The lamp and its pole are yellow and brown and stand above the seat, which
    starts at 47.5% of the height; every couch pixel up there is blue.
    """
    picture = picture.copy()
    red, _, blue, alpha = picture.split()
    blueish = ImageChops.subtract(blue, red).point(lambda v: 255 if v > 0 else 0)
    above_seat = (0, 0, picture.width, int(picture.height * 0.475))
    alpha.paste(ImageChops.multiply(alpha.crop(above_seat), blueish.crop(above_seat)), above_seat)
    picture.putalpha(alpha)
    return picture


# Per-icon touch-ups, by code point.
ICON_FIXES = {"1f6cb": _drop_floor_lamp}


def _name_tag(
    draw: ImageDraw.ImageDraw, person: str, area: Box, cell: int, low: bool = False
) -> None:
    x0, y0, x1, _ = area
    pad = cell // 10
    top = y0 + int(cell * 0.6) if low else y0 + cell // 3
    tag = (x0 + pad, top, x1 - pad, top + cell // 3)
    draw.rounded_rectangle(tag, radius=cell // 8, fill=WHITE, outline=INK, width=max(2, cell // 40))
    _centred_text(draw, person, tag, cell // 5, INK, max_width=cell - 3 * pad)


def _centred_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    area: Box,
    size: int,
    colour: RGB,
    max_width: int | None = None,
) -> None:
    x0, y0, x1, y1 = area
    font = _font(size)
    while max_width and size > 8 and draw.textlength(text, font=font) > max_width:
        size -= 1
        font = _font(size)
    draw.text(((x0 + x1) / 2, (y0 + y1) / 2), text, fill=colour, font=font, anchor="mm")


def _coordinates(draw: ImageDraw.ImageDraw, n: int, margin: int, cell: int) -> None:
    font = _font(cell // 5)
    grey = (120, 120, 120)
    for i in range(n):
        middle = margin + i * cell + cell / 2
        draw.text((middle, margin / 2), str(i + 1), fill=grey, font=font, anchor="mm")
        draw.text((margin / 2, middle), str(i + 1), fill=grey, font=font, anchor="mm")


# --- legend ---------------------------------------------------------------


class _Legend:
    """Region swatches with names, in two columns under the board."""

    def __init__(self, board: Board, cell: int) -> None:
        self.board = board
        self.cell = cell
        self.swatch = cell // 3
        self.line = int(self.swatch * 1.6)
        self.rows = (len(board.region_names) + 1) // 2
        self.height = self.rows * self.line + cell // 2

    def draw(self, image: Image.Image, draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
        fills = _fills(self.board)
        font = _font(int(self.swatch * 0.8))
        column = self.board.size * self.cell // 2
        for i, (rid, name) in enumerate(self.board.region_names.items()):
            left = x + (i // self.rows) * column
            top = y + (i % self.rows) * self.line
            square = (left, top, left + self.swatch, top + self.swatch)
            draw.rectangle(square, fill=fills[rid], outline=INK, width=2)
            if rid in self.board.hatched:
                for k in range(0, 2 * self.swatch, max(5, self.swatch // 4)):
                    draw.line(
                        [(left + max(0, k - self.swatch), top + min(k, self.swatch)),
                         (left + min(k, self.swatch), top + max(0, k - self.swatch))],
                        fill=(110, 110, 110), width=1,
                    )  # fmt: skip
            label = name.replace("_", " ").capitalize()
            draw.text((left + self.swatch + self.swatch // 2, top + self.swatch / 2),
                      label, fill=INK, font=font, anchor="lm")  # fmt: skip
