# Copyright: Speedrun
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Keep the 'Speedrun MC' note type in sync with the repo's card sources.

CSS (`speedrun/card_theme.css`) and the front/back templates
(`speedrun/card_front.html`, `speedrun/card_back.html`) are the same files the
deck builder bakes into generated decks. On collection load we refresh the
note type from them, so existing decks pick up theme/template changes (e.g.
the timed-test countdown) without re-importing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aqt import gui_hooks

# repo_root/speedrun/  (this file is repo_root/qt/aqt/speedrun_theme.py)
_SRC = Path(__file__).resolve().parents[2] / "speedrun"
_NOTETYPE = "Speedrun MC"


def _apply_theme(col: Any) -> None:
    try:
        notetype = col.models.by_name(_NOTETYPE)
        if notetype is None:
            return
        changed = False
        css_path = _SRC / "card_theme.css"
        if css_path.exists():
            css = css_path.read_text()
            if notetype.get("css") != css:
                notetype["css"] = css
                changed = True
        front = _SRC / "card_front.html"
        back = _SRC / "card_back.html"
        if front.exists() and back.exists() and notetype.get("tmpls"):
            qfmt, afmt = front.read_text(), back.read_text()
            tmpl = notetype["tmpls"][0]
            if tmpl.get("qfmt") != qfmt or tmpl.get("afmt") != afmt:
                tmpl["qfmt"] = qfmt
                tmpl["afmt"] = afmt
                changed = True
        if changed:
            col.models.update_dict(notetype)
    except Exception as exc:  # never block collection load over theming
        print(f"speedrun theme error: {exc}")


def init() -> None:
    gui_hooks.collection_did_load.append(_apply_theme)
