"""Benchmark: grade and time the solver on generated Sudokus.

    uv run python benchmark/run.py [--count 100] [--seed 42]

Each puzzle is a random solved grid (a base grid shuffled by relabelling
digits and permuting rows, columns, bands and stacks), from which givens are
removed in random order as long as the brute force still finds exactly one
solution, so every puzzle is unique and minimal. The solver then runs twice:
with the full rule ladder, and without chains (what_if still there), to show
what chains add. Times include compiling the model.
"""

import argparse
import random
import statistics
import time
from collections import Counter

from csp.bruteforce import sudoku as brute
from csp.core import DEFAULT_RULES, Rule, Solver
from csp.report import grade
from csp.sudoku import compile_puzzle

BASE = [[(3 * (r % 3) + r // 3 + c) % 9 + 1 for c in range(9)] for r in range(9)]


def solved_grid(rng: random.Random) -> list[list[int]]:
    digits = rng.sample(range(1, 10), 9)
    bands = rng.sample(range(3), 3)
    stacks = rng.sample(range(3), 3)
    rows = [3 * b + r for b in bands for r in rng.sample(range(3), 3)]
    cols = [3 * s + c for s in stacks for c in rng.sample(range(3), 3)]
    grid = [[digits[BASE[r][c] - 1] for c in cols] for r in rows]
    return [list(row) for row in zip(*grid, strict=True)] if rng.random() < 0.5 else grid


def text_of(grid: list[list[int]]) -> str:
    return "\n".join(" ".join(str(d) if d else "." for d in row) for row in grid) + "\n"


def minimal_puzzle(rng: random.Random) -> str:
    grid = solved_grid(rng)
    for r, c in rng.sample([(r, c) for r in range(9) for c in range(9)], 81):
        given, grid[r][c] = grid[r][c], 0
        if len(brute.solutions(text_of(grid), limit=2)) != 1:
            grid[r][c] = given
    return text_of(grid)


def run(text: str, rules: tuple[Rule, ...]) -> tuple[str, float]:
    start = time.perf_counter()
    model, _ = compile_puzzle(text)
    fired: list[str] = []
    result = Solver(model, rules).solve(on_step=lambda rule, steps: fired.append(rule))
    elapsed = (time.perf_counter() - start) * 1000
    return (grade(fired, rules) if result.solved else "unsolved"), elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    names = [r.name for r in DEFAULT_RULES]
    without_chains = tuple(r for r in DEFAULT_RULES if r.name != "chains")
    rng = random.Random(args.seed)
    puzzles = [minimal_puzzle(rng) for _ in range(args.count)]

    full = [run(p, DEFAULT_RULES) for p in puzzles]
    short = [run(p, without_chains) for p in puzzles]
    grades = Counter(g for g, _ in full)
    before = Counter(g for g, _ in short)

    print(f"{args.count} minimal Sudokus, seed {args.seed}\n")
    print("| Grade | Puzzles | Median ms | Max ms |")
    print("|---|---:|---:|---:|")
    for name in [*names, "unsolved"]:
        times = [t for g, t in full if g == name]
        if times:
            row = f"| `{name}` | {len(times)} | {statistics.median(times):.1f} | {max(times):.1f} |"
            print(row)
    solved = args.count - grades["unsolved"]
    print(
        f"\nSolved by logic alone: {solved} of {args.count}, "
        f"{grades['what_if']} of them with what_if."
    )
    print(
        f"Without chains: {args.count - before['unsolved']} of {args.count}, "
        f"{before['what_if']} of them with what_if."
    )


if __name__ == "__main__":
    main()
