"""PNG pictures of Murdoku boards, drawn from the puzzle itself.

The picture follows the printed Prrrdoku style: region fills (darker where an
object stands), optional diagonal hatching, thick dark lines between regions
and thin white lines inside them, an icon per object or piece of furniture,
name tags for people, and a legend. Icons come from `csp.icons`; an object
without one gets its name written in the square.

Needs Pillow (`uv sync --extra png`).
"""

from collections.abc import Callable, Iterable, Mapping

from PIL import Image, ImageDraw, ImageFont

from . import icons
from .murdoku import Board, Square

INK = (26, 26, 26)
WHITE = (255, 255, 255)
# Used for regions the puzzle file gives no colour.
PALETTE = ["#F3C8C0", "#FADFB5", "#CBE6B9", "#D8D2F0", "#C4DCF2", "#BEE5D6", "#F3EDA2",
           "#DCDCDC", "#E0A79C", "#A9D6F0"]  # fmt: skip

type RGB = tuple[int, int, int]
type Box = tuple[int, int, int, int]


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
    _grid_lines(draw, board, margin, cell)

    for name, squares in board.objects.items():
        for sq in squares:
            _icon(image, draw, name, box(sq), cell)
    occupied = set((placed or {}).values())
    for name, squares in board.furniture.items():
        for piece in _pieces(squares):
            x0, y0, _, _ = box(min(piece))
            _, _, x1, y1 = box(max(piece))
            if occupied & set(piece):
                y1 = y0 + int(cell * 0.62)  # leave room for the name tag below
                _icon(image, draw, name, (x0, y0, x1, y1), cell, scale=0.95)
            else:
                _icon(image, draw, name, (x0, y0, x1, y1), cell)
    furnished = board.squares_of(board.furniture)
    for person, sq in (placed or {}).items():
        _name_tag(draw, person, box(sq), cell, low=sq in furnished)

    if coordinates:
        _coordinates(draw, board.size, margin, cell)
    if key:
        key.draw(image, draw, margin, margin + side + cell // 3)
    return image


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


def _grid_lines(draw: ImageDraw.ImageDraw, board: Board, margin: int, cell: int) -> None:
    thin = max(2, cell // 40)
    thick = max(4, cell // 22)
    n = board.size
    walls: list[tuple[int, int, int, int]] = []
    for r in range(n):
        for c in range(n):
            x, y = margin + c * cell, margin + r * cell
            if c + 1 < n:
                line = (x + cell, y, x + cell, y + cell)
                same = board.regions[r][c] == board.regions[r][c + 1]
                (draw.line(line, fill=WHITE, width=thin) if same else walls.append(line))
            if r + 1 < n:
                line = (x, y + cell, x + cell, y + cell)
                same = board.regions[r][c] == board.regions[r + 1][c]
                (draw.line(line, fill=WHITE, width=thin) if same else walls.append(line))
    side = n * cell
    low, high = margin, margin + side
    for x0, y0, x1, y1 in walls:
        # Extend each wall by half its width so corners meet squarely, but not past the frame.
        dx, dy = (thick // 2, 0) if y0 == y1 else (0, thick // 2)
        x0, x1 = max(low, x0 - dx), min(high, x1 + dx)
        y0, y1 = max(low, y0 - dy), min(high, y1 + dy)
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
) -> None:
    x0, y0, x1, y1 = area
    path = icons.icon(name)
    if path is None:
        _centred_text(draw, name[:6], area, cell // 5, INK)
        return
    size = int(min(x1 - x0, y1 - y0) * scale)
    picture = Image.open(path).convert("RGBA")
    picture.thumbnail((size, size), Image.Resampling.LANCZOS)
    left = x0 + (x1 - x0 - picture.width) // 2
    top = y0 + (y1 - y0 - picture.height) // 2
    image.paste(picture, (left, top), picture)


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
