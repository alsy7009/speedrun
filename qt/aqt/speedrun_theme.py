# Copyright: Speedrun
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Keep the 'Speedrun MC' note type styled with the Speedrun blue theme.

The card CSS lives in `speedrun/card_theme.css` (the same file the deck builder
bakes into generated decks). On collection load we refresh the note type's CSS
from that file, so existing decks pick up theme changes without re-importing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aqt import gui_hooks

# repo_root/speedrun/card_theme.css  (this file is repo_root/qt/aqt/speedrun_theme.py)
_CSS_PATH = Path(__file__).resolve().parents[2] / "speedrun" / "card_theme.css"
_NOTETYPE = "Speedrun MC"


def _apply_theme(col: Any) -> None:
    try:
        if not _CSS_PATH.exists():
            return
        notetype = col.models.by_name(_NOTETYPE)
        if notetype is None:
            return
        css = _CSS_PATH.read_text()
        if notetype.get("css") != css:
            notetype["css"] = css
            col.models.update_dict(notetype)
    except Exception as exc:  # never block collection load over theming
        print(f"speedrun theme error: {exc}")


def init() -> None:
    gui_hooks.collection_did_load.append(_apply_theme)
