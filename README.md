# Speedrun — GRE Math Subject Test trainer

**Target exam: the GRE Mathematics Subject Test (scored 200–990).**

Speedrun is a desktop + mobile study app built **inside** the
[Anki](https://apps.ankiweb.net) codebase (a brownfield fork — we change the
shared Rust engine, not just the screens). It trains for the GRE Math Subject
Test with hard competition-math (AMC) problems plus original GRE-topic problems,
using two evidence-based methods:

- **Interleaving** — consecutive problems come from *different* topics, so you
  practice choosing the right strategy, not repeating one. Implemented in the
  Rust queue builder.
- **Retrieval / practice testing** — interactive multiple-choice with worked
  solutions, spaced by Anki's FSRS memory model, plus a timed practice test.

One shared Rust engine powers both the desktop app and the Android app.

## The three scores (shown separately, never blended)

- **Memory** — chance you recall a taught fact now (FSRS retrievability).
- **Performance** — chance you get a *new* exam-style question right.
- **Readiness** — projected 200–990 score, with a range.

Each score shows a point estimate, likely range, exam-coverage %, confidence,
last-updated time, reasons, and an explicit **give-up rule** (it shows *no*
score when it lacks data). Formulas and give-up rules: [`speedrun/SCORES.md`](speedrun/SCORES.md).

## The Rust engine change (required, brownfield)

Topic-aware **interleaving queue** + topic-aware **scheduling**, plus a fast
per-topic **scores query** — all in `rslib`, so they ship to desktop *and* the
phone. Rationale, tests, and merge-risk analysis: [`speedrun/RUST_ENGINE_CHANGE.md`](speedrun/RUST_ENGINE_CHANGE.md).
Includes ≥3 Rust unit tests + Python end-to-end tests, with undo + collection
integrity checks.

## Build & run

Prerequisites and the full toolchain follow upstream Anki (see
[`docs/development.md`](docs/development.md)). Every task is a `just` recipe —
run `just --list`.

### Desktop
```bash
just run              # build pylib + qt and launch (dev)
just run-optimized    # release-optimized build
just check            # format + build + all tests (Rust/Python/TS)
```
Speedrun adds toolbar buttons: **Speedrun Decks**, **Timed Test**, **Scores**,
**Settings**. FSRS + interleaving + topic scheduling are on by default.

### Android (AnkiDroid + our Rust backend)
The phone app is the [AnkiDroid](https://github.com/ankidroid/Anki-Android) fork
in `speedrun/out/Anki-Android`, consuming a Rust backend built from this repo:
```bash
# 1) Build the Rust backend (.aar) from our engine:
cd speedrun/out/Anki-Android-Backend && ./build.sh
# 2) Build + install the APK (or use the helper below):
bash speedrun/mobile.sh            # boots emulator, installs, pushes decks
```
Published mobile forks (so others can build without this checkout):
`alsy7009/speedrun-ankidroid` and `alsy7009/speedrun-anki-backend` (its `anki`
submodule points back here).

### Content decks
```bash
PYTHONPATH="pylib:out/pylib" out/pyenv/bin/python speedrun/build_all_decks.py \
    --harp speedrun/out/harp/HARP_mcq.jsonl --out-dir speedrun/decks
```
Produces the default **Mixed** sets (AMC tier + GRE, interleaved) plus dedicated
AMC-only / GRE-only sets. Sources: AMC via the HARP dataset (© MAA); GRE-topic
problems are original.

### Sync (desktop ↔ phone)
Anki's built-in self-hosted sync server — no external service:
```bash
bash speedrun/sync_server.sh   # user: speedrun / speedrun, port 8080
```
Point desktop (Preferences → Syncing) and AnkiDroid (Settings → Sync) at it.
Conflict rule is documented in [`speedrun/PROGRESS.md`](speedrun/PROGRESS.md).

## Architecture

Anki's layers, and where Speedrun lives:

- **Rust engine** `rslib/` — scheduler, FSRS, storage, sync. *Speedrun:*
  `scheduler/queue/builder/topic_interleaver.rs`, topic scheduling in
  `scheduler/{answering,states}`, `stats/speedrun.rs` (scores),
  `sync/` (self-hosted server).
- **Protobuf** `proto/` — the cross-language API. *Speedrun:* fields in
  `deck_config.proto`, `GetSpeedrunScores` in `stats.proto`.
- **Python** `pylib/` — wraps the engine. *Speedrun:* `anki/speedrun.py`
  (timed test), tests in `pylib/tests/test_speedrun*.py`.
- **Desktop GUI** `qt/aqt/` — PyQt + webviews. *Speedrun:* `speedrun_*.py`
  modules (decks, scores, settings, timed test, theme, tracking, UI skin).
- **Mobile** — AnkiDroid (Kotlin) over the same Rust backend via JNI.

## Files we touched (for a future upstream merge)

- **New (Speedrun-owned):** `rslib/src/stats/speedrun.rs`,
  `rslib/src/scheduler/queue/builder/topic_interleaver.rs`,
  `pylib/anki/speedrun.py`, `qt/aqt/speedrun_*.py`, everything under
  `speedrun/`, `pylib/tests/test_speedrun*.py`.
- **Modified upstream (additive/low-risk):** `proto/anki/{deck_config,stats}.proto`;
  `rslib/src/deckconfig/{mod,schema11}.rs`;
  `rslib/src/scheduler/queue/builder/mod.rs`;
  `rslib/src/scheduler/{answering/mod,states/mod,states/review}.rs`;
  `rslib/src/stats/{mod,service}.rs`; `rslib/src/storage/{card,revlog}/mod.rs`;
  `qt/aqt/__init__.py`. Merge risk is low — appended proto fields, additive
  struct fields, and single call sites (details in `RUST_ENGINE_CHANGE.md`).

## Build log

Running notes on everything built: [`speedrun/PROGRESS.md`](speedrun/PROGRESS.md).

## License & credit

Speedrun is a fork of **Anki** by Ankitects Pty Ltd
(<https://github.com/ankitects/anki>), used and distributed under the
**GNU AGPL v3 or later**. All upstream copyrights remain with their authors;
Speedrun's additions carry the same license. Original Anki documentation is
preserved under `docs/` and below.

---

# Anki (upstream)

This repository is built on Anki. See [`docs/development.md`](docs/development.md)
for the original build/development guide and <https://apps.ankiweb.net> to learn
more about Anki itself.
