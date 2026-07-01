# Copyright: Speedrun
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Speedrun settings dialog: toggle FSRS + the topic-aware engine features.

Adds a "Speedrun" button to the top toolbar (and a Tools-menu entry) that opens a
dialog with checkboxes, so users can enable these without the debug console:

- Enable FSRS (required for topic-aware scheduling). Enabling also seeds default
  FSRS parameters into any preset that lacks them, so answering can't break.
- Interleave topics (mix problem types within a session).
- Topic-aware scheduling (bring weak topics back sooner).

The two topic toggles are applied to all deck presets.
"""

from __future__ import annotations

from typing import Any

import aqt
from anki.decks import DeckId
from aqt import gui_hooks
from aqt.qt import (
    QAction,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    qconnect,
)
from aqt.utils import tooltip

_DEFAULT_WEAK_FACTOR = 0.5


class SpeedrunSettingsDialog(QDialog):
    def __init__(self, mw: Any) -> None:
        super().__init__(mw)
        self.mw = mw
        self.setWindowTitle("Speedrun Settings")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        intro = QLabel("Enable Speedrun's learning-science features:")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.fsrs_check = QCheckBox("Enable FSRS (spaced-repetition memory model)")
        self.interleave_check = QCheckBox("Interleave topics — mix problem types within a session")
        self.scheduling_check = QCheckBox(
            "Topic-aware scheduling — bring weak topics back sooner"
        )
        for check in (self.fsrs_check, self.interleave_check, self.scheduling_check):
            layout.addWidget(check)

        note = QLabel(
            "Topic-aware scheduling needs FSRS on. The topic toggles apply to all "
            "deck presets. Cards are grouped by their <code>topic::…</code> tag."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#888; font-size:12px; margin-top:8px;")
        layout.addWidget(note)

        self._load_current()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        qconnect(buttons.accepted, self._save)
        qconnect(buttons.rejected, self.reject)
        layout.addWidget(buttons)

    def _load_current(self) -> None:
        col = self.mw.col
        self.fsrs_check.setChecked(bool(col.get_config("fsrs", False)))
        default_conf = col.decks.config_dict_for_deck_id(DeckId(1))
        self.interleave_check.setChecked(bool(default_conf.get("topicInterleaving", False)))
        self.scheduling_check.setChecked(bool(default_conf.get("topicScheduling", False)))

    def _save(self) -> None:
        col = self.mw.col
        enable_fsrs = self.fsrs_check.isChecked()
        interleave = self.interleave_check.isChecked()
        scheduling = self.scheduling_check.isChecked()

        # Default FSRS parameters, so enabling FSRS never leaves a preset with an
        # empty parameter set (which would break answering).
        default_params = list(
            col.decks.get_deck_configs_for_update(DeckId(1)).defaults.config.fsrs_params_6
        )

        for conf in col.decks.all_config():
            conf["topicInterleaving"] = interleave
            conf["topicScheduling"] = scheduling
            if "topicWeakIntervalFactor" not in conf:
                conf["topicWeakIntervalFactor"] = _DEFAULT_WEAK_FACTOR
            if enable_fsrs and not conf.get("fsrsParams6"):
                conf["fsrsParams6"] = default_params
            col.decks.update_config(conf)

        col.set_config("fsrs", enable_fsrs)

        self.mw.reset()
        tooltip("Speedrun settings saved.", parent=self.mw)
        self.accept()


def _open_settings() -> None:
    mw = aqt.mw
    if mw is not None and mw.col is not None:
        SpeedrunSettingsDialog(mw).exec()


def _on_main_window_did_init() -> None:
    mw = aqt.mw
    if mw is None:
        return
    action = QAction("Speedrun: Settings…", mw)
    qconnect(action.triggered, _open_settings)
    mw.form.menuTools.addAction(action)


def _on_top_toolbar_init_links(links: list[str], toolbar: Any) -> None:
    links.append(
        toolbar.create_link(
            "speedrun_settings",
            "Settings",
            _open_settings,
            tip="Enable FSRS and topic-aware features",
            id="speedrun_settings",
        )
    )


def _apply_defaults_once(col: Any) -> None:
    """Turn Speedrun's features on by default the first time a collection loads.

    Runs once (guarded by a config marker), so later manual changes in the
    Settings dialog are respected.
    """
    try:
        if col.get_config("speedrun_defaults_applied", False):
            return
        default_params = list(
            col.decks.get_deck_configs_for_update(DeckId(1)).defaults.config.fsrs_params_6
        )
        for conf in col.decks.all_config():
            conf["topicInterleaving"] = True
            conf["topicScheduling"] = True
            if "topicWeakIntervalFactor" not in conf:
                conf["topicWeakIntervalFactor"] = _DEFAULT_WEAK_FACTOR
            if not conf.get("fsrsParams6"):
                conf["fsrsParams6"] = default_params
            col.decks.update_config(conf)
        col.set_config("fsrs", True)
        col.set_config("speedrun_defaults_applied", True)
    except Exception as exc:  # never block collection load over defaults
        print(f"speedrun defaults error: {exc}")


def init() -> None:
    gui_hooks.main_window_did_init.append(_on_main_window_did_init)
    gui_hooks.top_toolbar_did_init_links.append(_on_top_toolbar_init_links)
    gui_hooks.collection_did_load.append(_apply_defaults_once)
