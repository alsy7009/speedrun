# Copyright: Speedrun
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Speedrun timed test: a filtered deck of mixed problems on a 20-minute clock.

`build_timed_test` (re)builds the top-level **"Speedrun Timed Test"** filtered
deck with `questions` cards drawn at random from the due + unseen cards of all
Speedrun decks. Because it is a normal filtered deck with `reschedule=True`:

- it shows a due count in the deck list (Anki's due system is the motivation:
  the test is *due*, and answering feeds FSRS so revisits are scheduled), and
- reviews count toward history, the three scores, and topic-aware scheduling.

The 20:00 countdown itself lives in the card template (`speedrun/card_front.html`),
which shows it whenever the deck name contains "Timed Test" — so the same
mechanism works on desktop and on the phone with no app-specific timer code.
"""

from __future__ import annotations

from anki.collection import Collection
from anki.decks import DeckId

TIMED_DECK_NAME = "Speedrun Timed Test"
REVIEW_DECK_NAME = "Speedrun Review Mistakes"
DEFAULT_QUESTIONS = 20
# Search: any card under the Speedrun decks that is due or still unseen.
_SEARCH = '"deck:Speedrun::*" (is:due OR is:new)'


def _build_filtered(
    col: Collection,
    name: str,
    search: str,
    limit: int,
    order: int,
    reschedule: bool,
) -> DeckId:
    existing = col.decks.id_for_name(name)
    deck = col.sched.get_or_create_filtered_deck(DeckId(existing or 0))
    deck.name = name
    config = deck.config
    config.reschedule = reschedule
    del config.search_terms[:]
    term = config.search_terms.add()
    term.search = search
    term.limit = limit
    term.order = order
    changes = col.sched.add_or_update_filtered_deck(deck)
    return DeckId(changes.id)


def build_timed_test(
    col: Collection, questions: int = DEFAULT_QUESTIONS
) -> DeckId | None:
    """Phase 1: create/rebuild the timed-test filtered deck (random draw of due
    + unseen Speedrun cards). Returns the deck id, or None if none available.

    **One-shot / test-like:** `reschedule=False` (preview mode) — answering does
    not send cards to learning or re-queue them, and no "Learn" count appears.
    The student gets one attempt per question; real spaced-repetition happens in
    the post-test review (`build_review_deck`)."""
    if not col.find_cards(_SEARCH):
        return None
    # RANDOM = 1 (see decks.proto SearchTerm.Order)
    return _build_filtered(col, TIMED_DECK_NAME, _SEARCH, questions, 1, reschedule=False)


def build_review_deck(col: Collection, cids: list[int]) -> DeckId | None:
    """Phase 2: create/rebuild a filtered deck holding exactly `cids` (the cards
    missed in the test) for interactive, solution-shown re-practice. Returns the
    deck id, or None if `cids` is empty."""
    if not cids:
        return None
    search = "(" + " OR ".join(f"cid:{c}" for c in cids) + ")"
    # DUE = 6 keeps a stable order; limit covers all supplied cards. reschedule
    # is True here: the review IS the spaced-repetition step (ratings matter).
    return _build_filtered(col, REVIEW_DECK_NAME, search, len(cids), 6, reschedule=True)
