# Copyright: Speedrun
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Speedrun timed test: an exam-style 10-question / 20-minute session.

Flow (a real practice test — the highest-yield way to raise a score):

1. **Test pass:** one tap builds the "Speedrun Timed Test" filtered deck (20
   questions) and drops you in. Each shows choices + a 40:00 countdown; picking
   an answer records it but the **worked solution stays hidden** — you rate
   difficulty to advance, cycling through all 20 once.
2. **Drill the misses:** when the test finishes, the cards you got wrong (or
   didn't answer) are gathered into the "Speedrun Review Mistakes" deck and
   opened for **interactive** re-practice — solutions shown, normal flow. This
   is the crucial part: practicing what you missed.

Timer + solution-hiding are injected by a ``card_will_show`` hook (keyed on the
card's current deck ``card.did``), so they work regardless of the deck's stored
template. A static score/solution summary is also available under Tools.
"""

from __future__ import annotations

import json
import time
from typing import Any

import aqt
from anki.speedrun import build_review_deck, build_timed_test
from aqt import gui_hooks
from aqt.qt import (
    QAction,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QScrollArea,
    Qt,
    QVBoxLayout,
    QWidget,
    qconnect,
)
from aqt.utils import showInfo, tooltip

# Card ids in the current timed session (captured at start, before they leave
# the filtered deck as they're answered). Also persisted to the collection
# config so the review still works after an app restart.
_session_cids: list[int] = []
_session_active = False
# Epoch-ms when the current test was started/rebuilt. Injected into every card
# as window.SR_TIMED_START so the countdown resets whenever the test is rebuilt.
_session_start_ms = 0

_CONFIG_KEY = "speedrun_timed_session"


def _session(mw: Any) -> list[int]:
    """The last timed session's card ids — from memory, falling back to the
    persisted config (survives restarts)."""
    if _session_cids:
        return _session_cids
    try:
        return [int(c) for c in (mw.col.get_config(_CONFIG_KEY, None) or [])]
    except Exception:
        return []

# Self-contained countdown banner (inline-styled; no template/CSS dependency).
# The session start is provided by the host (window.SR_TIMED_START) so rebuilding
# the deck restarts the clock from 40:00.
_TIMER_WIDGET = """
<div id="sr-timed-banner" style="display:inline-block;font:700 13px -apple-system,
'Segoe UI',Roboto,sans-serif;letter-spacing:.04em;color:#0d47a1;background:#e3f0fb;
border:1px solid #b7d6f4;border-radius:999px;padding:6px 15px;margin-bottom:14px;"></div>
<script>
(function () {
  var el = document.getElementById("sr-timed-banner");
  if (!el) return;
  var LIMIT = 40 * 60 * 1000;
  var start = Number(window.SR_TIMED_START || 0);
  if (!start) { start = Date.now(); }  // fallback if host didn't provide one
  function tick() {
    var left = LIMIT - (Date.now() - start);
    if (left <= 0) {
      el.style.color = "#b3261e"; el.style.background = "#fdecea";
      el.style.borderColor = "#f2b8b5";
      el.textContent = "\\u23F1 Time's up \\u2014 finish and review your answers";
      return;
    }
    var m = Math.floor(left / 60000), s = Math.floor((left % 60000) / 1000);
    el.textContent = "\\u23F1 Timed test \\u2014 " + m + ":" + (s < 10 ? "0" : "") + s + " left";
    if (window.srTimerTimeout) clearTimeout(window.srTimerTimeout);
    window.srTimerTimeout = setTimeout(tick, 1000);
  }
  tick();
})();
</script>
"""

# Answer side during the test: hide the worked solution, source, and the
# correct/incorrect verdict; show a neutral "recorded" note instead.
_HIDE_SOLUTION = """
<style>
#sr-feedback, .solution, .src { display: none !important; }
</style>
<div style="margin-top:10px;color:#5a7184;font:600 14px -apple-system,'Segoe UI',
Roboto,sans-serif;">Answer recorded. Rate how hard it felt and continue —
solutions come at the end.</div>
"""


def _in_timed_deck(card: Any) -> bool:
    mw = aqt.mw
    if mw is None or mw.col is None:
        return False
    try:
        return "timed test" in mw.col.decks.name(card.did).lower()
    except Exception:
        return False


def _inject_timed(text: str, card: Any, kind: str) -> str:
    """Add the countdown to timed-test cards, and hide the solution on the
    answer side so it isn't revealed mid-test. The session start is injected as
    window.SR_TIMED_START so the clock resets each time the test is rebuilt."""
    if not _in_timed_deck(card):
        return text
    start = _session_start_ms or int(time.time() * 1000)
    out = f"<script>window.SR_TIMED_START={start};</script>" + _TIMER_WIDGET + text
    if kind in ("reviewAnswer", "clayoutAnswer"):
        out += _HIDE_SOLUTION
    return out


def _start_timed_test() -> None:
    global _session_cids, _session_active, _session_start_ms
    mw = aqt.mw
    if mw is None or mw.col is None:
        return
    did = build_timed_test(mw.col)
    if did is None:
        showInfo(
            "No Speedrun cards are due or unseen right now — import a Speedrun "
            "deck (toolbar) or come back when reviews are due.",
            parent=mw,
        )
        return
    # Capture the session's cards now, before answering moves them out.
    _session_cids = list(mw.col.find_cards(f"did:{did}"))
    mw.col.set_config(_CONFIG_KEY, _session_cids)  # survives app restart
    _session_active = True
    _session_start_ms = int(time.time() * 1000)  # restart the 40:00 clock
    mw.col.decks.set_current(did)
    mw.reset()
    mw.moveToState("overview")
    n = len(_session_cids)
    tooltip(
        f"Timed test: {n} questions, 40 minutes. Solutions come after — then you "
        "drill the ones you miss.",
        parent=mw,
    )


def _wrong_cids(mw: Any) -> list[int]:
    """Session cards whose first attempt was not correct (missed or unanswered)."""
    out = []
    for cid in _session(mw):
        try:
            card = mw.col.get_card(cid)
        except Exception:
            continue
        if _was_correct(card) is not True:
            out.append(cid)
    return out


def _on_reviewer_will_end() -> None:
    """Phase 1 finished: automatically pop the in-app review screen (a modal is
    far more reliable to show mid-transition than a state change)."""
    global _session_active
    if not _session_active:
        return
    _session_active = False
    mw = aqt.mw
    if mw is None or mw.col is None or not _session(mw):
        return
    # Defer so the current reviewer finishes tearing down first.
    from aqt.qt import QTimer

    QTimer.singleShot(200, _show_post_test_review)


def _show_post_test_review() -> None:
    mw = aqt.mw
    if mw is None or mw.col is None or not _session(mw):
        return
    TimedReviewDialog(mw, _session(mw)).show()


def _start_mistake_drill() -> None:
    mw = aqt.mw
    if mw is None or mw.col is None:
        return
    total = len(_session(mw))
    wrong = _wrong_cids(mw)
    correct = total - len(wrong)
    did = build_review_deck(mw.col, wrong)
    if did is None:
        tooltip(
            f"Test complete: {correct}/{total} correct. Perfect — nothing to review!",
            parent=mw,
        )
        return
    mw.col.decks.set_current(did)
    mw.reset()
    # Go straight into the flashcard review of the missed cards: solutions are
    # shown and the Again/Hard/Good/Easy rating feeds FSRS (what to review next).
    mw.moveToState("review")
    tooltip(
        f"Reviewing the {len(wrong)} you missed — read each solution and rate it.",
        parent=mw,
    )


def _fld(note: Any, name: str) -> str:
    try:
        return note[name]
    except (KeyError, IndexError):
        return ""


def _was_correct(card: Any) -> bool | None:
    try:
        data = json.loads(card.custom_data) if card.custom_data else {}
        sr = data.get("sr")
        if not sr or int(sr.get("n", 0)) < 1:
            return None
        return int(sr.get("f", 0)) == 1
    except (ValueError, TypeError):
        return None


class TimedReviewDialog(QDialog):
    def __init__(self, mw: Any, cids: list[int]) -> None:
        super().__init__(mw)
        self.setWindowTitle("Speedrun — Timed Test Review")
        self.resize(640, 680)
        from aqt.speedrun_ui import DIALOG_QSS

        self.setStyleSheet(DIALOG_QSS)

        self.mw = mw
        self._wrong: list[int] = []
        answered = correct = 0
        blocks = []
        for cid in cids:
            try:
                card = mw.col.get_card(cid)
                note = card.note()
            except Exception:
                continue
            verdict = _was_correct(card)
            if verdict is not None:
                answered += 1
                if verdict:
                    correct += 1
            if verdict is not True:
                self._wrong.append(cid)
            badge = (
                "<span style='color:#2e7d32;font-weight:700'>&#10003; Correct</span>"
                if verdict
                else "<span style='color:#b3261e;font-weight:700'>&#10007; Incorrect</span>"
                if verdict is False
                else "<span style='color:#8a97a6'>Not answered</span>"
            )
            blocks.append(
                f"<div style='margin:0 0 16px;padding-bottom:14px;"
                f"border-bottom:1px solid #dfeafa'>"
                f"<div style='font-size:12px;color:#1e88e5;font-weight:700'>"
                f"{_fld(note, 'Contest')} {_fld(note, 'Year')} &middot; "
                f"Problem {_fld(note, 'Number')} &middot; {_fld(note, 'Topic')} &middot; {badge}</div>"
                f"<div style='margin:6px 0'>{_fld(note, 'Problem')}</div>"
                f"<div><b>Answer:</b> {_fld(note, 'Answer')}</div>"
                f"<div style='margin-top:6px;padding:10px;background:#eef5fd;"
                f"border-left:3px solid #1e88e5;border-radius:6px'>{_fld(note, 'Solution')}</div>"
                f"</div>"
            )

        pct = round(100 * correct / answered) if answered else 0
        header = (
            f"<div style='font-size:22px;font-weight:800;color:#102a43'>"
            f"Score: {correct} / {answered} &nbsp;({pct}%)</div>"
            f"<div style='color:#5a7184;margin:4px 0 16px'>"
            f"{len(cids)} questions in this session. Read the worked solutions below, "
            f"then rate the ones you missed to schedule them for review.</div>"
        )

        layout = QVBoxLayout(self)
        content = QLabel(header + "".join(blocks))
        content.setTextFormat(Qt.TextFormat.RichText)
        content.setWordWrap(True)
        content.setAlignment(Qt.AlignmentFlag.AlignTop)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.addWidget(content)
        hl.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        layout.addWidget(scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        qconnect(buttons.rejected, self.reject)
        if self._wrong:
            from aqt.qt import QPushButton

            drill = QPushButton(f"Review the {len(self._wrong)} I missed — rate them →")
            drill.setDefault(True)
            qconnect(drill.clicked, self._start_drill)
            buttons.addButton(drill, QDialogButtonBox.ButtonRole.AcceptRole)
        layout.addWidget(buttons)

    def _start_drill(self) -> None:
        # User-initiated (button click) → moveToState("review") is reliable here.
        self.accept()
        _start_mistake_drill()


def _open_review() -> None:
    mw = aqt.mw
    if mw is None or mw.col is None:
        return
    cids = _session(mw)
    if not cids:
        showInfo("No timed test has been run yet.", parent=mw)
        return
    TimedReviewDialog(mw, cids).show()


def _on_main_window_did_init() -> None:
    mw = aqt.mw
    if mw is None:
        return
    start = QAction("Speedrun: Timed Test", mw)
    qconnect(start.triggered, _start_timed_test)
    mw.form.menuTools.addAction(start)
    review = QAction("Speedrun: Timed Test Review", mw)
    qconnect(review.triggered, _open_review)
    mw.form.menuTools.addAction(review)


def _on_top_toolbar_init_links(links: list[str], toolbar: Any) -> None:
    links.append(
        toolbar.create_link(
            "speedrun_timed",
            "Timed Test",
            _start_timed_test,
            tip="20 questions, 40 minutes; review your misses after",
            id="speedrun_timed",
        )
    )
    links.append(
        toolbar.create_link(
            "speedrun_review",
            "Review",
            _open_review,
            tip="Review your last timed test: solutions + rate what you missed",
            id="speedrun_review",
        )
    )


def init() -> None:
    gui_hooks.main_window_did_init.append(_on_main_window_did_init)
    gui_hooks.top_toolbar_did_init_links.append(_on_top_toolbar_init_links)
    gui_hooks.card_will_show.append(_inject_timed)
    gui_hooks.reviewer_will_end.append(_on_reviewer_will_end)
