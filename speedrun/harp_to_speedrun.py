#!/usr/bin/env python3
"""Convert HARP MCQ rows into the Speedrun deck-builder JSON schema.

HARP (https://github.com/aadityasingh/HARP) is a human-annotated research
dataset of problems scraped from the Art of Problem Solving wiki. The source
problems are (c) the Mathematical Association of America and are reproduced here
for educational use with attribution.

Usage::

    python3 speedrun/harp_to_speedrun.py \
        --input speedrun/out/harp/HARP_mcq.jsonl \
        --contest AMC_10A --year 2022 \
        --out speedrun/out/amc_10a_2022.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# HARP subjects -> Speedrun's four canonical interleaving topics.
SUBJECT_MAP = {
    "algebra": "algebra",
    "prealgebra": "algebra",
    "intermediate_algebra": "algebra",
    "precalculus": "algebra",
    "geometry": "geometry",
    "number_theory": "number_theory",
    "counting_and_probability": "combinatorics",
}


def aops_url(row: dict) -> str:
    """Best-effort reconstruction of the AoPS wiki page for AMC contests."""
    contest = str(row.get("contest", ""))
    year = row.get("year", "")
    number = row.get("number", "")
    if contest.startswith("AMC") and year and number:
        return (
            "https://artofproblemsolving.com/wiki/index.php/"
            f"{year}_{contest}_Problems/Problem_{number}"
        )
    return ""


def collect_solutions(row: dict) -> str:
    sols = []
    i = 1
    while True:
        key = f"solution_{i}"
        if key not in row:
            break
        if row[key]:
            sols.append(row[key])
        i += 1
    if len(sols) > 1:
        return "\n\n".join(f"Solution {n}:\n{s}" for n, s in enumerate(sols, 1))
    return sols[0] if sols else ""


def convert_row(row: dict) -> dict:
    subject = str(row.get("subject", ""))
    return {
        "source": "HARP (AoPS / MAA)",
        "contest": str(row.get("contest", "")).replace("_", " "),
        # Year is usually a plain int but can be e.g. "2021_Fall"; keep raw.
        "year": row["year"],
        "number": int(row["number"]),
        "url": aops_url(row),
        "problem": row.get("problem", ""),
        "choices": row.get("choices", {}),
        "answer": row.get("answer_choice", ""),
        "solution": collect_solutions(row),
        # Prefer the dataset's human subject label; None -> builder heuristics.
        "topic": SUBJECT_MAP.get(subject),
        "subject_raw": subject,
        "level": row.get("level"),
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--contest", required=True, help="HARP contest code, e.g. AMC_10A")
    ap.add_argument("--year", required=True, type=int)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)

    rows = [json.loads(line) for line in args.input.read_text().splitlines() if line.strip()]
    matched = [
        r for r in rows
        if str(r.get("year")) == str(args.year) and r.get("contest") == args.contest
    ]
    matched.sort(key=lambda r: int(r.get("number", 0)))
    out = [convert_row(r) for r in matched]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2))

    print(f"Converted {len(out)} problems for {args.year} {args.contest}.")
    nums = [o["number"] for o in out]
    print("Problem numbers present:", nums)
    from collections import Counter
    print("Topic distribution:", dict(Counter(o["topic"] or "(heuristic)" for o in out)))
    print(f"Wrote -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
