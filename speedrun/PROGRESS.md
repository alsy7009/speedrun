# Speedrun — Build Log

Concise log of what we've built on top of the Anki fork. Newest first.
See [prd.md](../prd.md) and [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md) for goals.

---

## All AMC decks + in-app deck picker

- `speedrun/build_all_decks.py` — generates one `.apkg` per AMC contest (AMC 8/10/10A/
  10B/12/12A/12B + AHSME/AJHSME), each with a subdeck per year, plus
  `speedrun/decks/manifest.json`. From HARP: **9 decks, 4,110 problems**.
  `build_deck.py` refactored into reusable `add_problem` / `build_decks`.
- `qt/aqt/speedrun_decks.py` (+ registered in `qt/aqt/__init__.py`) — adds
  **Tools → "Speedrun: Add AMC Decks…"**, a dialog that lists contests (problem
  count, year range, topic mix) with checkboxes, an **"Add starter set"** button
  (AMC 8 / 10A / 12A pre-checked), and imports the chosen `.apkg`s into the
  collection. Generated `.apkg`s are gitignored (MAA content); regenerate locally.

## Rust engine change — topic-aware interleaving queue (graded centerpiece)

**Goal:** guarantee consecutive review/new cards come from different topics
(strategy discrimination), in the shared Rust engine, without breaking FSRS/undo.

- `proto/anki/deck_config.proto` — new `bool topic_interleaving = 47;` on `Config`.
- `rslib/src/scheduler/queue/builder/topic_interleaver.rs` — greedy "most-remaining
  distinct topic" reorder; resolves topic from each note's `topic::<name>` tag.
- `rslib/src/scheduler/queue/builder/mod.rs` — `build_queues` prefetches a
  `note_id -> topic` map; `build()` permutes the gathered `review`/`new` vecs
  **after** `sort_new()`. Only ordering changes — FSRS state, due dates, intervals,
  and counts are untouched, so scheduling and undo stay valid.
- `rslib/src/deckconfig/{mod,schema11}.rs` — default `false`, legacy round-trip
  (`topicInterleaving`) so the GUI/Python can toggle it (enables the ablation study).
- **Tests:** 4 Rust unit tests (interleaver) + 1 Rust integration test (real queue
  build) + 1 Python end-to-end test (interleaved order + answer/undo + integrity).
  All green; clippy/mypy/ruff/svelte clean.
- **Upstream files touched:** `deck_config.proto`, `deckconfig/mod.rs`,
  `deckconfig/schema11.rs`, `scheduler/queue/builder/mod.rs` (+ new module). Merge
  risk: low — append-only proto field, additive struct fields, one call site.

## Interactive multiple-choice cards + attempt tracking

- `speedrun/build_deck.py` template — choices are clickable; clicking locks the
  pick, reveals the worked solution, and marks correct (green) / incorrect (red),
  with a ✓/✗ feedback line. Self-contained (works from the imported `.apkg`).
- `qt/aqt/speedrun_tracking.py` (+ registered in `qt/aqt/__init__.py`) — persists
  each attempt (`{chosen letter, correct, time}`) to the card's `custom_data`
  (which syncs), to later feed the performance/readiness models. Requires running
  the fork (not just the `.apkg`).

---

## Content pipeline — AMC decks

**Goal:** turn real AMC competition problems into interleaved, topic-tagged Anki decks.

- `speedrun/build_deck.py` — source-agnostic deck builder. Defines the **"Speedrun MC"**
  note type (fields: stem, 5 choices, answer letter, worked solution, topic,
  contest/year/number/URL), tags notes by topic for interleaving, converts `$…$`
  math to MathJax `\(…\)`, and exports a `.apkg`.
- `speedrun/harp_to_speedrun.py` — converts the [HARP dataset](https://github.com/aadityasingh/HARP)
  (AoPS-wiki problems; © MAA, MIT-licensed annotations) into the builder schema,
  using HARP's human subject labels mapped to our 4 interleaving topics
  (algebra / geometry / number_theory / combinatorics).
- `speedrun/data/sample_problems.json` — synthetic problems for pipeline validation.
- Heuristic topic classifier (keyword voting) as a fallback when a source lacks labels.

**Built:** `2022 AMC 10A` deck — 13 problems (HARP MC split drops diagram/inconsistent
items), interleaved across algebra (6) / geometry (5) / number theory (2). Tags:
`topic::*`, `amc::amc_10a`, `year::2022`, `source::harp_aops_maa`, `speedrun`.

**Note:** AMC covers algebra/geometry/number theory/combinatorics — _not calculus_
(~50% of the GRE Math Subject Test). Relevant later for the coverage map / readiness.
