// Copyright: Speedrun
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! The three Speedrun study scores: Memory, Performance, Readiness.
//!
//! Kept strictly separate (never blended into one number) and each shipped
//! with the full honesty contract: point estimate, likely range, coverage,
//! confidence, reasons, and an explicit abstain ("give-up") state. Formulas
//! and give-up rules are documented in `speedrun/SCORES.md`. Living in the
//! shared engine means desktop and the phone display identical numbers.

use std::collections::HashMap;

use anki_proto::stats::SpeedrunScore;
use anki_proto::stats::SpeedrunScores;
use fsrs::FSRS;
use fsrs::FSRS5_DEFAULT_DECAY;

use crate::prelude::*;
use crate::storage::card::data::CardData;

/// Chance of guessing a 5-choice MC question.
const GUESS_RATE: f32 = 0.2;
/// Shrinkage pseudo-count toward the guess rate for per-topic MC accuracy.
const SHRINK_K: f32 = 4.0;
const Z_95: f32 = 1.96;

// Give-up rules (see speedrun/SCORES.md).
const MEMORY_MIN_GRADED: u32 = 20;
const PERFORMANCE_MIN_ATTEMPTS: u32 = 30;
const PERFORMANCE_MIN_TOPICS: usize = 3;
const READINESS_MIN_GRADED: u32 = 200;
const READINESS_MIN_COVERAGE: f32 = 50.0;

/// GRE Math Subject outline weights per `topic::` tag (sums to 1.0).
/// Mirrors speedrun/gre_topics.json — keep in sync.
const TOPIC_WEIGHTS: &[(&str, f32)] = &[
    ("calculus", 0.25),
    ("multivariable_calculus", 0.10),
    ("sequences_series", 0.10),
    ("differential_equations", 0.05),
    ("algebra", 0.10),
    ("linear_algebra", 0.075),
    ("abstract_algebra", 0.05),
    ("number_theory", 0.025),
    ("real_analysis", 0.075),
    ("probability", 0.075),
    ("combinatorics", 0.05),
    ("geometry", 0.03),
    ("complex_analysis", 0.02),
];

/// Piecewise-linear map from expected fraction correct to the 200-990 scale.
/// ETS publishes no raw->scaled table; these anchors approximate the generous
/// curve implied by public percentile data (documented assumption).
const SCALE_ANCHORS: &[(f32, f32)] = &[
    (0.0, 200.0),
    (0.25, 500.0),
    (0.5, 680.0),
    (0.85, 900.0),
    (1.0, 990.0),
];

#[derive(Default)]
struct TopicAgg {
    studied_cards: u32,
    retrievability_sum: f64,
    retrievability_count: u32,
    first_attempts: u32,
    first_correct: u32,
}

/// Per-topic MC accuracy, shrunk toward the guess rate so tiny samples stay
/// honest. With zero attempts this is exactly the guess rate.
fn shrunk_accuracy(correct: u32, attempts: u32) -> f32 {
    (correct as f32 + SHRINK_K * GUESS_RATE) / (attempts as f32 + SHRINK_K)
}

/// Binomial-style standard error matching the shrunk estimate's denominator.
fn shrunk_se(correct: u32, attempts: u32) -> f32 {
    let p = shrunk_accuracy(correct, attempts);
    (p * (1.0 - p) / (attempts as f32 + SHRINK_K)).sqrt()
}

/// Map expected fraction correct to the 200-990 scale, rounded to nearest 10.
fn readiness_scaled(p: f32) -> f32 {
    let p = p.clamp(0.0, 1.0);
    let mut result = SCALE_ANCHORS[0].1;
    for pair in SCALE_ANCHORS.windows(2) {
        let ((x0, y0), (x1, y1)) = (pair[0], pair[1]);
        if p <= x1 {
            result = y0 + (p - x0) / (x1 - x0) * (y1 - y0);
            break;
        }
        result = y1;
    }
    (result / 10.0).round() * 10.0
}

fn topic_from_tags(tags: &str) -> Option<String> {
    tags.split_whitespace()
        .find_map(|t| t.strip_prefix("topic::"))
        .map(|name| name.to_ascii_lowercase())
}

/// First MC attempt outcome from a card's custom_data JSON. The MC tracking
/// hook stores a compact aggregate `{"sr": {"n": attempts, "k": correct,
/// "f": first_correct, "t": ts}}` (custom_data is limited to 100 bytes).
/// Only the first attempt counts toward Performance: it is the one where the
/// question was genuinely new.
fn first_attempt(custom_data: &str) -> Option<bool> {
    let value: serde_json::Value = serde_json::from_str(custom_data).ok()?;
    let sr = value.get("sr")?;
    // Require at least one recorded attempt.
    if sr.get("n")?.as_i64()? < 1 {
        return None;
    }
    Some(sr.get("f")?.as_i64()? == 1)
}

fn abstained(reason: String) -> SpeedrunScore {
    SpeedrunScore {
        available: false,
        abstain_reason: reason,
        ..Default::default()
    }
}

fn pct(p: f32) -> f32 {
    (p * 1000.0).round() / 10.0
}

impl Collection {
    pub fn speedrun_scores(&mut self) -> Result<SpeedrunScores> {
        let rows = self.storage.speedrun_card_rows()?;
        let last_review_times = self.storage.speedrun_last_review_times()?;
        let graded_reviews = self.storage.speedrun_graded_review_count()?;
        let now = self.timing_today()?.now;
        let fsrs = FSRS::new(None)?;

        let mut topics: HashMap<&'static str, TopicAgg> = HashMap::new();
        let mut all_retrievability: Vec<f32> = Vec::new();
        let mut mc_first_attempts = 0u32;

        for (card_id, ctype, tags, data_str) in &rows {
            let topic = topic_from_tags(tags);
            let topic_name: Option<&'static str> = topic.as_deref().and_then(|t| {
                TOPIC_WEIGHTS
                    .iter()
                    .find(|(name, _)| *name == t)
                    .map(|(name, _)| *name)
            });
            let data = CardData::from_str(data_str);

            if *ctype != 0 {
                if let Some(t) = topic_name {
                    topics.entry(t).or_default().studied_cards += 1;
                }
            }

            // FSRS retrievability right now (Memory).
            if let Some(state) = data.memory_state() {
                let last = data
                    .last_review_time
                    .or_else(|| last_review_times.get(card_id).copied());
                if let Some(last) = last {
                    let seconds = now.elapsed_secs_since(last).max(0) as u32;
                    let r = fsrs.current_retrievability_seconds(
                        state.into(),
                        seconds,
                        data.decay.unwrap_or(FSRS5_DEFAULT_DECAY),
                    );
                    all_retrievability.push(r);
                    if let Some(t) = topic_name {
                        let entry = topics.entry(t).or_default();
                        entry.retrievability_sum += r as f64;
                        entry.retrievability_count += 1;
                    }
                }
            }

            // First MC attempt (Performance).
            if !data.custom_data.is_empty() {
                if let Some(correct) = first_attempt(&data.custom_data) {
                    mc_first_attempts += 1;
                    if let Some(t) = topic_name {
                        let entry = topics.entry(t).or_default();
                        entry.first_attempts += 1;
                        if correct {
                            entry.first_correct += 1;
                        }
                    }
                }
            }
        }

        let coverage_percent: f32 = TOPIC_WEIGHTS
            .iter()
            .filter(|(name, _)| {
                topics
                    .get(name)
                    .map(|a| a.studied_cards > 0)
                    .unwrap_or(false)
            })
            .map(|(_, w)| w)
            .sum::<f32>()
            * 100.0;

        let memory = memory_score(&all_retrievability, &topics, graded_reviews);
        let performance = performance_score(&topics, mc_first_attempts);
        let readiness =
            readiness_score(&performance, &topics, graded_reviews, coverage_percent);

        Ok(SpeedrunScores {
            memory: Some(memory),
            performance: Some(performance),
            readiness: Some(readiness),
            coverage_percent,
            graded_reviews,
            mc_first_attempts,
            last_updated: TimestampSecs::now().0,
        })
    }
}

fn memory_score(
    retrievability: &[f32],
    topics: &HashMap<&'static str, TopicAgg>,
    graded_reviews: u32,
) -> SpeedrunScore {
    if graded_reviews < MEMORY_MIN_GRADED {
        return abstained(format!(
            "Not enough reviews yet: need {MEMORY_MIN_GRADED} graded reviews, have {graded_reviews}."
        ));
    }
    if retrievability.is_empty() {
        return abstained("No cards with FSRS memory state yet (enable FSRS and review some cards).".into());
    }
    let n = retrievability.len() as f32;
    let mean = retrievability.iter().sum::<f32>() / n;
    let var = retrievability
        .iter()
        .map(|r| (r - mean).powi(2))
        .sum::<f32>()
        / n.max(1.0);
    let half = Z_95 * (var / n).sqrt();

    // Weakest topics by mean retrievability.
    let mut topic_means: Vec<(&str, f32)> = topics
        .iter()
        .filter(|(_, a)| a.retrievability_count > 0)
        .map(|(name, a)| {
            (
                *name,
                (a.retrievability_sum / a.retrievability_count as f64) as f32,
            )
        })
        .collect();
    topic_means.sort_by(|a, b| a.1.total_cmp(&b.1));
    let mut reasons: Vec<String> = topic_means
        .iter()
        .take(2)
        .map(|(name, r)| format!("Weakest recall: {} ({:.0}%)", name.replace('_', " "), r * 100.0))
        .collect();
    reasons.push(format!(
        "Based on FSRS retrievability over {} studied cards.",
        retrievability.len()
    ));

    let confidence = if graded_reviews >= 500 {
        "high"
    } else if graded_reviews >= 100 {
        "medium"
    } else {
        "low"
    };

    SpeedrunScore {
        available: true,
        abstain_reason: String::new(),
        point: pct(mean),
        range_low: pct((mean - half).clamp(0.0, 1.0)),
        range_high: pct((mean + half).clamp(0.0, 1.0)),
        confidence: confidence.into(),
        reasons,
    }
}

fn performance_score(
    topics: &HashMap<&'static str, TopicAgg>,
    mc_first_attempts: u32,
) -> SpeedrunScore {
    let attempted_topics = topics.values().filter(|a| a.first_attempts > 0).count();
    if mc_first_attempts < PERFORMANCE_MIN_ATTEMPTS || attempted_topics < PERFORMANCE_MIN_TOPICS {
        return abstained(format!(
            "Need {PERFORMANCE_MIN_ATTEMPTS} first-try answers across {PERFORMANCE_MIN_TOPICS}+ topics \
             (have {mc_first_attempts} across {attempted_topics})."
        ));
    }

    let mut point = 0.0f32;
    let mut variance = 0.0f32;
    for (name, weight) in TOPIC_WEIGHTS {
        let (correct, attempts) = topics
            .get(name)
            .map(|a| (a.first_correct, a.first_attempts))
            .unwrap_or((0, 0));
        point += weight * shrunk_accuracy(correct, attempts);
        variance += (weight * shrunk_se(correct, attempts)).powi(2);
    }
    let half = Z_95 * variance.sqrt();

    // Reasons: weakest attempted topics and biggest unattempted weights.
    let mut attempted: Vec<(&str, f32)> = topics
        .iter()
        .filter(|(_, a)| a.first_attempts > 0)
        .map(|(name, a)| (*name, shrunk_accuracy(a.first_correct, a.first_attempts)))
        .collect();
    attempted.sort_by(|a, b| a.1.total_cmp(&b.1));
    let mut reasons: Vec<String> = attempted
        .iter()
        .take(2)
        .map(|(name, p)| {
            format!("Lowest accuracy: {} ({:.0}%)", name.replace('_', " "), p * 100.0)
        })
        .collect();
    let mut unattempted: Vec<(&str, f32)> = TOPIC_WEIGHTS
        .iter()
        .filter(|(name, _)| {
            topics.get(name).map(|a| a.first_attempts == 0).unwrap_or(true)
        })
        .map(|(name, w)| (*name, *w))
        .collect();
    unattempted.sort_by(|a, b| b.1.total_cmp(&a.1));
    if let Some((name, w)) = unattempted.first() {
        reasons.push(format!(
            "Unpracticed: {} ({:.0}% of the exam counts at guess rate)",
            name.replace('_', " "),
            w * 100.0
        ));
    }

    let confidence = if mc_first_attempts >= 300 {
        "high"
    } else if mc_first_attempts >= 100 {
        "medium"
    } else {
        "low"
    };

    SpeedrunScore {
        available: true,
        abstain_reason: String::new(),
        point: pct(point),
        range_low: pct((point - half).clamp(0.0, 1.0)),
        range_high: pct((point + half).clamp(0.0, 1.0)),
        confidence: confidence.into(),
        reasons,
    }
}

fn readiness_score(
    performance: &SpeedrunScore,
    topics: &HashMap<&'static str, TopicAgg>,
    graded_reviews: u32,
    coverage_percent: f32,
) -> SpeedrunScore {
    // The written give-up rule: >= 200 graded reviews AND >= 50% coverage
    // (and a usable Performance score). State exactly what is missing.
    let mut missing: Vec<String> = Vec::new();
    if graded_reviews < READINESS_MIN_GRADED {
        missing.push(format!(
            "{} more graded reviews",
            READINESS_MIN_GRADED - graded_reviews
        ));
    }
    if coverage_percent < READINESS_MIN_COVERAGE {
        missing.push(format!(
            "{:.0}% more topic coverage",
            READINESS_MIN_COVERAGE - coverage_percent
        ));
    }
    if !performance.available {
        missing.push("a Performance score (see its requirements)".into());
    }
    if !missing.is_empty() {
        return abstained(format!("No score until you have: {}.", missing.join("; ")));
    }

    let p = performance.point / 100.0;
    let (p_low, p_high) = (performance.range_low / 100.0, performance.range_high / 100.0);
    let point = readiness_scaled(p);
    let range_low = readiness_scaled(p_low);
    let range_high = readiness_scaled(p_high);

    // Never "high": the score mapping itself is an unvalidated assumption.
    let confidence = if coverage_percent >= 50.0
        && graded_reviews >= READINESS_MIN_GRADED
        && (range_high - range_low) <= 100.0
    {
        "medium"
    } else {
        "low"
    };

    let mut reasons: Vec<String> = Vec::new();
    let mut weak: Vec<(&str, f32, f32)> = topics
        .iter()
        .filter(|(_, a)| a.first_attempts > 0)
        .map(|(name, a)| {
            let weight = TOPIC_WEIGHTS
                .iter()
                .find(|(n, _)| n == name)
                .map(|(_, w)| *w)
                .unwrap_or(0.0);
            (*name, shrunk_accuracy(a.first_correct, a.first_attempts), weight)
        })
        .collect();
    // Weakest high-weight topics hurt the projection most.
    weak.sort_by(|a, b| ((1.0 - a.1) * a.2).total_cmp(&((1.0 - b.1) * b.2)).reverse());
    if let Some((name, p, w)) = weak.first() {
        reasons.push(format!(
            "Biggest drag: {} ({:.0}% accuracy on {:.0}% of the exam)",
            name.replace('_', " "),
            p * 100.0,
            w * 100.0
        ));
    }
    reasons.push(format!("You have covered {coverage_percent:.0}% of the exam outline."));
    reasons.push("Score mapping is an approximation; no official raw-to-scaled table exists.".into());

    SpeedrunScore {
        available: true,
        abstain_reason: String::new(),
        point,
        range_low,
        range_high,
        confidence: confidence.into(),
        reasons,
    }
}

#[cfg(test)]
mod test {
    use super::*;

    #[test]
    fn weights_sum_to_one() {
        let sum: f32 = TOPIC_WEIGHTS.iter().map(|(_, w)| w).sum();
        assert!((sum - 1.0).abs() < 1e-6, "weights sum to {sum}");
    }

    #[test]
    fn shrinkage_keeps_small_samples_honest() {
        // No attempts -> exactly the guess rate.
        assert!((shrunk_accuracy(0, 0) - GUESS_RATE).abs() < 1e-6);
        // 2/2 must NOT read as 100%.
        let p = shrunk_accuracy(2, 2);
        assert!(p < 0.6, "2/2 should be heavily shrunk, got {p}");
        // Large samples converge toward the raw rate ((90 + 0.8) / 104 ≈ 0.873).
        let p = shrunk_accuracy(90, 100);
        assert!((p - 0.873).abs() < 0.005, "90/100 should be ~0.873, got {p}");
    }

    #[test]
    fn readiness_mapping_hits_anchors_and_is_monotonic() {
        assert_eq!(readiness_scaled(0.0), 200.0);
        assert_eq!(readiness_scaled(0.25), 500.0);
        assert_eq!(readiness_scaled(0.5), 680.0);
        assert_eq!(readiness_scaled(1.0), 990.0);
        // Guess-rate performance should land well below the midpoint.
        assert!(readiness_scaled(GUESS_RATE) < 500.0);
        let mut last = 0.0;
        for i in 0..=100 {
            let s = readiness_scaled(i as f32 / 100.0);
            assert!(s >= last, "mapping must be monotonic");
            assert_eq!(s % 10.0, 0.0, "scores are rounded to 10s");
            last = s;
        }
    }

    #[test]
    fn abstains_without_data() {
        // Empty collection: every score must abstain with a concrete reason.
        let mut col = Collection::new();
        let scores = col.speedrun_scores().unwrap();
        let memory = scores.memory.unwrap();
        let performance = scores.performance.unwrap();
        let readiness = scores.readiness.unwrap();
        assert!(!memory.available && !performance.available && !readiness.available);
        assert!(memory.abstain_reason.contains("20 graded reviews"));
        assert!(performance.abstain_reason.contains("first-try answers"));
        assert!(readiness.abstain_reason.contains("more graded reviews"));
        assert_eq!(scores.coverage_percent, 0.0);
    }

    #[test]
    fn first_attempt_parsing() {
        assert_eq!(
            first_attempt(r#"{"sr":{"n":3,"k":2,"f":1,"t":1712345678}}"#),
            Some(true)
        );
        assert_eq!(
            first_attempt(r#"{"sr":{"n":1,"k":0,"f":0,"t":1712345678}}"#),
            Some(false)
        );
        assert_eq!(first_attempt(r#"{"sr":{"n":0,"k":0,"f":0,"t":0}}"#), None);
        assert_eq!(first_attempt("{}"), None);
        assert_eq!(first_attempt("not json"), None);
    }
}
