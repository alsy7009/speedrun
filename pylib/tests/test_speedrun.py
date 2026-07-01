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


def test_speedrun_scores_abstain_then_show():
    """The three-scores RPC abstains without data, and Memory appears once the
    give-up line is crossed. Readiness must state exactly what is missing."""
    import json

    col = getEmptyCol()

    # Empty collection: every score abstains with a concrete reason.
    scores = col._backend.get_speedrun_scores()
    assert not scores.memory.available
    assert "20 graded reviews" in scores.memory.abstain_reason
    assert not scores.performance.available
    assert not scores.readiness.available
    assert "more graded reviews" in scores.readiness.abstain_reason

    # Add and review topic-tagged cards with FSRS on (so memory state exists).
    col.set_config("fsrs", True)
    model = col.models.by_name("Basic")
    for i in range(25):
        note = col.new_note(model)
        note["Front"] = f"q{i}"
        note["Back"] = f"a{i}"
        note.tags = ["topic::calculus" if i % 2 else "topic::algebra"]
        col.add_note(note, DeckId(1))
    for _ in range(25):
        card = col.sched.getCard()
        if card is None:
            break
        col.sched.answerCard(card, 3)

    # Record a first MC attempt on one card (compact custom_data aggregate).
    card = col.sched.getCard() or col.get_card(
        col.find_cards("")[0]
    )
    card.custom_data = json.dumps({"sr": {"n": 1, "k": 1, "f": 1, "t": 0}})
    col.update_card(card)

    scores = col._backend.get_speedrun_scores()
    assert scores.graded_reviews >= 20
    assert scores.mc_first_attempts == 1
    # Memory is past its give-up line and must carry the full contract.
    assert scores.memory.available
    assert 0.0 <= scores.memory.range_low <= scores.memory.point <= scores.memory.range_high <= 100.0
    assert scores.memory.confidence in ("low", "medium", "high")
    assert scores.memory.reasons
    # Performance/Readiness still lack attempts/coverage and must abstain.
    assert not scores.performance.available
    assert not scores.readiness.available
    assert scores.last_updated > 0
    # Coverage reflects the two studied topics (algebra .10 + calculus .25).
    assert abs(scores.coverage_percent - 35.0) < 0.01

    # Collection must remain consistent after the read-only query.
    assert col.db.scalar("pragma integrity_check") == "ok"
