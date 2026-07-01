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


def spread(minor: list, major: list) -> list:
    """Evenly distribute `minor` through `major` so `minor` appears in any
    prefix of the result. Used to guarantee GRE cards show up in mixed sessions
    regardless of Anki's per-deck new-card gather limit (which is prefix-based)."""
    n, m = len(minor), len(major)
    if n == 0:
        return list(major)
    out: list = []
    mi = 0
    for i, item in enumerate(major):
        out.append(item)
        while mi < n and (mi + 1) * m <= (i + 1) * n:
            out.append(minor[mi])
            mi += 1
    while mi < n:
        out.append(minor[mi])
        mi += 1
    return out


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
    ap.add_argument(
        "--gre",
        type=Path,
        default=Path("speedrun/data/gre_problems.json"),
        help="GRE-topic problems JSON (already in builder schema).",
    )
    args = ap.parse_args(argv)

    rows = [
        json.loads(line) for line in args.harp.read_text().splitlines() if line.strip()
    ]

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
            "label": f"{tier} only",
            "file": f"{TIER_CODE[tier]}.apkg",
            "deck_name": f"Speedrun::{tier}",
            "problem_count": summary["total"],
            "deck_count": len(decks),
            "topics": summary["topics"],
            # Dedicated single-source set: opt-in via the picker. The default
            # practice is the interleaved Mixed sets below.
            "starter": False,
        }
        manifest_decks.append(entry)
        print(
            f"  {tier:7s} {summary['total']:5d} problems in {len(decks):3d} decks  "
            f"topics={summary['topics']}"
        )

    # GRE Math Subject deck, organized by topic (Speedrun::GRE::<Topic>). These
    # are original GRE-style problems covering the topics AMC does not (calculus,
    # analysis, linear/abstract algebra, ...). Same note type -> interleaves with
    # AMC by topic when studying the parent Speedrun deck.
    gre_topic_display = {
        "calculus": "Calculus",
        "multivariable_calculus": "Multivariable Calculus",
        "sequences_series": "Sequences & Series",
        "differential_equations": "Differential Equations",
        "linear_algebra": "Linear Algebra",
        "abstract_algebra": "Abstract Algebra",
        "real_analysis": "Real Analysis",
        "probability": "Probability & Statistics",
        "complex_analysis": "Complex Analysis",
    }
    gre_problems: list = []
    if args.gre.exists():
        gre_problems = json.loads(args.gre.read_text())
        gre_decks: dict[str, list] = defaultdict(list)
        for p in gre_problems:
            topic = p.get("topic", "other")
            disp = gre_topic_display.get(topic, topic.replace("_", " ").title())
            gre_decks[f"Speedrun::GRE::{disp}"].append(p)
        summary = build_decks(gre_decks, args.out_dir / "GRE.apkg", args.scratch)
        manifest_decks.append(
            {
                "code": "GRE",
                "tier": "GRE",
                "label": "GRE only",
                "file": "GRE.apkg",
                "deck_name": "Speedrun::GRE",
                "problem_count": summary["total"],
                "deck_count": len(gre_decks),
                "topics": summary["topics"],
                # Dedicated GRE-only set: opt-in via the picker. Its content also
                # ships inside the (default) Mixed sets below.
                "starter": False,
            }
        )
        print(
            f"  {'GRE':7s} {summary['total']:5d} problems in {len(gre_decks):3d} decks  "
            f"topics={summary['topics']}"
        )

    # Mixed sets (KEY, default practice): one per difficulty tier, each a single
    # flat deck where the GRE problems are spread evenly through that tier's most
    # recent contests. Because Anki gathers new cards by position up to the daily
    # limit, spreading GRE by position guarantees GRE appears in every mixed
    # session; the topic interleaver then spaces AMC/GRE topics apart within the
    # queue. Nesting under `Speedrun::Mixed::` lets a student study one level
    # (e.g. AMC 10 + GRE) or the parent for an all-levels mix.
    if gre_problems:
        for tier in TIERS:
            tier_rows = [
                r for r in rows if CONTEST_TO_TIER.get(r.get("contest")) == tier
            ]
            if not tier_rows:
                continue
            years = {str(r.get("year")) for r in tier_rows}
            latest_year = max(years, key=lambda y: (y.isdigit(), y))
            amc_recent = [
                convert_row(r) for r in tier_rows if str(r.get("year")) == latest_year
            ]
            mixed = spread(gre_problems, amc_recent)  # GRE evenly distributed in AMC
            code = f"MIXED_{TIER_CODE[tier]}"
            fname = f"{code}.apkg"
            deck_name = f"Speedrun::Mixed::{tier} + GRE"
            summary = build_decks(
                {deck_name: mixed}, args.out_dir / fname, args.scratch
            )
            manifest_decks.append(
                {
                    "code": code,
                    "tier": "Mixed",
                    "label": f"Mixed: {tier} + GRE",
                    "file": fname,
                    "deck_name": deck_name,
                    "problem_count": summary["total"],
                    "deck_count": 1,
                    "topics": summary["topics"],
                    "starter": True,
                }
            )
            print(
                f"  {code:12s} {summary['total']:5d} problems  "
                f"(GRE {len(gre_problems)} spread through {tier} {latest_year} "
                f"x{len(amc_recent)})"
            )

    manifest = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "HARP (AoPS / MAA) + original GRE-style problems",
        "decks": manifest_decks,
    }
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2)
    )

    total = sum(d["problem_count"] for d in manifest_decks)
    print(f"\nGenerated {len(manifest_decks)} tier decks ({total} problems).")
    print(f"Manifest -> {args.out_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
