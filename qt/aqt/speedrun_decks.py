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


class AmcDeckDialog(QDialog):
    def __init__(self, mw: Any) -> None:
        super().__init__(mw)
        self.mw = mw
        self.setWindowTitle("Speedrun — Add Decks")
        self.resize(560, 520)
        self._checks: dict[str, QCheckBox] = {}

        manifest = _load_manifest()
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Add Speedrun decks. The <b>Mixed</b> sets are the main practice: each "
            "blends one AMC tier with GRE problems and guarantees GRE topics "
            "(calculus, linear/abstract algebra, analysis, …) appear in every "
            "session, interleaved so consecutive cards use different strategies. "
            "The <b>AMC 8/10/12</b> and <b>GRE</b> sets are dedicated single-source "
            "decks for targeted, blocked practice."
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
            name = deck.get("label", deck["tier"])
            label = (
                f"<b>{name}</b>{' ★' if deck.get('starter') else ''}"
                f" — {deck['problem_count']} problems · {deck.get('deck_count', 0)} decks"
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

        starter_btn = QPushButton("Add all Mixed sets (recommended)")
        qconnect(starter_btn.clicked, self._add_starter)
        layout.addWidget(starter_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
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


def _open_dialog() -> None:
    mw = aqt.mw
    if mw is not None:
        AmcDeckDialog(mw).exec()


def _on_main_window_did_init() -> None:
    mw = aqt.mw
    if mw is None:
        return
    action = QAction("Speedrun: Add Decks…", mw)
    qconnect(action.triggered, _open_dialog)
    mw.form.menuTools.addAction(action)


def _on_top_toolbar_init_links(links: list[str], toolbar: Any) -> None:
    """Add a 'Decks' button to the top toolbar (Decks / Add / Browse / ...)."""
    links.append(
        toolbar.create_link(
            "speedrun_amc_decks",
            "Speedrun Decks",
            _open_dialog,
            tip="Add Speedrun decks (Mixed, AMC, GRE)",
            id="speedrun_amc_decks",
        )
    )


def _import_starters_once(col: Any) -> None:
    """Auto-import starter decks (the Mixed sets) the first time each is seen,
    mirroring the Android app. Tracks imported deck codes individually so newly
    added starters import without re-importing/duplicating the ones already
    present. Later manual removals are respected.
    """
    try:
        manifest = _load_manifest()
        if not manifest:
            return
        imported = set(col.get_config("speedrun_imported_deck_codes", None) or [])
        # Migrate the old single-boolean marker: the 3 AMC tiers were imported.
        if not imported and col.get_config("speedrun_tier_decks_imported", False):
            imported = {"AMC_8", "AMC_10", "AMC_12"}
        newly = []
        for deck in manifest.get("decks", []):
            code = deck.get("code")
            if not deck.get("starter") or code in imported:
                continue
            path = DECKS_DIR / deck["file"]
            if not path.exists():
                continue
            col.import_anki_package(
                import_export_pb2.ImportAnkiPackageRequest(
                    package_path=str(path),
                    options=import_export_pb2.ImportAnkiPackageOptions(
                        merge_notetypes=True,
                        with_scheduling=False,
                        with_deck_configs=False,
                    ),
                )
            )
            newly.append(code)
        if newly:
            col.set_config(
                "speedrun_imported_deck_codes", sorted(imported | set(newly))
            )
    except Exception as exc:  # never block collection load over deck seeding
        print(f"speedrun tier deck import error: {exc}")


def init() -> None:
    gui_hooks.main_window_did_init.append(_on_main_window_did_init)
    gui_hooks.top_toolbar_did_init_links.append(_on_top_toolbar_init_links)
    gui_hooks.collection_did_load.append(_import_starters_once)
