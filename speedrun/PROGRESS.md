# Speedrun — Build Log

Concise log of what we've built on top of the Anki fork. Newest first.
See [prd.md](../prd.md) and [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md) for goals.

---

## The three scores: Memory / Performance / Readiness (shown separately)

Computed in the **shared Rust engine** (`rslib/src/stats/speedrun.rs`, new
`GetSpeedrunScores` RPC in `proto/anki/stats.proto`) so desktop and phone show
identical numbers. Formulas, weights, and give-up rules: [SCORES.md](SCORES.md).

- **Memory** = mean FSRS retrievability over taught cards (give-up: < 20 graded
  reviews). **Performance** = GRE-weighted first-attempt MC accuracy, shrunk
  toward the 20% guess rate; uncovered topics count at guess rate (give-up:
  < 30 first attempts or < 3 topics). **Readiness** = Performance mapped to
  200–990 via documented piecewise-linear anchors; confidence capped at
  *medium* because the mapping is an assumption (give-up: < 200 graded reviews
  or < 50% weighted coverage — abstains stating exactly what's missing).
- Topic weights: `speedrun/gre_topics.json` (ETS outline ≈ 50% calculus / 25%
  algebra / 25% additional), mirrored as `TOPIC_WEIGHTS` in Rust.
- MC tracking rewritten to a compact `custom_data` aggregate
  `{"sr":{"n","k","f","t"}}` — the old per-attempt log silently exceeded
  Anki's 100-byte custom_data cap after ~3 attempts (latent bug fixed).
- New storage helpers (`speedrun_card_rows`, `speedrun_last_review_times`,
  `speedrun_graded_review_count`) keep it one pass over cards + revlog —
  read-only, no transaction, FSRS/undo untouched.
- **Tests:** 5 Rust unit tests (weights, shrinkage, mapping anchors/monotonic,
  abstain-on-empty, attempt parsing) + Python end-to-end test (abstain →
  Memory appears past its give-up line; coverage math; integrity check).
- **UI:** desktop `qt/aqt/speedrun_scores.py` — "Scores" toolbar button +
  Tools-menu entry; mobile `SpeedrunScores.kt` — "Speedrun scores" in the
  deck-list ⋮ menu. Both show all required fields per score and the abstain
  state with the written give-up rule.
- **Follow-ups (validation):** memory calibration (Brier/log-loss on held-out
  reviews), performance held-out validation + 30×2 paraphrase test, leakage
  check script.

## Mixed sets are the default practice; GRE guaranteed in every mix

Interleaved (mixed) practice is the app's core learning-science thesis, so the **Mixed
sets are the default** and the single-source sets are opt-in. GRE topics stay disjoint
from AMC (AMC = algebra/geometry/number-theory/combinatorics; GRE = calculus, sequences/
series, ODEs, linear/abstract algebra, real/complex analysis, probability, multivariable
— i.e. only what AMC does *not* cover).

- **`Speedrun::Mixed::<tier> + GRE`** — **three** mixed sets (auto-imported), one per AMC
  difficulty tier (AMC 8 / 10 / 12), so a learner studies at their level; study the parent
  `Speedrun::Mixed` for an all-levels mix. Each is a single flat deck where the GRE
  problems are **spread evenly through that tier's most recent contests**
  (`build_all_decks.spread()` — GRE appears in every prefix). Because Anki gathers new
  cards by *position* up to the daily limit, position-spreading **guarantees GRE is
  gathered** even under a small `perDay`. Verified (AMC 12 mix, `perDay=20`): 5 GRE in the
  first 20, at positions 4,5,11,15,16.
- **`Speedrun::AMC 8/10/12`** (opt-in via picker): dedicated AMC-only tiers for blocked,
  exam-specific practice.
- **`Speedrun::GRE`** (opt-in via picker): dedicated GRE-only set, `Speedrun::GRE::<Topic>`.

**Engine fix (ships to desktop + phone).** The topic interleaver previously used a
"largest remaining bucket first" greedy, which clustered the minority GRE topics at the
*end* of the queue (first GRE only at position 18 in a mixed deck). Replaced with a
**least-emitted-fraction** strategy (`topic_interleaver.rs`): each step emits from the
topic that has so far emitted the smallest fraction `(emitted+0.5)/size` of its cards
(excluding the previous topic). This distributes *every* topic proportionally across the
whole queue, so 1–2-card minority topics (a GRE subject) appear early and throughout,
while still minimizing adjacency for a dominant topic. Integer cross-multiplication (no
float), deterministic, preserves within-topic order — FSRS/undo untouched. New Rust test
`spreads_minority_topics_throughout` + existing adjacency/order tests all green. Backend
`.aar` rebuilt and re-bundled so the phone gets the same guarantee.

- `speedrun/data/gre_problems.json` — original GRE-style MCQs (copyright-clean vs
  scraping ETS PDFs; scalable later via AI + safety pipeline), tagged
  `gre::gre_math_subject` / `source::gre_style` / `topic::*`.
- Auto-import tracks **per-deck codes** (desktop `speedrun_imported_deck_codes`; Android
  `StringSet`, both migrating the old boolean) so Mixed imports without duplicating AMC.

## Card UI — blue theme (matches mobile)

- `speedrun/card_theme.css` — single source of truth for the MC card styling: an
  AnkiDroid-blue identity (blue gradient top accent + `topic::` eyebrow, blue choice
  buttons with hover/selected states; correct/incorrect stay green/red), with a full
  night-mode variant. Used by `build_deck.py` (baked into generated decks) and
  `qt/aqt/speedrun_theme.py`, which refreshes the `Speedrun MC` note type's CSS on
  `collection_did_load` so existing desktop decks pick up the theme without re-import.
  Decks regenerated + mobile assets re-bundled + APK rebuilt so both apps match.

## Mobile repos (published)

Three repos, mirroring upstream's split:
- **Engine + desktop:** `alsy7009/speedrun` (this repo) — home of `rslib` with our changes.
- **AnkiDroid app fork:** `alsy7009/speedrun-ankidroid` — bundled AMC tier decks + picker.
- **Backend fork:** `alsy7009/speedrun-anki-backend` — its `anki` submodule → `alsy7009/speedrun`.

Others build mobile by cloning the two mobile repos side by side, then:
`cd speedrun-anki-backend && git submodule update --init --recursive && ./build.sh`,
then in `speedrun-ankidroid` set `local_backend=true` and build the APK.
(The `0.1.65-anki26.05b1` backend isn't on Maven, so a local backend build is required.)
Fork snapshots were pushed as single root commits (`--no-verify`, dropping upstream CI workflows).

## Mobile (AnkiDroid) — in progress

- **M0 toolchain (done):** JDK 17, Android SDK (platform 35/36, build-tools,
  platform-tools), emulator + arm64 system image, Rust Android targets, AVD `speedrun`.
- **M1 build+run (done):** AnkiDroid cloned to `speedrun/out/Anki-Android` (gitignored);
  built our `full-debug` APKs (per ABI) against the shared Rust backend; installed +
  launched on the emulator. `speedrun/mobile.sh` boots the emulator, installs the APK,
  and pushes the AMC deck.
- **In-app decks (done):** the 3 AMC **tier** decks (`AMC_8/10/12.apkg`) are bundled
  as app assets. New `SpeedrunDecks.kt` + `DeckPicker.kt` hooks: **auto-import all
  three tier folders on first launch** (guarded by a pref), and an **"Import AMC
  decks"** item in the deck-list ⋮ menu to re-add a tier. Rebuilt OK.
- **M2 shared engine on mobile (done):** built a **custom `rsdroid-release.aar`** from
  our 26.05 fork via `Anki-Android-Backend` (NDK 29 cross-compile of `rslib`), pointing
  its `anki/` submodule at our fork so the **single engine source** ships to mobile.
  AnkiDroid consumes it via `local_backend=true` (+ bumped `ankiBackend` to
  `0.1.65-anki26.05b1`; one enum-skew fix in `libanki/Deck.kt`). APK rebuilt and
  launches on the emulator with **no native/JNI crash** — so topic interleaving +
  topic scheduling now run on the phone (defaults are ON in the 26.05 deck config).
  Confirm interleaved order interactively by studying a deck.
- **M3 (todo):** self-host `anki-sync-server`; sync desktop ↔ phone both ways.

---

## All AMC decks + in-app deck picker

- `speedrun/build_all_decks.py` — generates one `.apkg` per **difficulty tier**
  (AMC 8 / AMC 10 / AMC 12), each a folder of full-named subdecks
  (`Speedrun::AMC 10::AMC 10A 2023`). A/B variants + predecessors (AHSME→AMC 12,
  AJHSME→AMC 8) fold into the tier. From HARP: **3 tier decks, 4,110 problems**
  (AMC 8: 915, AMC 10: 697, AMC 12: 2498). `build_deck.py` refactored into reusable
  `add_problem` / `build_decks`.
- `qt/aqt/speedrun_decks.py` (+ registered in `qt/aqt/__init__.py`) — a top-toolbar
  **"AMC Decks"** button / Tools menu that lists contests (problem count, year range,
  topic mix) with checkboxes + an **"Add starter set"** button, and imports the
  chosen `.apkg`s. **Auto-imports the 3 tier folders (AMC 8 / AMC 10 / AMC 12) on
  first collection load** (guarded by a config marker) — mirrors the Android app.
  Decks nest as `Speedrun::AMC 10::AMC 10A 2023`. Generated `.apkg`s are gitignored.
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
- `rslib/src/scheduler/queue/builder/topic_interleaver.rs` — **least-emitted-fraction**
  reorder (spreads every topic proportionally, so minority topics like a GRE subject
  appear throughout, not clustered at the end); resolves topic from each note's
  `topic::<name>` tag.
- `rslib/src/scheduler/queue/builder/mod.rs` — `build_queues` prefetches a
  `note_id -> topic` map; `build()` permutes the gathered `review`/`new` vecs
  **after** `sort_new()`. Only ordering changes — FSRS state, due dates, intervals,
  and counts are untouched, so scheduling and undo stay valid.
- `rslib/src/deckconfig/{mod,schema11}.rs` — default `false`, legacy round-trip
  (`topicInterleaving`) so the GUI/Python can toggle it (enables the ablation study).
- **Tests:** 5 Rust unit tests (interleaver, incl. minority-spread) + 1 Rust integration
  test (real queue build) + 1 Python end-to-end test (interleaved order + answer/undo +
  integrity). All green; clippy/mypy/ruff/svelte clean.
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
