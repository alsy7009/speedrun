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
# the filtered deck as they're answered).
_session_cids: list[int] = []
_session_active = False

# Self-contained countdown banner (inline-styled; no template/CSS dependency).
_TIMER_WIDGET = """
<div id="sr-timed-banner" style="display:inline-block;font:700 13px -apple-system,
'Segoe UI',Roboto,sans-serif;letter-spacing:.04em;color:#0d47a1;background:#e3f0fb;
border:1px solid #b7d6f4;border-radius:999px;padding:6px 15px;margin-bottom:14px;"></div>
<script>
(function () {
  var el = document.getElementById("sr-timed-banner");
  if (!el) return;
  var KEY = "sr_timed_start", LIMIT = 40 * 60 * 1000, STALE = 60 * 60 * 1000;
  var start = 0;
  try { start = Number(sessionStorage.getItem(KEY) || 0); } catch (e) {}
  var now = Date.now();
  if (!start || now - start > STALE) {
    start = now;
    try { sessionStorage.setItem(KEY, String(start)); } catch (e) {}
  }
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
    answer side so it isn't revealed mid-test."""
    if not _in_timed_deck(card):
        return text
    out = _TIMER_WIDGET + text
    if kind in ("reviewAnswer", "clayoutAnswer"):
        out += _HIDE_SOLUTION
    return out


def _start_timed_test() -> None:
    global _session_cids, _session_active
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
    _session_active = True
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
    for cid in _session_cids:
        try:
            card = mw.col.get_card(cid)
        except Exception:
            continue
        if _was_correct(card) is not True:
            out.append(cid)
    return out


def _on_reviewer_will_end() -> None:
    """Phase 1 finished: gather the misses and launch interactive drill (Phase 2)."""
    global _session_active
    if not _session_active:
        return
    _session_active = False
    mw = aqt.mw
    if mw is None or mw.col is None or not _session_cids:
        return
    # Defer so the current reviewer finishes tearing down first.
    from aqt.qt import QTimer

    QTimer.singleShot(150, _start_mistake_drill)


def _start_mistake_drill() -> None:
    mw = aqt.mw
    if mw is None or mw.col is None:
        return
    total = len(_session_cids)
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
    mw.moveToState("overview")
    tooltip(
        f"Test complete: {correct}/{total} correct. Now drill the {len(wrong)} "
        "you missed — solutions shown.",
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
            f"{len(cids)} questions in this session. Review the worked solutions below.</div>"
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
        layout.addWidget(buttons)


def _open_review() -> None:
    mw = aqt.mw
    if mw is None or mw.col is None:
        return
    if not _session_cids:
        showInfo("No timed test has been run yet this session.", parent=mw)
        return
    TimedReviewDialog(mw, list(_session_cids)).show()


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
            tip="10 questions, 20 minutes, solutions at the end",
            id="speedrun_timed",
        )
    )


def init() -> None:
    gui_hooks.main_window_did_init.append(_on_main_window_did_init)
    gui_hooks.top_toolbar_did_init_links.append(_on_top_toolbar_init_links)
    gui_hooks.card_will_show.append(_inject_timed)
    gui_hooks.reviewer_will_end.append(_on_reviewer_will_end)
