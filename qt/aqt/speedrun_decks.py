# Copyright: Speedrun
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""In-app picker for adding Speedrun AMC decks.

Adds a "Speedrun: Add AMC Decks…" entry to the Tools menu. The dialog lists the
contests described by ``speedrun/decks/manifest.json`` (produced by
``speedrun/build_all_decks.py``) and imports the chosen ``.apkg`` files into the
current collection. A one-click "Add starter set" imports a small recommended
subset.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aqt
from anki import import_export_pb2
from aqt import gui_hooks
from aqt.qt import (
    QAction,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    Qt,
    QVBoxLayout,
    QWidget,
    qconnect,
)
from aqt.utils import showInfo, tooltip

# repo_root/speedrun/decks  (this file is repo_root/qt/aqt/speedrun_decks.py)
DECKS_DIR = Path(__file__).resolve().parents[2] / "speedrun" / "decks"
MANIFEST = DECKS_DIR / "manifest.json"

_TOPIC_ABBR = {
    "algebra": "alg",
    "geometry": "geo",
    "number_theory": "num",
    "combinatorics": "comb",
}


def _load_manifest() -> dict[str, Any] | None:
    if not MANIFEST.exists():
        return None
    try:
        return json.loads(MANIFEST.read_text())
    except (ValueError, OSError):
        return None


def _topic_summary(topics: dict[str, int]) -> str:
    parts = [
        f"{_TOPIC_ABBR.get(name, name)} {count}"
        for name, count in sorted(topics.items(), key=lambda kv: -kv[1])
    ]
    return " · ".join(parts)


def _years_label(deck: dict[str, Any]) -> str:
    years = [str(y) for y in deck.get("years", [])]
    if not years:
        return ""
    return f"{years[0]}–{years[-1]}" if len(years) > 1 else years[0]


class AmcDeckDialog(QDialog):
    def __init__(self, mw: Any) -> None:
        super().__init__(mw)
        self.mw = mw
        self.setWindowTitle("Speedrun — Add AMC Decks")
        self.resize(560, 520)
        self._checks: dict[str, QCheckBox] = {}

        manifest = _load_manifest()
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Choose AMC competition decks to add. Problems are interleaved across "
            "topics (algebra / geometry / number theory / combinatorics)."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        if not manifest or not manifest.get("decks"):
            warn = QLabel(
                "No generated decks found.\n\nRun:\n"
                '  PYTHONPATH="pylib:out/pylib" out/pyenv/bin/python '
                "speedrun/build_all_decks.py --harp speedrun/out/harp/HARP_mcq.jsonl"
            )
            warn.setWordWrap(True)
            layout.addWidget(warn)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            qconnect(buttons.rejected, self.reject)
            layout.addWidget(buttons)
            return

        self._decks = {d["code"]: d for d in manifest["decks"]}

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        col = QVBoxLayout(container)
        for deck in manifest["decks"]:
            available = (DECKS_DIR / deck["file"]).exists()
            label = (
                f"<b>{deck['contest']}</b>{' ★' if deck.get('starter') else ''}"
                f" — {deck['problem_count']} problems · {_years_label(deck)}"
                f"<br><span style='color:#888'>{_topic_summary(deck.get('topics', {}))}</span>"
            )
            if not available:
                label += " <span style='color:#c0392b'>(file missing)</span>"
            check = QCheckBox()
            check.setEnabled(available)
            if deck.get("starter") and available:
                check.setChecked(True)
            text = QLabel(label)
            text.setTextFormat(Qt.TextFormat.RichText)
            text.setWordWrap(True)
            holder = QWidget()
            row = QHBoxLayout(holder)
            row.setContentsMargins(0, 4, 0, 4)
            row.addWidget(check)
            row.addWidget(text, 1)
            col.addWidget(holder)
            self._checks[deck["code"]] = check

        col.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)

        starter_btn = QPushButton("Add starter set (AMC 8, 10A, 12A)")
        qconnect(starter_btn.clicked, self._add_starter)
        layout.addWidget(starter_btn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close
        )
        add_btn = QPushButton("Add selected")
        add_btn.setDefault(True)
        qconnect(add_btn.clicked, self._add_selected)
        buttons.addButton(add_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        qconnect(buttons.rejected, self.reject)
        layout.addWidget(buttons)

    def _add_starter(self) -> None:
        codes = [c for c, d in self._decks.items() if d.get("starter")]
        self._import(codes)

    def _add_selected(self) -> None:
        codes = [c for c, chk in self._checks.items() if chk.isChecked()]
        if not codes:
            showInfo("No decks selected.", parent=self)
            return
        self._import(codes)

    def _import(self, codes: list[str]) -> None:
        codes = [c for c in codes if (DECKS_DIR / self._decks[c]["file"]).exists()]
        if not codes:
            showInfo("Selected decks are not available.", parent=self)
            return

        self.mw.progress.start(parent=self, label="Adding Speedrun decks…")
        added = 0
        try:
            for code in codes:
                path = DECKS_DIR / self._decks[code]["file"]
                request = import_export_pb2.ImportAnkiPackageRequest(
                    package_path=str(path),
                    options=import_export_pb2.ImportAnkiPackageOptions(
                        merge_notetypes=True,
                        with_scheduling=False,
                        with_deck_configs=False,
                    ),
                )
                self.mw.col.import_anki_package(request)
                added += 1
        finally:
            self.mw.progress.finish()

        self.mw.reset()
        tooltip(f"Added {added} Speedrun deck(s).", parent=self.mw)
        self.accept()


def _on_main_window_did_init() -> None:
    mw = aqt.mw
    if mw is None:
        return
    action = QAction("Speedrun: Add AMC Decks…", mw)
    qconnect(action.triggered, lambda: AmcDeckDialog(mw).exec())
    mw.form.menuTools.addAction(action)


def init() -> None:
    gui_hooks.main_window_did_init.append(_on_main_window_did_init)
