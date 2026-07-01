// Copyright: Speedrun
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Topic-aware interleaving of the review/new queue.
//!
//! Speedrun trains strategy discrimination by ensuring consecutive problems
//! require different approaches. We model "topic" as a note tag of the form
//! `topic::<name>` (e.g. `topic::geometry`) and reorder the *already gathered*
//! card vectors so that adjacent cards come from different topics where
//! possible. This only permutes the gathered `Vec`s — it never touches FSRS
//! memory state, due dates, intervals, or queue counts, so scheduling and undo
//! are unaffected.

use std::collections::HashMap;
use std::collections::VecDeque;

use crate::prelude::*;

/// Topic id used for cards whose note has no `topic::` tag.
pub(super) const NO_TOPIC: i64 = -1;

const TOPIC_PREFIX: &str = "topic::";

/// Build a `note_id -> topic id` map for the given notes by reading their tags.
///
/// Topic names are interned to small integers (first-seen order). Notes without
/// a `topic::` tag map to [`NO_TOPIC`].
pub(super) fn topic_ids_for_notes(
    col: &Collection,
    note_ids: &[NoteId],
) -> Result<HashMap<NoteId, i64>> {
    let rows = col.storage.get_note_tags_by_id_list(note_ids)?;
    let mut interned: HashMap<String, i64> = HashMap::new();
    let mut out: HashMap<NoteId, i64> = HashMap::with_capacity(rows.len());
    for row in rows {
        let id = match topic_from_tags(&row.tags) {
            Some(name) => {
                let next = interned.len() as i64;
                *interned.entry(name).or_insert(next)
            }
            None => NO_TOPIC,
        };
        out.insert(row.id, id);
    }
    Ok(out)
}

/// Extract the first `topic::<name>` tag from a space-separated tag string.
fn topic_from_tags(tags: &str) -> Option<String> {
    tags.split_whitespace()
        .find_map(|t| t.strip_prefix(TOPIC_PREFIX))
        .map(|name| name.to_ascii_lowercase())
}

/// Reorder `cards` so every topic is spread evenly across the queue and
/// consecutive entries differ in topic where possible.
///
/// Strategy ("least emitted fraction"): at each step emit a card from the topic
/// that has so far emitted the smallest fraction of its own cards, excluding the
/// topic just emitted. Concretely we pick the topic minimising
/// `(emitted + 0.5) / size`. This distributes each topic proportionally over the
/// whole ordering, so a minority topic with only one or two cards (e.g. a GRE
/// subject in a deck dominated by AMC problems) is guaranteed to appear early and
/// throughout rather than being clustered at the end — which a "largest bucket
/// first" greedy would do. Excluding the previous topic keeps adjacent cards
/// distinct, so it also minimises unavoidable adjacencies for a dominant topic.
///
/// Ties are broken by first-seen topic order, which keeps the result
/// deterministic and preserves each topic's internal order (cards are moved via
/// `pop_front`, never modified). Fractions are compared with integer
/// cross-multiplication to avoid floating point.
pub(super) fn interleave_by_topic<T>(cards: &mut Vec<T>, topic_of: impl Fn(&T) -> i64) {
    if cards.len() < 3 {
        return;
    }

    // Group into per-topic queues, preserving first-seen topic order and the
    // original within-topic order. `size` is the original count for that topic.
    let mut buckets: Vec<(i64, usize, VecDeque<T>)> = Vec::new();
    for card in std::mem::take(cards) {
        let topic = topic_of(&card);
        if let Some(slot) = buckets.iter_mut().find(|(t, _, _)| *t == topic) {
            slot.1 += 1;
            slot.2.push_back(card);
        } else {
            let mut queue = VecDeque::new();
            queue.push_back(card);
            buckets.push((topic, 1, queue));
        }
    }

    let total: usize = buckets.iter().map(|(_, _, q)| q.len()).sum();
    let mut out: Vec<T> = Vec::with_capacity(total);
    let mut last_topic: Option<i64> = None;

    for _ in 0..total {
        // Pick the non-empty bucket (topic != last) with the smallest emitted
        // fraction (emitted + 0.5) / size. Compare a<b as
        // (2*emitted_a + 1) * size_b < (2*emitted_b + 1) * size_a.
        let mut best: Option<usize> = None;
        for (i, (topic, size, queue)) in buckets.iter().enumerate() {
            if queue.is_empty() || Some(*topic) == last_topic {
                continue;
            }
            let emitted = size - queue.len();
            let is_better = match best {
                None => true,
                Some(b) => {
                    let (_, bsize, bqueue) = &buckets[b];
                    let bemitted = bsize - bqueue.len();
                    let lhs = (2 * emitted as i64 + 1) * *bsize as i64;
                    let rhs = (2 * bemitted as i64 + 1) * *size as i64;
                    // strict `<` keeps the earlier bucket on ties -> deterministic
                    lhs < rhs
                }
            };
            if is_better {
                best = Some(i);
            }
        }
        // If everything left shares the last topic, take the first non-empty bucket.
        let pick = best.unwrap_or_else(|| {
            buckets
                .iter()
                .position(|(_, _, q)| !q.is_empty())
                .expect("at least one non-empty bucket remains")
        });
        let card = buckets[pick]
            .2
            .pop_front()
            .expect("picked bucket is non-empty");
        last_topic = Some(buckets[pick].0);
        out.push(card);
    }

    *cards = out;
}

#[cfg(test)]
mod test {
    use super::*;

    fn interleaved(input: &[i64]) -> Vec<i64> {
        let mut cards = input.to_vec();
        interleave_by_topic(&mut cards, |c| *c);
        cards
    }

    fn adjacent_dups(v: &[i64]) -> usize {
        v.windows(2).filter(|w| w[0] == w[1]).count()
    }

    fn sorted(mut v: Vec<i64>) -> Vec<i64> {
        v.sort_unstable();
        v
    }

    #[test]
    fn separates_consecutive_when_balanced() {
        // Blocked input across 3 topics; interleaving should remove all adjacency.
        let out = interleaved(&[1, 1, 2, 2, 3, 3]);
        assert_eq!(
            adjacent_dups(&out),
            0,
            "no two adjacent cards should share a topic: {out:?}"
        );
        assert_eq!(sorted(out), vec![1, 1, 2, 2, 3, 3], "must be a permutation");
    }

    #[test]
    fn minimizes_adjacency_for_dominant_topic() {
        // Topic 1 is 4 of 6 cards, so exactly one adjacency is unavoidable.
        let out = interleaved(&[1, 1, 1, 1, 2, 3]);
        assert_eq!(out[0], 1, "dominant topic should lead");
        assert_eq!(
            adjacent_dups(&out),
            1,
            "only the unavoidable minimum adjacency should remain: {out:?}"
        );
        assert_eq!(sorted(out), vec![1, 1, 1, 1, 2, 3]);
    }

    #[test]
    fn handles_degenerate_cases() {
        // Single topic: order unchanged.
        let mut single = vec![7, 7, 7];
        interleave_by_topic(&mut single, |c| *c);
        assert_eq!(single, vec![7, 7, 7]);

        // Empty input.
        let mut empty: Vec<i64> = vec![];
        interleave_by_topic(&mut empty, |c| *c);
        assert!(empty.is_empty());

        // Fewer than three cards: left as-is.
        let mut two = vec![2, 1];
        interleave_by_topic(&mut two, |c| *c);
        assert_eq!(two, vec![2, 1]);
    }

    #[test]
    fn spreads_minority_topics_throughout() {
        // 20 cards of a dominant topic (0) plus three singleton minority topics
        // (1, 2, 3). The old "largest bucket first" greedy would emit all of
        // topic 0 first and push the singletons to the very end; the fraction
        // strategy must instead distribute them across the ordering so a
        // student sees the minority topics early.
        let mut input: Vec<i64> = std::iter::repeat(0).take(20).collect();
        input.extend([1, 2, 3]);
        let out = interleaved(&input);
        assert_eq!(sorted(out.clone()), sorted(input), "must be a permutation");

        let minority_positions: Vec<usize> = out
            .iter()
            .enumerate()
            .filter(|(_, &t)| t != 0)
            .map(|(i, _)| i)
            .collect();
        // Each singleton lands near the centre of its proportional slot, so all
        // three appear within the first ~two thirds, never bunched at the tail.
        for &p in &minority_positions {
            assert!(
                p < out.len() * 3 / 4,
                "minority topic at {p} should be spread, not clustered at the end: {out:?}"
            );
        }
        assert_eq!(minority_positions.len(), 3);
    }

    #[test]
    fn preserves_within_topic_order() {
        // (topic, original_seq) so we can verify per-topic stability.
        let mut cards = vec![(1i64, 0usize), (1, 1), (2, 2), (1, 3), (2, 4)];
        interleave_by_topic(&mut cards, |c| c.0);
        let topic1: Vec<usize> = cards.iter().filter(|c| c.0 == 1).map(|c| c.1).collect();
        let topic2: Vec<usize> = cards.iter().filter(|c| c.0 == 2).map(|c| c.1).collect();
        assert_eq!(
            topic1,
            vec![0, 1, 3],
            "within-topic order must be preserved"
        );
        assert_eq!(topic2, vec![2, 4]);
    }
}
