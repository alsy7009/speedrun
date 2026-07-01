# The Rust Engine Change

Speedrun makes two changes to Anki's Rust engine (`rslib`), both driven by note
tags of the form `topic::<name>` and gated behind deck-config options:

1. **Topic-aware interleaving queue** — reorders the gathered review/new queue so
   consecutive cards come from different topics (strategy discrimination) and every
   topic is spread proportionally, so minority topics (e.g. a GRE subject mixed into
   AMC) appear throughout the session rather than clustered at the end.
2. **Topic-aware scheduling** — shortens the next review interval for weak
   (high FSRS-difficulty) topic-tagged cards so they come back sooner.

Both ship to **desktop and the Android phone** because they compile into the one
shared engine (see `PROGRESS.md` → "M2").

---

## Why this belongs in Rust, not Python (one page)

**It's engine-level, and shared by both apps.** Queue building and answer-time
scheduling live entirely in `rslib`. The desktop (via PyO3) and AnkiDroid (via
JNI) both call the *same* compiled engine. Writing this once in Rust means the
change reaches both clients with no duplication; a Python implementation would
only affect desktop, violating the "one engine, two apps" requirement and never
reaching the phone.

**It must respect FSRS and undo, which are Rust-owned invariants.** FSRS memory
state (`stability`, `difficulty`) and the undo journal are computed and enforced
in Rust. Interleaving only permutes the *already-gathered* `Vec<DueCard>` /
`Vec<NewCard>` before they become `CardQueues` — it never touches `due`,
`interval`, or `memory_state`, so scheduling and undo stay valid. Topic
scheduling applies its multiplier at the exact seam Anki already uses to scale
review intervals (`constrain_passing_interval`), leaving `memory_state`
untouched. Doing this correctly requires being *inside* the scheduling math; a
Python post-filter can't reorder the queue without desyncing the cached
`CardQueues`, and can't adjust intervals without corrupting FSRS state.

**It has to be fast on 50k cards.** The queue is rebuilt every session and the
interleave runs over the whole gathered set; the interval multiplier runs on
every answer. This is hot-path work that belongs in the compiled engine, not in
a per-card Python callback crossing the FFI boundary.

**The data is already there.** Topic comes from note tags (read in bulk via
`get_note_tags_by_id_list`); weakness comes from the FSRS `difficulty` already
stored on each card. No new model or recomputation — just engine logic reading
existing engine data.

---

## Tests

**Rust unit tests** (`rslib`):
- `scheduler/queue/builder/topic_interleaver.rs`: `separates_consecutive_when_balanced`,
  `minimizes_adjacency_for_dominant_topic`, `handles_degenerate_cases`,
  `preserves_within_topic_order`, `spreads_minority_topics_throughout`.
- `scheduler/states/review.rs`: `topic_scheduling_shortens_passing_intervals`,
  `topic_scheduling_under_fsrs_preserves_memory_state`.

**Rust integration test**: `scheduler/queue/builder/mod.rs`
`topic_interleaving_separates_adjacent_cards` — builds a real queue on a tagged
deck and asserts consecutive cards differ in topic.

**Python end-to-end** (`pylib/tests/test_speedrun.py`):
`test_topic_interleaving_end_to_end` — enables `topicInterleaving`, adds tagged
notes, asserts the built queue interleaves, then **answers a card, calls
`col.undo()`, and asserts `pragma integrity_check == "ok"`** (undo works, no
corruption).

Run: `just test-rust` and `just test-py` (or `cargo test -p anki topic_`).

---

## Upstream files touched + future-merge difficulty

**New files (no conflict risk):**
- `rslib/src/scheduler/queue/builder/topic_interleaver.rs` — interleaver + topic parsing.
- `pylib/tests/test_speedrun.py` — Python end-to-end test.

**Modified upstream files (all additive/localized → LOW merge risk):**

| File | Change | Merge risk |
|---|---|---|
| `proto/anki/deck_config.proto` | 3 appended fields (47/48/49) | Very low — wire-stable, append-only |
| `rslib/src/deckconfig/mod.rs` | default values + one `ensure_f32_valid` | Low — additive lines in a const/list |
| `rslib/src/deckconfig/schema11.rs` | legacy round-trip for the 3 fields | Low — additive struct fields + From arms |
| `rslib/src/scheduler/queue/builder/mod.rs` | `mod` decl, `QueueSortOptions`/`QueueBuilder` fields, `sort_options()`, insert in `build()`, prefetch in `build_queues()` | Low–moderate — several small additive hunks |
| `rslib/src/scheduler/states/mod.rs` | one `StateContext` field + test default | Low |
| `rslib/src/scheduler/states/review.rs` | one line in `constrain_passing_interval` | Low — single hot-path seam |
| `rslib/src/scheduler/answering/mod.rs` | `CardStateUpdater` field + `state_context()` wiring + `topic_interval_multiplier()` helper | Low–moderate |

**Overall:** LOW. Everything is additive, behind default-off-then-opt-in config,
and the bulk of the new logic is isolated in a new module. The only edits to
upstream scheduling math are (a) one call site in `QueueBuilder::build` and (b)
one multiplier line in `constrain_passing_interval`. A future rebase onto
upstream Anki would mainly need to re-apply those two small hunks.

---

## Phone

The change is verified on the Android build: `Anki-Android-Backend` was compiled
from this fork's `rslib` into a custom `rsdroid.aar` (NDK cross-compile), and
AnkiDroid runs against it (`local_backend`) with no JNI/native crash. Because the
deck-config defaults enable both features, the behavior is active on mobile from
the same code. See `PROGRESS.md` → "M2".
