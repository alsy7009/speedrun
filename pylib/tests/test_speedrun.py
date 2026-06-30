# Copyright: Speedrun
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""End-to-end test for the Speedrun topic-aware interleaving queue (Rust change).

Builds a queue on a tagged deck with `topicInterleaving` enabled and asserts that
consecutive cards differ in topic, that answering + undo still work, and that the
collection passes an integrity check.
"""

from tests.shared import getEmptyCol

from anki.decks import DeckId


def _topic_of(col, card_id):
    note = col.get_note(col.get_card(card_id).nid)
    return next(
        (t.split("::", 1)[1] for t in note.tags if t.startswith("topic::")), ""
    )


def _queue_topics(col, limit=10):
    queued = col.sched.get_queued_cards(fetch_limit=limit)
    return [_topic_of(col, qc.card.id) for qc in queued.cards]


def test_topic_interleaving_end_to_end():
    col = getEmptyCol()

    # Enable topic interleaving on the default deck's config.
    conf = col.decks.config_dict_for_deck_id(1)
    conf["topicInterleaving"] = True
    col.decks.update_config(conf)

    # Blocked input: three "algebra" notes, then three "geometry" notes.
    model = col.models.by_name("Basic")
    tags = [
        "topic::algebra",
        "topic::algebra",
        "topic::algebra",
        "topic::geometry",
        "topic::geometry",
        "topic::geometry",
    ]
    for i, tag in enumerate(tags):
        note = col.new_note(model)
        note["Front"] = f"q{i}"
        note["Back"] = f"a{i}"
        note.tags = [tag]
        col.add_note(note, DeckId(1))

    # The built queue should interleave topics: no two adjacent the same.
    topics = _queue_topics(col)
    assert len(topics) == 6, topics
    dups = sum(1 for a, b in zip(topics, topics[1:]) if a == b)
    assert dups == 0, f"consecutive cards should differ in topic: {topics}"

    # Answering and undo must still work with interleaving enabled.
    card = col.sched.getCard()
    assert card is not None
    col.sched.answerCard(card, 3)
    col.undo()

    # Collection must remain consistent.
    assert col.db.scalar("pragma integrity_check") == "ok"
