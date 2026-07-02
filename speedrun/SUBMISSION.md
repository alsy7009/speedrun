# Wednesday MVP — submission checklist & proof

**Exam:** GRE Mathematics Subject Test (200–990).
**Commit:** the tip of `main` (a file can't contain its own hash — get it with
`git rev-parse HEAD`, or read it from the latest commit on GitHub). All results
and artifacts below were produced at that commit.
**License:** GNU AGPL v3+ (fork of Anki by Ankitects; see `README.md`).

## Status vs. the Wednesday checklist (PRD §12)

| Requirement | Status | Evidence |
| --- | --- | --- |
| Anki forked & building from source (desktop) | ✅ | `just run` / `just check` |
| Rust engine change, end-to-end (diff + ≥3 Rust tests + 1 Python test) | ✅ | `speedrun/RUST_ENGINE_CHANGE.md`; tests below |
| Undo works + collection not corrupted | ✅ | `test_speedrun.py` (answer→undo→`pragma integrity_check`) |
| Review loop on the AMC/GRE deck | ✅ | interactive MC, interleaved |
| Memory model, honest score (range + give-up) | ✅ | all three scores; `speedrun/SCORES.md` |
| Desktop installer (clean machine) | ✅ | `out/installer/dist/anki-26.05-mac-apple.dmg` (218 MB) |
| Android builds/runs, loads deck, real review on shared engine | ✅ | `AnkiDroid-full-arm64-v8a-debug.apk` (115 MB) |

## Test results (this commit)

Rust (engine, `cargo test -p anki`):
- `topic_interleaver::test` — **5 passed**
- `scheduler::states::review::test::topic*` — **2 passed**
- `stats::speedrun::test` — **5 passed**
- `builder::test::topic_interleaving_separates_adjacent_cards` (integration) — **1 passed**

Python (`pytest pylib/tests/test_speedrun*.py`): **6 passed**
(interleaving + answer/undo/integrity; three-scores abstain→show; timed test;
review-mistakes deck; two-device sync merge; sync conflict winner).

Reproduce:
```bash
CARGO_TARGET_DIR=$PWD/out/rust cargo test -p anki --lib topic_interleaver stats::speedrun states::review
PYTHONPATH="pylib:out/pylib" out/pyenv/bin/python -m pytest pylib/tests/test_speedrun.py pylib/tests/test_speedrun_sync.py -q
```

## Build artifacts

- Desktop installer: `out/installer/dist/anki-26.05-mac-apple.dmg`
  (built with `./ninja installer:package`; needs `just wheels` first).
- Wheels: `out/wheels/anki-26.5-*.whl`, `out/wheels/aqt-26.5-*.whl`.
- Android APK: `speedrun/out/Anki-Android/AnkiDroid/build/outputs/apk/full/debug/AnkiDroid-full-arm64-v8a-debug.apk`.

## Recordings to capture (only these are left)

1. **Clean build (desktop):** fresh `git clone`, then `just run` → app launches.
2. **Test results:** run the two commands above on camera.
3. **Rust change in action:** study a Speedrun deck; show consecutive cards are
   different topics (interleaving) — toggle it off in Settings to contrast.
4. **Clean install (desktop):** open `anki-26.05-mac-apple.dmg` on a machine
   without the dev tree, drag to Applications, launch, study a card.
5. **Phone review session:** `bash speedrun/mobile.sh --reset`, open AnkiDroid,
   study a card on the emulator/device (shared Rust engine).
6. **(Deliverable) 3–5 min demo video** covering the above + the three scores.

## Repo hand-in items

- Exam stated up front, build instructions (both apps), architecture, Rust-change
  note, files-touched list → `README.md`.
- Model descriptions (Memory/Performance/Readiness + give-up) → `speedrun/SCORES.md`.
- Rust-change note (why-Rust, files, merge risk) → `speedrun/RUST_ENGINE_CHANGE.md`.
- Build log → `speedrun/PROGRESS.md`.
- **To confirm:** GitHub repo is public; Brainlift (`brainlift_speedrun.pdf`) final.

## Notes / honest caveats

- The `.dmg` is **unsigned** (no Apple Developer signing); on a clean Mac use
  right-click → Open (Gatekeeper). Signing is a Friday/Sunday concern.
- No AI yet — per the "no AI before Friday" rule. The app scores fully with AI
  off (there is no AI path to disable).
