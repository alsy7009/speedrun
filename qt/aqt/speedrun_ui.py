# Copyright: Speedrun
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Speedrun desktop skin.

Anki's desktop UI is a thin Qt shell around webviews, and every built-in page
(deck list, study screens, toolbars) is styled through CSS design tokens
(``--canvas``, ``--state-new``, ``--button-primary-bg``, ...). We rebrand the
whole app by overriding those tokens on every webview, plus targeted styling
for the top toolbar (blue gradient brand bar with pill buttons) and the deck
list (elevated card, count pills). The Speedrun MC cards themselves are themed
by ``speedrun/card_theme.css`` — this module makes the app around them match.

Registered from ``aqt/__init__.py`` at startup.
"""

from __future__ import annotations

from typing import Any

from aqt import gui_hooks

# Design tokens applied to every webview (light + night mode). This restyles
# all built-in pages at once, since they all consume these variables.
_BRAND_VARS = """
:root {
  --canvas: #edf3fa;
  --canvas-elevated: #ffffff;
  --canvas-overlay: #ffffff;
  --fg: #102a43;
  --fg-subtle: #5a7184;
  --fg-link: #1565c0;
  --border: #c9dcf0;
  --border-subtle: #dfeafa;
  --border-focus: #1e88e5;
  --button-primary-bg: #1976d2;
  --button-primary-gradient-start: #1e88e5;
  --button-primary-gradient-end: #1565c0;
  --state-new: #1e88e5;
  --state-learn: #ef6c00;
  --state-review: #2e7d32;
  --highlight-bg: rgba(30, 136, 229, 0.25);
  --border-radius: 8px;
  --border-radius-medium: 14px;
  --border-radius-large: 18px;
  --shadow: rgba(16, 42, 67, 0.14);
}
:root.night-mode {
  --canvas: #0f1b28;
  --canvas-elevated: #16283c;
  --canvas-overlay: #16283c;
  --fg: #e3f0fb;
  --fg-subtle: #8fb3d1;
  --fg-link: #64b5f6;
  --border: #23405c;
  --border-subtle: #1c3550;
  --border-focus: #42a5f5;
  --button-primary-bg: #1976d2;
  --button-primary-gradient-start: #1e88e5;
  --button-primary-gradient-end: #1565c0;
  --state-new: #64b5f6;
  --state-learn: #ffb74d;
  --state-review: #81c784;
  --highlight-bg: rgba(100, 181, 246, 0.3);
  --border-radius: 8px;
  --border-radius-medium: 14px;
  --border-radius-large: 18px;
}
body {
  font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
}
"""

# Brand bar: blue gradient, white pill links (Decks / Add / Browse / Stats /
# Sync + the Speedrun entries). Anki's "fancy" toolbar mode paints its own
# white/glass backgrounds on `.toolbar` and each `.hitem` — neutralize those,
# or the white link text would sit on a white container and disappear.
_TOOLBAR_CSS = """
body, body.fancy { margin: 0; }
.header {
  background: linear-gradient(90deg, #0d47a1 0%, #1565c0 45%, #1e88e5 100%);
  border-bottom: none !important;
  padding: 7px 12px;
  box-shadow: 0 2px 10px rgba(13, 71, 161, 0.35);
}
body.fancy .toolbar,
body.fancy:not(.flat) .toolbar {
  background: transparent !important;
  box-shadow: none !important;
  backdrop-filter: none !important;
  border-radius: 0 !important;
  overflow: visible !important;
}
.header .hitem,
body.fancy .hitem,
body.fancy:not(.flat) .hitem {
  background: transparent !important;
  border: 1px solid transparent !important;
  color: #ffffff !important;
  font-weight: 600;
  font-size: 13.5px;
  letter-spacing: 0.02em;
  text-decoration: none;
  padding: 6px 14px;
  margin: 0 2px;
  border-radius: 999px !important;
  transition: background 150ms ease, transform 150ms ease;
  box-shadow: none !important;
}
.header .hitem:hover,
body.fancy .hitem:hover,
body.fancy:not(.flat) .hitem:hover {
  background: rgba(255, 255, 255, 0.18) !important;
  border-color: transparent !important;
  text-decoration: none;
}
.header .hitem:active { transform: scale(0.97); }
#speedrun_scores, #speedrun_settings, #speedrun_amc_decks, #speedrun_timed,
#speedrun_review {
  background: rgba(255, 255, 255, 0.12) !important;
  border: 1px solid rgba(255, 255, 255, 0.4) !important;
}
#speedrun_scores:hover, #speedrun_settings:hover, #speedrun_amc_decks:hover,
#speedrun_timed:hover, #speedrun_review:hover {
  background: rgba(255, 255, 255, 0.28) !important;
}
/* Sync state colors must stay visible on the blue gradient. */
.normal-sync { color: #b3e5fc !important; }
.full-sync { color: #ffcdd2 !important; }
:root.night-mode .header {
  background: linear-gradient(90deg, #0a1f33 0%, #10395e 55%, #155a96 100%);
}
"""

# Deck list: elevated card container, roomier rows, count pills.
_DECKBROWSER_CSS = """
body { margin: 1.6em 1em 1em 1em; }
center > table {
  background: var(--canvas-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--border-radius-medium);
  box-shadow: 0 8px 28px rgba(16, 42, 67, 0.10), 0 1px 3px rgba(16, 42, 67, 0.08);
  padding: 1.1rem 1.4rem;
  border-top: 4px solid #1e88e5;
}
th {
  color: #1e88e5;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.09em;
  border-bottom: 1px solid var(--border-subtle);
  padding-bottom: 8px;
}
tr.deck td { padding: 7px 12px; border-bottom: 1px solid var(--border-subtle); }
a.deck { font-size: 15px; font-weight: 500; }
a.deck:hover { text-decoration: none; color: var(--fg-link); }
.current td, tr:hover:not(.top-level-drag-row) td { background: var(--canvas); }
.new-count, .learn-count, .review-count, .zero-count {
  display: inline-block;
  min-width: 2.1em;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 700;
  text-align: center;
}
.new-count    { background: rgba(30, 136, 229, 0.14); }
.learn-count  { background: rgba(239, 108, 0, 0.14); }
.review-count { background: rgba(46, 125, 50, 0.14); }
.zero-count   { background: transparent; }
#studiedToday { color: var(--fg-subtle); font-size: 13px; }
:root.night-mode center > table {
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.45);
}
"""

# Study overview + congrats + reviewer chrome inherit the brand tokens; give
# the primary study button a little extra presence.
_OVERVIEW_CSS = """
button, .btn {
  border-radius: 999px !important;
  font-weight: 600;
}
"""

_BOTTOMBAR_CSS = """
body, #outer {
  background: var(--canvas-elevated) !important;
  border-top: 1px solid var(--border-subtle) !important;
}
button {
  border-radius: 999px !important;
  font-weight: 600;
  padding: 4px 16px;
}
"""

# Shared stylesheet for the Speedrun Qt dialogs (Scores / Settings / Decks).
DIALOG_QSS = """
QDialog { background: #f4f8fd; }
QLabel { color: #102a43; }
QPushButton {
  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e88e5, stop:1 #1565c0);
  color: white;
  font-weight: 600;
  border: none;
  border-radius: 14px;
  padding: 7px 18px;
}
QPushButton:hover { background: #1976d2; }
QPushButton:pressed { background: #1257a5; }
QCheckBox { color: #102a43; spacing: 8px; }
QScrollArea { border: none; background: transparent; }
"""


def _inject(web_content: Any, context: Any) -> None:
    web_content.head += f"<style>{_BRAND_VARS}</style>"
    name = type(context).__name__ if context is not None else ""
    if name == "TopToolbar":
        web_content.head += f"<style>{_TOOLBAR_CSS}</style>"
    elif name == "DeckBrowser":
        web_content.head += f"<style>{_DECKBROWSER_CSS}</style>"
    elif name == "Overview":
        web_content.head += f"<style>{_OVERVIEW_CSS}</style>"
    elif name == "BottomToolbar":
        web_content.head += f"<style>{_BOTTOMBAR_CSS}</style>"


def init() -> None:
    gui_hooks.webview_will_set_content.append(_inject)
