"""Tests for the PNG pictures and the icon references. No network needed."""

from pathlib import Path

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

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
    assert icons.code_for("zeppelin") is None
    assert icons.NOTO_COMMIT in icons.SOURCE


def test_cached_icon_is_used_without_downloading():
    path = icons.cache_dir() / "1f333.png"
    path.parent.mkdir(parents=True)
    Image.new("RGBA", (8, 8), (0, 128, 0, 255)).save(path)
    assert icons.icon("boom") == path
    assert icons.icon("koffer") is None  # not cached, and the download fails


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
    assert cli.main([str(EXAMPLES / "sudoku_easy.txt"), "--png", str(target)]) == 2
    assert "only draws Murdoku" in capsys.readouterr().err
