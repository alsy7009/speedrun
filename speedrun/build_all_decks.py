#!/usr/bin/env python3
"""Generate Speedrun .apkg decks grouped by difficulty tier.

The top-level folders are the three difficulty tiers **AMC 8 / AMC 10 / AMC 12**.
Under each tier, every individual contest+year is its own deck, named in full,
e.g. `Speedrun::AMC 10::AMC 10A 2023`. The A/B variants and the historical
predecessors are folded into the matching tier (AHSME -> AMC 12, AJHSME -> AMC 8).

Produces `AMC_8.apkg`, `AMC_10.apkg`, `AMC_12.apkg` plus `manifest.json` (read by
the in-app deck pickers). Run with the build's Python::

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

# HARP contest -> difficulty tier (our top-level folder).
CONTEST_TO_TIER = {
    "AMC_8": "AMC 8",
    "AJHSME": "AMC 8",  # historical AMC 8
    "AMC_10": "AMC 10",
    "AMC_10A": "AMC 10",
    "AMC_10B": "AMC 10",
    "AMC_12": "AMC 12",
    "AMC_12A": "AMC 12",
    "AMC_12B": "AMC 12",
    "AHSME": "AMC 12",  # historical AMC 12
}

TIERS = ["AMC 8", "AMC 10", "AMC 12"]
TIER_CODE = {"AMC 8": "AMC_8", "AMC 10": "AMC_10", "AMC 12": "AMC_12"}


def full_deck_name(contest: str, year) -> str:
    """Human-readable per-deck name, e.g. 'AMC 10A 2023'."""
    contest_disp = contest.replace("_", " ")
    year_disp = str(year).replace("_", " ")
    return f"{contest_disp} {year_disp}"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--harp", required=True, type=Path)
    ap.add_argument("--out-dir", type=Path, default=Path("speedrun/decks"))
    ap.add_argument(
        "--scratch",
        type=Path,
        default=Path("speedrun/out/_build_all.anki2"),
        help="Scratch collection file reused for each tier build.",
    )
    args = ap.parse_args(argv)

    rows = [json.loads(line) for line in args.harp.read_text().splitlines() if line.strip()]

    # tier -> { "Speedrun::<tier>::<full name>": [problems] }
    by_tier: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        tier = CONTEST_TO_TIER.get(row.get("contest"))
        if tier is None:
            continue
        deck_name = f"Speedrun::{tier}::{full_deck_name(row['contest'], row['year'])}"
        by_tier[tier][deck_name].append(convert_row(row))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_decks = []

    for tier in TIERS:
        if tier not in by_tier:
            continue
        decks = by_tier[tier]
        out_path = args.out_dir / f"{TIER_CODE[tier]}.apkg"
        summary = build_decks(decks, out_path, args.scratch)

        entry = {
            "code": TIER_CODE[tier],
            "tier": tier,
            "file": f"{TIER_CODE[tier]}.apkg",
            "deck_name": f"Speedrun::{tier}",
            "problem_count": summary["total"],
            "deck_count": len(decks),
            "topics": summary["topics"],
            "starter": True,  # all three tiers are default decks
        }
        manifest_decks.append(entry)
        print(
            f"  {tier:7s} {summary['total']:5d} problems in {len(decks):3d} decks  "
            f"topics={summary['topics']}"
        )

    manifest = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "HARP (AoPS / MAA)",
        "decks": manifest_decks,
    }
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    total = sum(d["problem_count"] for d in manifest_decks)
    print(f"\nGenerated {len(manifest_decks)} tier decks ({total} problems).")
    print(f"Manifest -> {args.out_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
