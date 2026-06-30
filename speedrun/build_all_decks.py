#!/usr/bin/env python3
"""Generate Speedrun .apkg decks for every AMC contest in the HARP dataset.

Produces one `.apkg` per contest (e.g. `AMC_10A.apkg`), with a subdeck per year
(`Speedrun::AMC 10A::2022`), plus a `manifest.json` the in-app deck picker reads.

Run with the build's Python::

    PYTHONPATH="pylib:out/pylib" out/pyenv/bin/python speedrun/build_all_decks.py \
        --harp speedrun/out/harp/HARP_mcq.jsonl --out-dir speedrun/decks
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from build_deck import build_decks
from harp_to_speedrun import convert_row

# AMC-family contests in HARP, in display order. AHSME/AJHSME are the historical
# names for AMC 12 / AMC 8 and are included for completeness.
CONTEST_ORDER = [
    "AMC_8",
    "AMC_10",
    "AMC_10A",
    "AMC_10B",
    "AMC_12",
    "AMC_12A",
    "AMC_12B",
    "AHSME",
    "AJHSME",
]

# Decks offered by the one-click "Add starter set" button.
STARTER = {"AMC_10A", "AMC_12A", "AMC_8"}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--harp", required=True, type=Path)
    ap.add_argument("--out-dir", type=Path, default=Path("speedrun/decks"))
    ap.add_argument(
        "--scratch",
        type=Path,
        default=Path("speedrun/out/_build_all.anki2"),
        help="Scratch collection file reused for each contest build.",
    )
    args = ap.parse_args(argv)

    rows = [json.loads(line) for line in args.harp.read_text().splitlines() if line.strip()]

    # contest -> year -> [converted problems]
    by_contest: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        contest = row.get("contest")
        if contest not in CONTEST_ORDER:
            continue
        by_contest[contest][str(row["year"])].append(convert_row(row))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_decks = []

    for contest in CONTEST_ORDER:
        if contest not in by_contest:
            continue
        display = contest.replace("_", " ")
        years = sorted(by_contest[contest])
        decks = {
            f"Speedrun::{display}::{year}": by_contest[contest][year] for year in years
        }
        out_path = args.out_dir / f"{contest}.apkg"
        summary = build_decks(decks, out_path, args.scratch)

        entry = {
            "code": contest,
            "contest": display,
            "file": f"{contest}.apkg",
            "deck_name": f"Speedrun::{display}",
            "problem_count": summary["total"],
            "years": years,
            "year_count": len(years),
            "topics": summary["topics"],
            "starter": contest in STARTER,
        }
        manifest_decks.append(entry)
        star = " *" if entry["starter"] else "  "
        print(
            f"{star} {display:10s} {summary['total']:5d} problems "
            f"across {len(years):2d} years  topics={summary['topics']}"
        )

    manifest = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "HARP (AoPS / MAA)",
        "decks": manifest_decks,
    }
    manifest_path = args.out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    total = sum(d["problem_count"] for d in manifest_decks)
    print(f"\nGenerated {len(manifest_decks)} contest decks ({total} problems).")
    print(f"Manifest -> {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
