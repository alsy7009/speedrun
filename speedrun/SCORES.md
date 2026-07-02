# The Three Scores: Memory, Performance, Readiness

Three separate scores, never blended. Computed in the shared Rust engine
(`rslib/src/stats/speedrun.rs`, RPC `GetSpeedrunScores`) so desktop and phone
show identical numbers. Every score carries: point estimate, likely range,
% of exam covered, confidence, last-updated time, main reasons, and an
abstain state with the exact give-up rule spelled out.

## Shared inputs

- **Topic weights** (`speedrun/gre_topics.json`): the ETS GRE Math outline is
  ~50% calculus, ~25% algebra, ~25% additional topics. We split those blocks
  across our `topic::` tags (weights sum to 1.0):
  - Calculus 0.50 = calculus .25, multivariable .10, sequences/series .10, ODEs .05
  - Algebra 0.25 = algebra .10, linear algebra .075, abstract algebra .05, number theory .025
  - Additional 0.25 = real analysis .075, probability/stats .075, combinatorics .05,
    geometry .03, complex analysis .02
- **Coverage %** = sum of weights of topics with ≥ 1 studied card (a card that
  has left the "new" state), × 100.
- **Graded review** = a revlog row with ease 1–4 (manual reschedules excluded).
- **MC first attempts** = the outcome of each card's *first* multiple-choice
  answer. The MC tracking hook stores a compact aggregate on
  `card.custom_data`: `{"sr": {"n": attempts, "k": correct, "f":
  first_attempt_correct, "t": last_ts}}` (Anki caps custom_data at 100 bytes).
  The first attempt is our proxy for "a question you had never seen before".

## Memory — chance you recall a taught fact right now

- **Population:** cards with FSRS memory state (i.e. cards we actually taught).
- **Point:** mean FSRS retrievability R(now) over that population, computed the
  same way as Anki's card stats (`current_retrievability_seconds`).
- **Range:** mean ± 1.96·SD/√n over cards (normal approximation).
- **Reasons:** the weakest topics by mean R.
- **Give-up rule:** *no Memory score until ≥ 20 graded reviews.* Below that we
  show "not enough reviews yet (have X, need 20)".
- *Not* used: MC correctness. Memory is purely the FSRS recall model.
- Follow-up (validation): calibration chart + Brier score on held-out reviews.

## Performance — chance you get a NEW exam-style question right

- **Per topic:** first-attempt MC accuracy, shrunk toward the 5-choice guess
  rate: p_t = (correct_t + k·0.2) / (attempts_t + k), k = 4. Shrinkage keeps
  tiny samples honest (2/2 does not mean 100%).
- **Aggregate:** P = Σ_t w_t · p_t, where **uncovered topics count at the guess
  rate 0.2** — exactly what would happen on the real exam.
- **Range:** per-topic binomial SE = √(p_t(1−p_t)/(attempts_t+k)), combined as
  √(Σ w_t²·SE_t²), ± 1.96·SE on the aggregate.
- **Reasons:** lowest-accuracy attempted topics + highest-weight unattempted ones.
- **Give-up rule:** *no Performance score until ≥ 30 MC first attempts spanning
  ≥ 3 topics.*
- *Not* used: FSRS retrievability. Performance is measured on question outcomes,
  which is why it can diverge from Memory (the paraphrase test will quantify this).

## Readiness — projected GRE Math score (200–990)

- **Mapping (our documented assumption):** piecewise-linear interpolation of
  expected fraction correct P through anchor points
  (0→200, 0.25→500, 0.50→680, 0.85→900, 1.0→990), rounded to the nearest 10.
  ETS publishes no raw→scaled table; anchors approximate the generous curve
  implied by public percentile data. This is an assumption and is why Readiness
  confidence is capped at *medium*.
- **Range:** the Performance CI (P_low, P_high) mapped through the same curve.
- **Confidence:** `low` by default; `medium` when coverage ≥ 50% **and**
  ≥ 200 graded reviews **and** range width ≤ 100 points. Never `high` until the
  mapping is validated against real score data.
- **Reasons:** weakest high-weight topics, coverage gaps, and the mapping caveat.
- **Give-up rule (the line, written down):** *no Readiness score until the
  student has ≥ 200 graded reviews AND ≥ 50% weighted topic coverage.* Below
  the line the app abstains and states exactly what is missing, e.g.
  "142 more graded reviews; 23% more topic coverage".

## Display contract (all three scores)

point · range · coverage % · confidence · last updated · reasons · abstain
state. When a score abstains, nothing that looks like a score is shown — only
the missing requirements.

## Worked examples (inputs → outputs)

**A) Early student — Readiness abstains (the give-up rule at work).**
Inputs: 142 graded reviews; studied cards in calculus (mean R 0.71) and algebra
(mean R 0.66); 21 MC first-attempts across 2 topics; weighted coverage 38%.
Outputs:
- Memory → **68%**, range 61–75%, confidence *low* (≥20 reviews, so it shows).
- Performance → **abstains**: "Need 30 first-try answers across 3+ topics
  (have 21 across 2)."
- Readiness → **abstains**: "No score until you have: 58 more graded reviews;
  12% more topic coverage." (Needs ≥200 reviews **and** ≥50% coverage.)

**B) Further along — all three show.**
Inputs: 240 graded reviews; 120 MC first-attempts over 7 topics; per-topic
first-attempt accuracy e.g. calculus 18/30, linear_algebra 9/12, algebra 22/28,
…; weighted coverage 62%.
Outputs (illustrative):
- Memory → **74%**, range 70–78%, confidence *medium*.
- Performance → **P ≈ 0.55**, range 0.49–0.61 (GRE-weighted, uncovered topics
  counted at the 0.20 guess rate). Reason: "Lowest accuracy: real analysis
  (33%)."
- Readiness → **≈ 700**, likely range 660–740, confidence *medium* because the
  raw→scaled mapping is an assumption. Reason: "Biggest drag: real analysis
  (33% on 7.5% of the exam)."

*(Numbers illustrate the contract and the give-up thresholds; exact values move
with the data. The abstain thresholds and the 200–990 anchors are the fixed,
documented parts.)*

## Interleaving: before → after (the Rust change, visibly doing something)

Gathered queue (blocked): `alg, alg, alg, geo, geo, calc, calc`
After the least-emitted-fraction interleaver:
`alg, geo, calc, alg, geo, alg, calc` — no two adjacent share a topic, and the
minority topic (calc) is spread across the queue instead of clustered at the
end. Verified by `topic_interleaver.rs` tests + the Python end-to-end test.

## Follow-ups (validation deliverables, not yet built)

- Memory calibration (held-out reviews → calibration chart, Brier/log-loss).
- Performance held-out validation + the 30×2 paraphrase test (memory vs.
  reworded-question gap).
- Leakage check script for held-out/AI-generated items.
