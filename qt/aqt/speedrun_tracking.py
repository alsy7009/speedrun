# Copyright: Speedrun
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Persist Speedrun multiple-choice attempts to ``card.custom_data``.

The Speedrun MC card template posts a message ``speedrun:attempt:<correct>:<letter>``
when the answer side is shown (``<correct>`` is ``1``/``0``, or empty if the student
revealed the answer without picking). We record a compact aggregate on the card's
``custom_data`` JSON, which is part of the collection and therefore syncs to the
phone. This signal feeds the Performance/Readiness scores (see speedrun/SCORES.md).

Anki enforces custom_data keys <= 8 bytes and <= 100 bytes serialized, so we keep
one small object instead of a per-attempt log::

    {"sr": {"n": attempts, "k": correct, "f": first_attempt_correct, "t": last_ts}}

Registered from ``aqt/__init__.py`` at startup; it is a no-op for any other card
type or message.
"""

from __future__ import annotations

import json
import time
from typing import Any

import aqt
from aqt import gui_hooks

_PREFIX = "speedrun:attempt:"


def _record_attempt(message: str) -> None:
    payload = message[len(_PREFIX):]
    correct_str, _, _letter = payload.partition(":")
    if correct_str == "":
        return  # answer revealed without a selection; nothing to record
    correct = int(correct_str)

    mw = aqt.mw
    if mw is None or mw.reviewer is None or mw.reviewer.card is None or mw.col is None:
        return
    card = mw.reviewer.card

    try:
        data = json.loads(card.custom_data) if card.custom_data else {}
    except (ValueError, TypeError):
        data = {}

    stats = data.get("sr") or {}
    first_attempt = not stats
    data["sr"] = {
        "n": int(stats.get("n", 0)) + 1,
        "k": int(stats.get("k", 0)) + correct,
        "f": correct if first_attempt else int(stats.get("f", 0)),
        "t": int(time.time()),
    }
    card.custom_data = json.dumps(data, separators=(",", ":"))
    mw.col.update_card(card)


def _on_js_message(
    handled: tuple[bool, Any], message: str, context: Any
) -> tuple[bool, Any]:
    if not message.startswith(_PREFIX):
        return handled
    try:
        _record_attempt(message)
    except Exception as exc:  # never break the reviewer over telemetry
        print(f"speedrun tracking error: {exc}")
    return (True, None)


def init() -> None:
    gui_hooks.webview_did_receive_js_message.append(_on_js_message)
