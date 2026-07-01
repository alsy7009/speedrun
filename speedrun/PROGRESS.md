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
- `qt/aqt/speedrun_settings.py` (+ registered in `qt/aqt/__init__.py`) — a
  **"Settings"** top-toolbar button / Tools-menu entry opening a dialog with
  checkboxes: **Enable FSRS** (seeds default params so answering can't break),
  **Interleave topics**, and **Topic-aware scheduling**. All three are **ON by
  default** — the engine deck-config defaults are `true`, and a one-time
  `collection_did_load` pass enables FSRS + the topic flags on all existing
  presets (guarded by a config marker so later manual changes are respected).

## Rust engine change — topic-aware scheduling (weak topics return sooner)

**Goal:** bring weak-topic cards back sooner by shortening their next review
interval, while keeping FSRS memory state valid and undo working. Default OFF.

- `proto/anki/deck_config.proto` — `bool topic_scheduling = 48;` +
  `float topic_weak_interval_factor = 49;` (+ default/validation in
  `deckconfig/mod.rs`, legacy round-trip in `schema11.rs`).
- `rslib/src/scheduler/answering/mod.rs` — `CardStateUpdater` computes a per-card
  interval multiplier: only for `topic::`-tagged cards with FSRS state, scaled by
  the card's FSRS **difficulty** (1.0 for easy → `topic_weak_interval_factor` for
  hardest). Threaded into `StateContext`.
- `rslib/src/scheduler/states/{mod,review}.rs` — applied in
  `constrain_passing_interval` (same seam as the SM-2 interval multiplier),
  **before** fuzz/clamp. Only `scheduled_days` changes; `memory_state` (stability/
  difficulty) is never touched, so FSRS stays valid and undo restores the prior
  interval via the existing card snapshot.
- **Tests:** 2 Rust unit tests — intervals shorten under the multiplier (SM-2 path)
  and, under FSRS, the interval halves while memory state is preserved.
- Enable (debug console): `conf["topicScheduling"]=True` (requires FSRS on).
- *Note:* weakness is the card's FSRS difficulty; a true per-topic aggregate
  (mean recall) is a follow-up that can reuse the dashboard mastery query.

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
