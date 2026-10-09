---
name: murdoku-puzzle-generator
description: "Use when transcribing a user-provided Murdoku photo or scan into solver text, or creating an original Murdoku puzzle from loose clues and constraints. Covers board reconstruction, clue mapping, file validation, uniqueness, and deductive grade."
argument-hint: "Attach a puzzle image or specify a theme, size, clues, constraints, language, target grade, or output path"
---

# Murdoku Puzzle Assistant

Handle either a faithful transcription of a supplied puzzle image or an
original puzzle built from the user's loose clues and constraints. The agent
prepares the file; the solver validates it. Do not call a puzzle verified
based only on reasoning or a plausible-looking solution.

## Choose a Workflow

- If the user supplies a photo or scan of an existing puzzle, use
  [Transcribe an Image](#transcribe-an-image).
- If the user describes a new puzzle, theme, clues, or constraints, use
  [Build from Constraints](#build-from-constraints).
- If both are supplied, transcribe the image first, then treat the user's
  requested changes as explicit constraints on a separate derived puzzle.

Before persistent edits, follow `AGENT.md`, including the branch and
originality requirements. Honor a requested output path, but never overwrite
an existing file.

## Transcribe an Image

1. Inspect the actual user-supplied image. Use visual inspection at full
resolution and zoom or crop when useful; do not rely on OCR alone for grid
lines, region boundaries, colors, or small clue text. Do not search the web
for a source image or substitute another version.
2. Record the board size and coordinates, each region's name and cells, object
and furniture placements, people, board-wide rules, and numbered clues in
their printed order. Distinguish blocking objects from usable furniture.
3. Map each clue to the supported syntax below without changing its meaning.
   If a clue is not expressible by this solver, explain the gap and ask whether
  the user wants a partial transcription or a separate solver enhancement.
  A partial file must be labeled incomplete and must not be presented as a
  faithful, complete conversion. Never silently approximate the clue.
4. Do not guess at unclear cells, names, colors, or clue words. Ask focused
   questions about ambiguities that affect the file. A solver result may help
   identify a possible transcription error, but must not be used to silently
   choose between competing readings.
5. Save the transcription at the requested path, or by default under the
   gitignored `prrrdokus/` directory with a descriptive new filename. Keep
   transcriptions of existing or potentially published puzzles out of tracked
   `examples/`, documentation, and commits. Do not reproduce the source image
   in the repository.
6. Validate parser acceptance with `uv run csp <file.txt> --show-model`.
   Then run the solution-count and grade checks under [Validation](#validation).
   For transcription, report those results faithfully; do not alter the
   transcribed clues just to force uniqueness or a desired grade.

## Build from Constraints

1. Separate the user's requirements into hard constraints and preferences.
   Treat specified people, board facts, clue meanings, size, and required
   features as hard constraints. Treat unspecified theme, wording, and grade
   as choices; make sensible defaults and state them in the result. Ask a
  focused question only when an ambiguity blocks a faithful puzzle. Accept
  clues in ordinary language; do not require the user to know the file format
  or solver syntax.
2. Translate requested clues into the supported syntax below. Preserve their
   meaning. If a requested clue is unsupported or ambiguous, explain that and
   ask before replacing it with a different rule.
3. Design an intended assignment first: each person occupies one free square,
   with exactly one person in every row and column. Build an original board
   and clue set around it. Check each user-specified clue against the
   assignment, then add only the clues needed to meet the requested
   uniqueness and solver-grade goals.
4. Write a new file at the requested path; otherwise use a new descriptive
   filename under `examples/`. Never copy a published puzzle's board, clue
   set, story, or solution. Consult the `Puzzle files` section of `README.md`
   or `src/csp/murdoku.py` if clue semantics are unclear.
5. Run [Validation](#validation). If uniqueness or the requested grade is not
   achieved, revise the board or added clues without weakening hard
   constraints, then rerun the checks. If the requirements cannot be met
  together, explain the conflict instead of quietly dropping one. When adding
  the puzzle under tracked `examples/`, also run `uv run pytest -q` before
  reporting it complete.

## Validation

Run commands from the repository root. The options below are mutually
exclusive, so run each separately:

```bash
uv run csp <file.txt> --show-model
uv run csp <file.txt> --brute-force
uv run csp <file.txt> --grade
```

- `--show-model` must parse and compile the file. This establishes format/model
  acceptance, not that an image was transcribed correctly.
- `--brute-force` reports whether the encoded puzzle has zero, one, or multiple
  solutions. For a newly generated puzzle, require exactly one. For a
  transcription, treat the result as a diagnostic and report it; compare
  unexpected results with the image rather than changing the source puzzle.
- `--grade` reports the hardest rule this solver used, or `unsolved`. For a
  generated puzzle, require a solved grade and compare it with the user's
  target. For a transcription, `unsolved` means this solver's deduction rules
  did not finish it; it does not mean the text file is malformed.
- `--explain` can produce a worked solution when requested. Review it against
  the intended assignment and clue meanings. Use `--png <file.png>` when a
  board picture is requested.

Report the file path, parser result, solution count, actual grade, and any
remaining uncertainties. For generated puzzles, include the intended
solution. Do not claim a requested grade was reached unless `--grade` confirms
it.

## Murdoku Invariants

- For a board of size `N`, provide exactly `N` people, an `N` by `N` region
  grid, and one person per row and column. Squares may remain empty.
- Every region ID in `Grid:` must be declared in `Regions:`. Use single-token
  identifiers for people, regions, groups, objects, and furniture; use
  `Words:` for display wording where needed.
- `Objects:` block their squares. `Furniture:` does not. Do not place an
  object and furniture on the same square. All placements must be within the
  board.
- Put board-wide, unnumbered clues in `Rules:` and numbered puzzle clues in
   `Clues:`. Required sections are `Size:`, `Regions:`, `Grid:`, and `People:`.
   `Clues:`, `Language:`, `Words:`, `Groups:`, `Hatched:`, `Objects:`,
   `Furniture:`, and `Rules:` are optional.
- Keep clues concise and non-duplicative. Avoid clues that directly reveal
  every person's square unless the user requests a very easy puzzle.

## Supported Clues

Use the spellings and argument order below. Names refer to one-token IDs.

| Form | Meaning |
|---|---|
| `in_region <person> <region-or-group>...` | Person is in one of the named regions. |
| `outside <person> <region-or-group>...` | Person is in none of the named regions. |
| `next_to <person> <object-or-furniture>...` | Person is orthogonally beside any named thing, in the same region. |
| `not_next_to <person> <object-or-furniture>...` | Person is not next to any named thing. |
| `knight_from <person> <object-or-furniture>...` | Person is a chess-knight move from any named thing; region boundaries do not matter. |
| `on <person> <furniture>...` | Person occupies one of the named furniture squares. |
| `same_region <person-a> <person-b>` | Both people are in the same region. |
| `different_region <person-a> <person-b>` | People are in different regions. |
| `apart <person-a> <person-b>` | People are in different, non-touching regions. |
| `left_of <person-a> <person-b>` | A is in a column left of B. |
| `above <person-a> <person-b> [n]` | A is above B; with `n`, exactly `n` rows above. |
| `within <person-a> <person-b> <n>` | Manhattan distance is at most `n`. |
| `at_least <person-a> <person-b> <n>` | Manhattan distance is at least `n`. |
| `alone <person>` | Nobody else is in that person's region. |
| `furthest <person-a> <person-b>` | A is strictly farther from B than every other person. |
| `exactly <n> <clue> ; <clue> ...` | Exactly `n` of the listed simple, one- or two-person clues hold. At most three distinct people may be named across them. |

`next_to` stays within a region. Direction, distance, and `knight_from` may
cross region boundaries. There is no person-to-person adjacency clue: one
person per row and column makes it impossible for two people to share a side.

## Verification Notes

`--brute-force` searches independently of the deduction engine, but shares
the puzzle reader and Murdoku clue definitions. Uniqueness means unique under
the implemented clue semantics; it does not prove that an image was read
correctly or that natural-language clue intent was represented faithfully.
Check the source image or user constraints yourself. `--grade` measures the
hardest rule in this solver's deduction ladder, not a universal human
difficulty rating.

If validation fails, inspect the error and correct only what the selected
workflow permits: a transcription must stay faithful to its source, while a
generated puzzle may change as long as all hard constraints remain satisfied.
Do not weaken verification or change solver code unless the user separately
asks for a solver change.