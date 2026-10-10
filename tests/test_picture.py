"""Tests for the PNG pictures and the icon references. No network needed."""

from pathlib import Path

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402

from csp import bruteforce, icons, picture  # noqa: E402
from csp.murdoku import Board, Square  # noqa: E402
from csp.puzzlefile import load_board  # noqa: E402

EXAMPLES = Path(__file__).parent.parent / "examples"
CELL = 100


@pytest.fixture(autouse=True)
def offline_icons(tmp_path, monkeypatch):
    """An empty icon cache, and no downloads: icons fall back to text labels."""
    monkeypatch.setenv("CSP_ICON_CACHE", str(tmp_path / "icons"))

    def no_network(*args, **kwargs):
        raise OSError("network disabled in tests")

    monkeypatch.setattr(icons.urllib.request, "urlopen", no_network)


def _centre(image, board, r, c, coordinates=True):
    margin = CELL // 2 if coordinates else CELL // 6
    return image.getpixel((margin + c * CELL + CELL // 2, margin + r * CELL + CELL // 4))


def test_icon_names_map_to_code_points():
    assert icons.code_for("koffer") == icons.code_for("Suitcase") == "1f9f3"
    assert icons.code_for("boom2") == icons.code_for("boom") == "1f333"
    assert icons.code_for("kruik") == "1f3fa"
    assert icons.code_for("paard") == "1f40e"
    assert icons.code_for("ton") == icons.code_for("barrel") == "1f6e2"
    assert icons.code_for("zeppelin") is None
    assert icons.NOTO_COMMIT in icons.SOURCE


def test_cached_icon_is_used_without_downloading():
    path = icons.cache_dir() / "1f333.png"
    path.parent.mkdir(parents=True)
    Image.new("RGBA", (8, 8), (0, 128, 0, 255)).save(path)
    assert icons.icon("boom") == path
    assert icons.icon("koffer") is None  # not cached, and the download fails


def _cache_icon(code: str, image: Image.Image) -> None:
    path = icons.cache_dir() / f"{code}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def test_two_square_furniture_is_stretched_across_both_squares():
    _cache_icon("1f6cb", Image.new("RGBA", (40, 40), (0, 0, 255, 255)))  # a blue block
    board = Board(
        2, [["a", "a"], ["a", "a"]], {"a": "here"}, {}, ["A", "B"],
        furniture={"bank": [Square(1, 0), Square(1, 1)]},
    )  # fmt: skip
    image = picture.murdoku_picture(board, cell=CELL, coordinates=False)
    margin = CELL // 6
    row = margin + CELL + CELL // 2
    blue = [x for x in range(image.width) if image.getpixel((x, row)) == (0, 0, 255)]
    assert blue[0] < margin + CELL // 4 and blue[-1] > margin + 2 * CELL - CELL // 4


def test_adjacent_chairs_render_as_separate_single_cell_icons(monkeypatch):
    board = Board(
        2, [["a", "a"], ["a", "a"]], {"a": "here"}, {}, ["A", "B"],
        furniture={"stoel": [Square(0, 0), Square(1, 0)]},
    )  # fmt: skip
    calls = []

    def capture(image, draw, name, area, cell, **kwargs):
        calls.append((name, area, kwargs))

    monkeypatch.setattr(picture, "_icon", capture)
    picture.murdoku_picture(board, cell=CELL, coordinates=False)
    assert len(calls) == 2
    assert all(name == "stoel" and area[2] - area[0] == CELL for name, area, _ in calls)
    assert all(area[3] - area[1] == CELL for _, area, _ in calls)


def test_vertical_bed_icon_is_rotated(monkeypatch):
    board = Board(
        2, [["a", "a"], ["a", "a"]], {"a": "here"}, {}, ["A", "B"],
        furniture={"bed": [Square(0, 0), Square(1, 0)]},
    )  # fmt: skip
    rotations = []

    def capture(image, draw, name, area, cell, **kwargs):
        rotations.append(kwargs.get("rotate", False))

    monkeypatch.setattr(picture, "_icon", capture)
    picture.murdoku_picture(board, cell=CELL, coordinates=False)
    assert rotations == [True]


def test_custom_carpet_and_well_icons_draw_distinct_images():
    carpet = Image.new("RGB", (120, 120), picture.WHITE)
    picture._draw_carpet(ImageDraw.Draw(carpet), (0, 0, 120, 120))
    assert carpet.getpixel((60, 60)) == (156, 58, 45)

    well = Image.new("RGB", (120, 120), picture.WHITE)
    picture._draw_water_well(ImageDraw.Draw(well), (0, 0, 120, 120))
    assert well.getpixel((45, 84)) == (45, 65, 70)


def test_couch_icon_loses_its_floor_lamp():
    couch = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    couch.paste((250, 210, 0, 255), (60, 0, 90, 40))  # yellow lamp, top right
    couch.paste((40, 140, 220, 255), (5, 30, 95, 95))  # blue couch, backrest up to y=30
    cleaned = picture.ICON_FIXES["1f6cb"](couch)
    assert cleaned.getpixel((75, 10))[3] == 0  # lamp gone
    assert cleaned.getpixel((20, 35)) == (40, 140, 220, 255)  # backrest kept
    assert cleaned.getpixel((50, 80)) == (40, 140, 220, 255)  # seat kept


def test_picture_shows_regions_objects_and_borders():
    text = (EXAMPLES / "prrrdoku3.txt").read_text()
    board, _ = load_board(text)
    image = picture.murdoku_picture(board, cell=CELL)
    margin = CELL // 2
    assert image.width == 2 * margin + 9 * CELL

    moestuin = picture._rgb(board.colours["c"])
    assert _centre(image, board, 3, 5)[:3] == moestuin  # r4c6, plain moestuin
    kas = _centre(image, board, 4, 5)  # r5c6 holds the kas: darker shade
    assert sum(kas[:3]) < sum(moestuin)

    def pixel_on_line(x, y):
        return image.getpixel((margin + x, margin + y))

    # r1c4|r1c5 are both Helmholtzstraat now: thin white line. r1c5|r1c6: thick dark.
    assert pixel_on_line(4 * CELL, CELL // 2) == (255, 255, 255)
    assert sum(pixel_on_line(5 * CELL, CELL // 2)) < 100


def test_without_legend_the_picture_is_square():
    board, _ = load_board((EXAMPLES / "prrrdoku3.txt").read_text())
    with_legend = picture.murdoku_picture(board, cell=CELL)
    without = picture.murdoku_picture(board, cell=CELL, legend=False)
    assert without.width == without.height == with_legend.width < with_legend.height


def test_hatching_only_on_hatched_regions():
    board, _ = load_board((EXAMPLES / "prrrdoku3.txt").read_text())
    image = picture.murdoku_picture(board, cell=CELL)
    margin = CELL // 2

    def colours(r, c):
        x0, y0 = margin + c * CELL + 10, margin + r * CELL + 10
        return {image.getpixel((x, y)) for x in range(x0, x0 + 60) for y in range(y0, y0 + 60)}

    assert len(colours(8, 0)) > 1  # water (hatched)
    assert len(colours(5, 7)) == 1  # klimgebied zuid (plain)


def test_solution_picture_puts_name_tags_on_squares():
    text = (EXAMPLES / "prrrdoku3.txt").read_text()
    board, _ = load_board(text)
    (solution,) = bruteforce.solutions(text, "murdoku")
    image = picture.murdoku_picture(board, solution, cell=CELL)
    tim = solution["Tim"]
    margin = CELL // 2
    tag = image.getpixel((margin + tim.col * CELL + 20, margin + tim.row * CELL + CELL // 2))
    assert tag == (255, 255, 255)


def test_default_palette_when_no_colours_given():
    board = Board(2, [["a", "b"], ["a", "b"]], {"a": "here", "b": "there"}, {}, ["A", "B"])
    image = picture.murdoku_picture(board, cell=CELL, coordinates=False)
    assert _centre(image, board, 0, 0, coordinates=False)[:3] == picture._rgb(picture.PALETTE[0])
    assert _centre(image, board, 0, 1, coordinates=False)[:3] == picture._rgb(picture.PALETTE[1])


def test_unknown_object_gets_a_text_label():
    board = Board(
        2, [["a", "a"], ["a", "a"]], {"a": "here"}, {"zeppelin": [Square(0, 0)]}, ["A", "B"]
    )
    image = picture.murdoku_picture(board, cell=CELL, coordinates=False)
    margin = CELL // 6
    square = image.crop((margin, margin, margin + CELL, margin + CELL))
    pixels = square.load()
    dark = sum(1 for x in range(CELL) for y in range(CELL) if sum(pixels[x, y][:3]) < 150)
    assert dark > 20  # the word is drawn


def test_bad_region_colour_is_rejected():
    text = "Size: 2\nRegions:\na: here #12345\nGrid:\na a\na a\nPeople:\nA\nB\n"
    with pytest.raises(ValueError, match="colour"):
        load_board(text)


def test_cli_png_writes_board_and_solution(tmp_path, capsys):
    from csp import cli

    target = tmp_path / "board.png"
    assert cli.main([str(EXAMPLES / "prrrdoku1.txt"), "--png", str(target)]) == 0
    assert target.exists() and (tmp_path / "board-solution.png").exists()
    for name in ("sudoku_4x4.txt", "calcudoku_4x4_easy.txt"):
        target = tmp_path / f"{name}.png"
        assert cli.main([str(EXAMPLES / name), "--png", str(target)]) == 0
        assert target.exists() and target.with_stem(f"{target.stem}-solution").exists()


# --- sudoku and calcudoku -------------------------------------------------


def _middle(r, c):
    margin = CELL // 2
    return margin + c * CELL + CELL // 2, margin + r * CELL + int(CELL * 0.56)


def _has(image, r, c, colour):
    """Whether any pixel near the middle of cell (r, c) is close to `colour`."""
    x, y = _middle(r, c)
    return any(
        sum(abs(a - b) for a, b in zip(image.getpixel((x + dx, y + dy)), colour, strict=True)) < 60
        for dx in range(-15, 16)
        for dy in range(-15, 16)
    )


def test_sudoku_picture_shows_givens_in_ink_and_solved_numbers_in_blue():
    from csp import sudoku

    text = (EXAMPLES / "sudoku_4x4.txt").read_text()
    grid = sudoku.parse(text)
    (solution,) = bruteforce.solutions(text)
    image = picture.sudoku_picture(grid, solution, cell=CELL)
    assert image.size == (5 * CELL, 5 * CELL)
    assert _has(image, 0, 2, picture.INK) and not _has(image, 0, 2, picture.SOLVED)
    assert _has(image, 0, 0, picture.SOLVED) and not _has(image, 0, 0, picture.INK)
    blank = picture.sudoku_picture(grid, cell=CELL)
    assert not _has(blank, 0, 0, picture.SOLVED)


def test_sudoku_picture_shades_alternate_boxes():
    from csp import sudoku

    grid = sudoku.parse((EXAMPLES / "sudoku_4x4.txt").read_text())
    image = picture.sudoku_picture(grid, cell=CELL)
    corner = lambda r, c: image.getpixel((CELL // 2 + c * CELL + 8, CELL // 2 + r * CELL + 8))  # noqa: E731
    assert corner(0, 0) == corner(2, 2) == picture.WHITE
    assert corner(0, 2) == corner(2, 0) != picture.WHITE


def _corner(image, r, c):
    return image.getpixel((CELL // 2 + c * CELL + 8, CELL // 2 + r * CELL + 8))


def test_jigsaw_picture_colours_touching_boxes_apart():
    from csp import sudoku

    puzzle = sudoku.parse((EXAMPLES / "sudoku_jigsaw.txt").read_text())
    image = picture.sudoku_picture(puzzle, cell=CELL)
    boxes = puzzle.boxes
    for r in range(6):
        for c in range(5):
            same = boxes[r][c] == boxes[r][c + 1]
            assert (_corner(image, r, c) == _corner(image, r, c + 1)) == same, (r, c)


def test_x_sudoku_picture_greys_the_diagonals():
    from csp import sudoku

    puzzle = sudoku.parse((EXAMPLES / "sudoku_x.txt").read_text())
    image = picture.sudoku_picture(puzzle, cell=CELL)
    assert _corner(image, 0, 0) == _corner(image, 0, 8) == _corner(image, 4, 4) == picture.EXTRA
    assert _corner(image, 0, 1) != picture.EXTRA


def test_nrc_sudoku_picture_greys_the_extra_boxes():
    from csp import sudoku

    puzzle = sudoku.parse((EXAMPLES / "sudoku_nrc.txt").read_text())
    image = picture.sudoku_picture(puzzle, cell=CELL)
    assert _corner(image, 1, 1) == _corner(image, 7, 7) == picture.EXTRA
    assert _corner(image, 0, 0) == _corner(image, 4, 4) == picture.WHITE


def test_futoshiki_picture_points_each_sign_at_the_smaller_cell():
    from csp import futoshiki

    puzzle = futoshiki.parse("Grid:\n" + ". . . .\n" * 4 + "Signs:\nr1c2 < r1c1\n")
    image = picture.futoshiki_picture(puzzle, cell=CELL)
    edge, middle = CELL // 2 + CELL, CELL // 2 + CELL // 2
    arm = CELL // 9
    assert image.getpixel((edge + arm // 2, middle)) == picture.INK  # the tip, in r1c2
    assert image.getpixel((edge - arm // 2, middle)) == picture.WHITE  # open towards r1c1


def test_touching_calcudoku_cages_never_share_a_colour():
    from csp import calcudoku

    for name in ("calcudoku_4x4_easy.txt", "calcudoku_7x7_hard.txt"):
        puzzle = calcudoku.parse((EXAMPLES / name).read_text())
        fills = picture._cage_fills(puzzle)
        at = puzzle.cage_at
        for (r, c), cage in at.items():
            for nb in ((r, c + 1), (r + 1, c)):
                if nb in at and at[nb] is not cage:
                    assert fills[at[nb]] != fills[cage], (name, (r, c), nb)


def test_calcudoku_picture_writes_each_cage_target_in_its_first_cell():
    from csp import calcudoku

    puzzle = calcudoku.parse((EXAMPLES / "calcudoku_4x4_easy.txt").read_text())
    image = picture.calcudoku_picture(puzzle, cell=CELL)
    for cage in puzzle.cages:
        r, c = min(cage.cells)
        x, y = CELL // 2 + c * CELL, CELL // 2 + r * CELL
        label = image.crop((x + 8, y + 6, x + CELL // 2, y + CELL // 3))
        assert label.convert("L").getextrema()[0] < 60, cage.label


def test_walls_do_not_poke_into_cells():
    """Where a cage wall ends against a thin line, no ink spills past it."""
    from csp import calcudoku

    puzzle = calcudoku.parse((EXAMPLES / "calcudoku_4x4_easy.txt").read_text())
    image = picture.calcudoku_picture(puzzle, cell=CELL)
    x, y = CELL // 2 + 2 * CELL, CELL // 2 + CELL  # top-left corner of r2c3
    corner = image.crop((x - 10, y - 10, x - 3, y - 3))
    assert corner.convert("L").getextrema()[0] > 60
