"""Pictures for Murdoku objects and furniture, referenced rather than bundled.

Every object name maps to a Unicode emoji code point; the picture for a code
point comes from Google's Noto Emoji (image resources under the Apache License
2.0), pinned to one commit so a name always gives the same picture. Pictures
are downloaded on first use and cached under ~/.cache/csp-solver (or
$CSP_ICON_CACHE). Without network, `icon` returns None and callers fall back to
a text label.
"""

import os
import urllib.request
from pathlib import Path

NOTO_COMMIT = "e20cbc2bbec1926686be9f9bee7d1d2cfa1fea0e"
SOURCE = (
    f"https://raw.githubusercontent.com/googlefonts/noto-emoji/{NOTO_COMMIT}"
    "/2D/png/512/emoji_u{code}.png"
)

# Dutch names as used in the puzzles, plus English synonyms.
CATALOGUE: dict[str, str] = {
    # outdoors
    "boom": "1f333", "tree": "1f333",
    "struik": "1f33f", "bush": "1f33f",
    "bloem": "1f337", "flower": "1f337",
    "paddenstoel": "1f344", "mushroom": "1f344",
    "boulder": "1faa8", "rots": "1faa8", "rock": "1faa8",
    "paard": "1f40e", "horse": "1f40e",
    "vuurtje": "1f525", "kampvuur": "1f525", "campfire": "1f525", "fire": "1f525",
    "tent": "26fa",
    "parasol": "26f1", "umbrella": "26f1",
    "fontein": "26f2", "fountain": "26f2",
    "vijver": "1fab7", "pond": "1fab7",
    "ton": "1f6e2", "barrel": "1f6e2",
    "standbeeld": "1f5ff", "statue": "1f5ff",
    "glijbaan": "1f6dd", "slide": "1f6dd",
    "klimwand": "1f9d7", "climbing_wall": "1f9d7",
    "kas": "1fab4", "plant": "1fab4", "greenhouse": "1fab4",
    "lantaarn": "1f3ee", "lantern": "1f3ee",
    "fiets": "1f6b2", "bicycle": "1f6b2",
    "auto": "1f697", "car": "1f697",
    "boot": "26f5", "boat": "26f5",
    # indoors
    "bank": "1f6cb", "bankje": "1f6cb", "couch": "1f6cb", "sofa": "1f6cb", "bench": "1f6cb",
    "stoel": "1fa91", "chair": "1fa91",
    "bed": "1f6cf",
    "bad": "1f6c1", "bathtub": "1f6c1",
    "douche": "1f6bf", "shower": "1f6bf",
    "toilet": "1f6bd",
    "kast": "1f5c4", "cabinet": "1f5c4",
    "boekenkast": "1f4da", "boeken": "1f4da", "books": "1f4da",
    "tv": "1f4fa", "televisie": "1f4fa",
    "piano": "1f3b9",
    "gitaar": "1f3b8", "guitar": "1f3b8",
    "lamp": "1f4a1",
    "klok": "1f570", "clock": "1f570",
    "schilderij": "1f5bc", "painting": "1f5bc",
    "spiegel": "1fa9e", "mirror": "1fa9e",
    "ladder": "1fa9c",
    "tafel": "1f37d", "table": "1f37d",
    "bureau": "1f5a5", "desk": "1f5a5", "computer": "1f5a5",
    "kookeiland": "1f373", "fornuis": "1f373", "stove": "1f373",
    "kombuis": "1f372", "galley": "1f372",
    "koffer": "1f9f3", "suitcase": "1f9f3",
    "kruik": "1f3fa", "amphora": "1f3fa", "vase": "1f3fa",
}  # fmt: skip


def code_for(name: str) -> str | None:
    """The emoji code point for an object name; 'boom2' finds 'boom'."""
    return CATALOGUE.get(name.lower().rstrip("0123456789").rstrip("_"))


def cache_dir() -> Path:
    root = os.environ.get("CSP_ICON_CACHE") or Path.home() / ".cache" / "csp-solver"
    return Path(root) / f"noto-emoji-{NOTO_COMMIT[:12]}"


def icon(name: str) -> Path | None:
    """A local PNG for object `name`, downloading it once if needed.

    None if the name is not in the catalogue or the picture cannot be fetched.
    """
    code = code_for(name)
    if code is None:
        return None
    path = cache_dir() / f"{code}.png"
    if not path.exists():
        try:
            with urllib.request.urlopen(SOURCE.format(code=code), timeout=15) as response:
                data = response.read()
        except OSError:
            return None
        if not data.startswith(b"\x89PNG"):
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return path
