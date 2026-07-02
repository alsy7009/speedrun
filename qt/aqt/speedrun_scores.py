# Copyright: Speedrun
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Speedrun Scores dialog: Memory / Performance / Readiness, shown separately.

Adds a "Scores" button to the top toolbar (and a Tools-menu entry). The three
scores are computed by the shared Rust engine (``GetSpeedrunScores`` RPC, see
``rslib/src/stats/speedrun.rs`` and ``speedrun/SCORES.md``), so desktop and the
phone display identical numbers. Every score shows the full honesty contract:
point estimate, likely range, coverage, confidence, last-updated, reasons —
or an explicit abstain state naming exactly what data is still missing.
"""

from __future__ import annotations

import time
from typing import Any

import aqt
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

_CONFIDENCE_COLOR = {"low": "#c0392b", "medium": "#b7791f", "high": "#1e7e34"}


def _score_block(title: str, subtitle: str, score: Any, fmt: str) -> str:
    """One score as an HTML card. `fmt` is 'percent' or 'scaled'."""
    if not score.available:
        return (
            f"<div style='margin-bottom:18px'>"
            f"<div style='font-size:15px;font-weight:700'>{title}</div>"
            f"<div style='color:#888;font-size:12px;margin-bottom:6px'>{subtitle}</div>"
            f"<div style='color:#c0392b;font-weight:600'>No score yet.</div>"
            f"<div style='color:#555'>{score.abstain_reason}</div>"
            f"</div>"
        )
    if fmt == "percent":
        point = f"{score.point:.0f}%"
        rng = f"{score.range_low:.0f}% – {score.range_high:.0f}%"
    else:
        point = f"{score.point:.0f}"
        rng = f"{score.range_low:.0f} – {score.range_high:.0f}"
    color = _CONFIDENCE_COLOR.get(score.confidence, "#555")
    reasons = "".join(f"<li>{r}</li>" for r in score.reasons)
    return (
        f"<div style='margin-bottom:18px'>"
        f"<div style='font-size:15px;font-weight:700'>{title}</div>"
        f"<div style='color:#888;font-size:12px;margin-bottom:6px'>{subtitle}</div>"
        f"<div><span style='font-size:26px;font-weight:800'>{point}</span>"
        f"&nbsp;&nbsp;<span style='color:#555'>likely range {rng}</span></div>"
        f"<div>Confidence: <b style='color:{color}'>{score.confidence}</b></div>"
        f"<ul style='margin:6px 0 0 18px;color:#555'>{reasons}</ul>"
        f"</div>"
    )


class SpeedrunScoresDialog(QDialog):
    def __init__(self, mw: Any) -> None:
        super().__init__(mw)
        self.mw = mw
        self.setWindowTitle("Speedrun — Scores")
        self.resize(560, 620)
        from aqt.speedrun_ui import DIALOG_QSS

        self.setStyleSheet(DIALOG_QSS)

        scores = mw.col._backend.get_speedrun_scores()
        updated = time.strftime("%Y-%m-%d %H:%M", time.localtime(scores.last_updated))

        html = (
            f"<div style='color:#555;margin-bottom:14px'>"
            f"Exam coverage: <b>{scores.coverage_percent:.0f}%</b> of the GRE outline"
            f" &nbsp;·&nbsp; {scores.graded_reviews} graded reviews"
            f" &nbsp;·&nbsp; {scores.mc_first_attempts} first-try answers"
            f" &nbsp;·&nbsp; updated {updated}</div>"
            + _score_block(
                "Memory",
                "Chance you recall a taught fact right now (FSRS).",
                scores.memory,
                "percent",
            )
            + _score_block(
                "Performance",
                "Chance you get a new, exam-style question right.",
                scores.performance,
                "percent",
            )
            + _score_block(
                "Readiness",
                "Projected GRE Math score (200–990).",
                scores.readiness,
                "scaled",
            )
            + "<div style='color:#888;font-size:11px'>These are three separate "
            "estimates and are never blended. Give-up rules and formulas: "
            "speedrun/SCORES.md.</div>"
        )

        layout = QVBoxLayout(self)
        content = QLabel(html)
        content.setTextFormat(Qt.TextFormat.RichText)
        content.setWordWrap(True)
        content.setAlignment(Qt.AlignmentFlag.AlignTop)
        holder = QWidget()
        holder_layout = QVBoxLayout(holder)
        holder_layout.addWidget(content)
        holder_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        qconnect(buttons.rejected, self.reject)
        qconnect(buttons.accepted, self.accept)
        layout.addWidget(buttons)


def _open_scores() -> None:
    mw = aqt.mw
    if mw is not None and mw.col is not None:
        SpeedrunScoresDialog(mw).exec()


def _on_main_window_did_init() -> None:
    mw = aqt.mw
    if mw is None:
        return
    action = QAction("Speedrun: Scores…", mw)
    qconnect(action.triggered, _open_scores)
    mw.form.menuTools.addAction(action)


def _on_top_toolbar_init_links(links: list[str], toolbar: Any) -> None:
    links.append(
        toolbar.create_link(
            "speedrun_scores",
            "Scores",
            _open_scores,
            tip="Memory / Performance / Readiness",
            id="speedrun_scores",
        )
    )


def init() -> None:
    from aqt import gui_hooks

    gui_hooks.main_window_did_init.append(_on_main_window_did_init)
    gui_hooks.top_toolbar_did_init_links.append(_on_top_toolbar_init_links)
