# Speedrun — 5-minute demo script

Target: hit every graded item — the Rust engine change, the three honest scores,
both apps on one engine, sync, and proof (tests + installer). No AI (correct for
this milestone; the app scores fully without it).

## Before you hit record (setup, ~5 min)

1. **Desktop running from source:** `just run` (so the Speedrun toolbar buttons
   show: Timed Test · Review · Scores · Settings · Speedrun Decks).
2. **A studied profile for the scores demo:** have one profile where you've done
   ~30+ reviews across a few topics (so Memory shows and you can contrast with a
   fresh profile that abstains). Keep a fresh profile too.
3. **Emulator up with the latest APK:** `bash speedrun/mobile.sh` (or `--reset`
   for a clean first-run). Import a Mixed deck.
4. **Sync server ready in a terminal:** `bash speedrun/sync_server.sh`
   (user `speedrun` / `speedrun`). Point desktop Preferences→Syncing and
   AnkiDroid Settings→Sync at it beforehand, signed in on both.
5. **A terminal ready** for the test-results command (below).
6. Have the commit hash handy: `git rev-parse HEAD`.

## Script (minute by minute)

**0:00–0:30 — What it is.**
"Speedrun trains for the **GRE Math Subject Test** using hard competition-math
problems. It's built *inside* Anki — we changed the shared **Rust engine**, so
one engine powers both a desktop app and an Android app."

**0:30–1:30 — The Rust change, visible (interleaving).**
- Study a `Speedrun::Mixed` deck. Point out consecutive cards are **different
  topics** (algebra → calculus → geometry…), and GRE topics are mixed in.
- Open **Settings**, uncheck "Interleave topics," study again → now it's blocked
  (same topic clumped). Re-enable it.
- Say: "This reorder happens in `rslib` (`topic_interleaver.rs`), with unit tests
  plus a Python test proving undo and no corruption — and because it's in the
  engine, it ships to the phone too."

**1:30–2:15 — Practice test → review the misses.**
- Click **Timed Test**. Show the **40:00 countdown** and that it's **one-shot**
  (no Learn count — it's a test, not flashcards). Answer a few, get some wrong.
- Finish → the **Review screen** pops up: score + worked solutions. Click
  **"Review the N I missed — rate them →"** → drills just those with solutions
  and Again/Hard/Good/Easy. "Testing yourself then drilling misses is the
  highest-yield way to raise a score."

**2:15–3:10 — Three honest scores.**
- Open **Scores** on the **fresh** profile → all three **abstain** with the
  give-up rule ("No score until 200 graded reviews AND 50% coverage").
- Switch to the **studied** profile → **Memory / Performance / Readiness** show
  **separately**, each with a **range**, coverage %, confidence, and reasons.
- "Memory is FSRS recall; Performance is new-question accuracy; Readiness maps to
  200–990 with a range — never one blended number, and it refuses to guess
  without data."

**3:10–3:55 — Same engine on the phone.**
- Show the emulator: the same **Mixed** decks, interactive MC, the timed test
  with the countdown, and ⋮ → **Speedrun scores**. "Same Rust backend via JNI."

**3:55–4:35 — Sync (no lost/double-counted reviews).**
- Review a card on the **phone**, tap sync. On the **desktop**, sync → show the
  review/card appears. "Anki's built-in self-hosted server — our own Rust code,
  no third-party service."

**4:35–5:00 — Proof.**
- In the terminal: run the tests, show green:
  ```
  CARGO_TARGET_DIR=$PWD/out/rust cargo test -p anki --lib topic_interleaver stats::speedrun states::review
  PYTHONPATH="pylib:out/pylib" out/pyenv/bin/python -m pytest pylib/tests/test_speedrun.py pylib/tests/test_speedrun_sync.py -q
  ```
- Show the packaged installer: `out/installer/dist/*.dmg` → `Speedrun.app`.
- "Fork of Anki under AGPL; commit `<hash>`. Thanks!"

## If you're over time (trim in this order)
1. Drop the Settings ablation toggle (just narrate interleaving).
2. Shorten the phone segment to a single glance.
3. Cut the live test run; show a pre-captured results screenshot.

## One-liners to have on screen
- Exam: GRE Mathematics Subject Test (200–990).
- Rust change: `rslib/src/scheduler/queue/builder/topic_interleaver.rs`,
  topic-aware scheduling, `stats/speedrun.rs`. See `RUST_ENGINE_CHANGE.md`.
- Scores + give-up rules: `speedrun/SCORES.md`.
- Everything built: `speedrun/PROGRESS.md`; submission checklist: `SUBMISSION.md`.
