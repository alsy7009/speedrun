#!/usr/bin/env python3
"""Speedrun deck generator.

Builds an Anki ``.apkg`` of interleaved AMC-style multiple-choice problems from a
source-agnostic JSON file. The note type stores each answer choice, the correct
letter, and the worked solution in separate fields so we can later add full
click-to-answer interactivity and right/wrong tracking. Notes are tagged by
topic (algebra / geometry / number theory / combinatorics) so the Speedrun Rust
interleaving queue can guarantee consecutive problems differ in type.

Run with the build's Python (the one that ships the ``anki`` package)::

    out/pyenv/bin/python speedrun/build_deck.py \
        --input speedrun/data/sample_problems.json \
        --deck "Speedrun::AMC" \
        --out speedrun/out/amc_sample.apkg

JSON schema (a list of objects)::

    {
      "source":  "aops" | "synthetic" | ...,
      "contest": "AMC 10A",
      "year":    2022,
      "number":  2,
      "url":     "https://artofproblemsolving.com/...",
      "problem": "stem text, math in \\( ... \\) or \\[ ... \\]",
      "choices": {"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."},
      "answer":  "B",
      "solution":"worked solution text",
      "topic":   "geometry"        # optional; auto-classified when omitted
    }
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from anki.collection import Collection, ExportAnkiPackageOptions

NOTETYPE_NAME = "Speedrun MC"

FIELDS = [
    "Source",
    "Contest",
    "Year",
    "Number",
    "URL",
    "Problem",
    "ChoiceA",
    "ChoiceB",
    "ChoiceC",
    "ChoiceD",
    "ChoiceE",
    "Answer",
    "Solution",
    "Topic",
]

# Canonical topics we interleave across. Keep these stable: the Rust queue and
# the coverage map key off them.
TOPICS = ("algebra", "geometry", "number_theory", "combinatorics")

# Ordered so earlier, more-specific categories win ties over the algebra catch-all.
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "geometry": [
        r"triangl", r"\bcircle", r"\bangle", r"polygon", r"\bsquare", r"rectangl",
        r"hexagon", r"pentagon", r"trapezoid", r"\barea\b", r"perimeter", r"radius",
        r"diameter", r"parallel", r"perpendicular", r"vert(ex|ices)", r"hypotenuse",
        r"\bcoordinate", r"diagonal",
    ],
    "number_theory": [
        r"divis", r"\bprime", r"remainder", r"\bdigit", r"divisor", r"multiple of",
        r"greatest common", r"least common multiple", r"\bgcd\b", r"\blcm\b",
        r"modul", r"\binteger", r"factor", r"\bodd\b", r"\beven\b",
    ],
    "combinatorics": [
        r"how many ways", r"probabilit", r"\bchoose\b", r"arrang", r"permutation",
        r"combination", r"number of ways", r"\bcount", r"distinct", r"\bsubset",
    ],
    "algebra": [
        r"polynomial", r"equation", r"function", r"sequence", r"\bseries\b",
        r"\broot", r"expression", r"value of", r"\bsum\b", r"\bproduct\b",
    ],
}


def strip_math(text: str) -> str:
    """Remove math delimiters/commands so keyword matching sees plain words."""
    text = re.sub(r"\\[\(\)\[\]]", " ", text)
    text = re.sub(r"\$+", " ", text)
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    return text.lower()


def classify_topic(problem: str) -> str:
    """Pick the most likely topic from the problem stem via keyword voting."""
    haystack = strip_math(problem)
    best_topic = "algebra"
    best_score = 0
    for topic, patterns in TOPIC_KEYWORDS.items():
        score = sum(1 for pat in patterns if re.search(pat, haystack))
        if score > best_score:
            best_score, best_topic = score, topic
    return best_topic


def to_mathjax(text: str) -> str:
    """Normalize ``$...$`` / ``$$...$$`` to MathJax ``\\(...\\)`` / ``\\[...\\]``.

    Anki's reviewer typesets ``\\(...\\)`` and ``\\[...\\]`` via MathJax for free.
    Inputs already using those delimiters pass through unchanged.
    """
    if not text:
        return text
    text = re.sub(r"\$\$(.+?)\$\$", lambda m: r"\[" + m.group(1) + r"\]", text, flags=re.S)
    text = re.sub(r"(?<!\\)\$(.+?)(?<!\\)\$", lambda m: r"\(" + m.group(1) + r"\)", text, flags=re.S)
    return text


CARD_CSS = """
.card {
  font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
  font-size: 20px;
  color: #1a1a1a;
  background: #ffffff;
  max-width: 720px;
  margin: 0 auto;
  text-align: left;
  line-height: 1.5;
}
.meta { font-size: 13px; color: #888; text-transform: uppercase; letter-spacing: .04em; margin-bottom: 10px; }
.problem { margin-bottom: 18px; }
.choices { display: flex; flex-direction: column; gap: 10px; }
.choice {
  display: block; width: 100%; text-align: left; cursor: pointer; font: inherit; color: inherit;
  background: #fafafa; border: 1px solid #e0e0e0; border-radius: 10px; padding: 12px 14px;
  transition: background .12s, border-color .12s;
}
.choice::before { content: attr(data-letter) ".\\00a0\\00a0"; font-weight: 700; color: #666; }
.choice:hover:not(.locked) { background: #f0f4ff; border-color: #b9c8ff; }
.choice.selected { border-color: #5b7cfa; }
.choice.locked { cursor: default; }
.choice.correct { background: #e7f7ec; border-color: #2e9e54; }
.choice.correct::before { color: #2e9e54; }
.choice.incorrect { background: #fdebec; border-color: #d6453f; }
.choice.incorrect::before { color: #d6453f; }
#answer { margin: 18px 0; border: none; border-top: 2px solid #eee; }
.feedback { font-size: 16px; font-weight: 600; margin: 12px 0; }
.feedback.ok { color: #2e9e54; }
.feedback.bad { color: #d6453f; }
.feedback.neutral { color: #555; }
.solution { background: #fafafa; border-left: 3px solid #ddd; padding: 10px 14px; border-radius: 4px; }
.src { font-size: 12px; color: #aaa; margin-top: 14px; }
.nightMode.card { color: #e6e6e6; background: #2a2a2a; }
.nightMode .choice { background: #333; border-color: #444; }
.nightMode .choice:hover:not(.locked) { background: #2f3a5a; }
.nightMode .choice.correct { background: #1f3b29; border-color: #46b46e; }
.nightMode .choice.incorrect { background: #4a2422; border-color: #e06a64; }
.nightMode .solution { background: #333; border-left-color: #555; }
"""

# Front: problem stem + clickable choices. Clicking locks the selection (stored in
# sessionStorage) and reveals the answer side via pycmd("ans").
QFMT = """
<div class="meta">{{Contest}} {{Year}} &middot; Problem {{Number}} &middot; {{Topic}}</div>
<div class="problem">{{Problem}}</div>
<div class="choices" id="sr-choices">
  <button type="button" class="choice" data-letter="A">{{ChoiceA}}</button>
  <button type="button" class="choice" data-letter="B">{{ChoiceB}}</button>
  <button type="button" class="choice" data-letter="C">{{ChoiceC}}</button>
  <button type="button" class="choice" data-letter="D">{{ChoiceD}}</button>
  {{#ChoiceE}}<button type="button" class="choice" data-letter="E">{{ChoiceE}}</button>{{/ChoiceE}}
</div>
<script>
(function () {
  try { sessionStorage.removeItem("sr_sel"); } catch (e) {}
  var locked = false;
  document.querySelectorAll("#sr-choices .choice").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (locked) return;
      locked = true;
      var letter = btn.getAttribute("data-letter");
      try { sessionStorage.setItem("sr_sel", letter); } catch (e) {}
      btn.classList.add("selected");
      if (typeof pycmd !== "undefined") { pycmd("ans"); }
    });
  });
})();
</script>
"""

# Back: lock the choices, mark correct/incorrect, give feedback, reveal the
# solution, and report the attempt (correctness + chosen letter) to the host app.
AFMT = """
{{FrontSide}}
<hr id="answer">
<div id="sr-feedback" class="feedback neutral"></div>
<div class="solution">{{Solution}}</div>
{{#URL}}<div class="src">Source: <a href="{{URL}}">{{Source}} {{Contest}} {{Year}} #{{Number}}</a></div>{{/URL}}
<script>
(function () {
  var correct = "{{Answer}}".trim();
  var sel = null;
  try { sel = sessionStorage.getItem("sr_sel"); } catch (e) {}
  document.querySelectorAll("#sr-choices .choice").forEach(function (btn) {
    btn.classList.add("locked");
    btn.disabled = true;
    var letter = btn.getAttribute("data-letter");
    if (letter === correct) btn.classList.add("correct");
    else if (sel && letter === sel) btn.classList.add("incorrect");
  });
  var fb = document.getElementById("sr-feedback");
  if (fb) {
    if (!sel) {
      fb.className = "feedback neutral";
      fb.innerHTML = "Correct answer: <b>" + correct + "</b>";
    } else if (sel === correct) {
      fb.className = "feedback ok";
      fb.innerHTML = "\\u2713 Correct \\u2014 you chose <b>" + sel + "</b>";
    } else {
      fb.className = "feedback bad";
      fb.innerHTML = "\\u2717 Incorrect \\u2014 you chose <b>" + sel + "</b>; correct is <b>" + correct + "</b>";
    }
  }
  if (typeof pycmd !== "undefined") {
    var c = sel ? (sel === correct ? "1" : "0") : "";
    pycmd("speedrun:attempt:" + c + ":" + (sel || ""));
  }
})();
</script>
"""


def ensure_notetype(col: Collection):
    existing = col.models.by_name(NOTETYPE_NAME)
    if existing:
        return existing
    nt = col.models.new(NOTETYPE_NAME)
    for fname in FIELDS:
        col.models.add_field(nt, col.models.new_field(fname))
    tmpl = col.models.new_template("MC Card")
    tmpl["qfmt"] = QFMT
    tmpl["afmt"] = AFMT
    col.models.add_template(nt, tmpl)
    nt["css"] = CARD_CSS
    col.models.add(nt)
    return col.models.by_name(NOTETYPE_NAME)


def slug(value: str) -> str:
    """Lowercase alnum slug; Anki tags cannot contain spaces."""
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def contest_tag(contest: str) -> str:
    s = slug(contest)
    return f"amc::{s}" if s else "amc"


def add_problem(col: Collection, nt, problem: dict, deck_id) -> str:
    """Add one problem as a note in the given deck. Returns its resolved topic."""
    topic = (problem.get("topic") or classify_topic(problem["problem"])).lower()
    note = col.new_note(nt)
    note["Source"] = str(problem.get("source", ""))
    note["Contest"] = str(problem.get("contest", ""))
    note["Year"] = str(problem.get("year", ""))
    note["Number"] = str(problem.get("number", ""))
    note["URL"] = str(problem.get("url", ""))
    note["Problem"] = to_mathjax(problem["problem"])
    choices = problem.get("choices", {})
    for letter in ("A", "B", "C", "D", "E"):
        note[f"Choice{letter}"] = to_mathjax(choices.get(letter, ""))
    note["Answer"] = str(problem.get("answer", "")).strip().upper()
    note["Solution"] = to_mathjax(problem.get("solution", ""))
    note["Topic"] = topic

    tags = ["speedrun", f"source::{slug(problem.get('source', 'unknown'))}", f"topic::{topic}"]
    if problem.get("contest"):
        tags.append(contest_tag(str(problem["contest"])))
    if problem.get("year"):
        tags.append(f"year::{problem['year']}")
    note.tags = tags
    col.add_note(note, deck_id)
    return topic


def build_decks(decks: dict[str, list], out_path: Path, col_path: Path) -> dict:
    """Build one or more (sub)decks into a fresh collection and export the whole
    collection as a single .apkg. `decks` maps deck name -> list of problems.
    Returns a summary {"total": int, "topics": {topic: count}}.
    """
    if col_path.exists():
        col_path.unlink()
    col_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    col = Collection(str(col_path))
    try:
        nt = ensure_notetype(col)
        topic_counts: dict[str, int] = {}
        total = 0
        for deck_name, problems in decks.items():
            deck_id = col.decks.id(deck_name)
            for problem in problems:
                topic = add_problem(col, nt, problem, deck_id)
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
                total += 1

        col.export_anki_package(
            out_path=str(out_path),
            options=ExportAnkiPackageOptions(
                with_scheduling=False,
                with_deck_configs=False,
                with_media=True,
                legacy=True,
            ),
            limit=None,
        )
        return {"total": total, "topics": topic_counts}
    finally:
        col.close()


def build(input_path: Path, deck_name: str, out_path: Path, col_path: Path) -> int:
    problems = json.loads(input_path.read_text())
    summary = build_decks({deck_name: problems}, out_path, col_path)

    print(f"Built {summary['total']} notes into deck '{deck_name}'.")
    print("Topic distribution:")
    for topic in TOPICS:
        if topic in summary["topics"]:
            print(f"  {topic:14s} {summary['topics'][topic]}")
    for topic, n in summary["topics"].items():
        if topic not in TOPICS:
            print(f"  {topic:14s} {n}  (non-canonical)")
    print(f"\nWrote .apkg -> {out_path}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Build a Speedrun AMC .apkg from JSON.")
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--deck", default="Speedrun::AMC")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument(
        "--collection",
        type=Path,
        default=Path("speedrun/out/_build.anki2"),
        help="Scratch collection file used to assemble the deck.",
    )
    args = ap.parse_args(argv)
    return build(args.input, args.deck, args.out, args.collection)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
