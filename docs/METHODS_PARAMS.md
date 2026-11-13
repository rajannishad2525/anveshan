# ANVESHAN evaluation methods and current boundaries

The full OSCD run uses the locally staged `blanchon/OSCD_RGB` mirror: 14
training image pairs for threshold selection and 10 test image pairs for one
evaluation. Pairs, not tiles, define the split. This is the mirror's public
split, **not** a new geographically independent holdout. Every image is cut
into complete, non-overlapping 64×64 RGB tiles; partial edge tiles are dropped.
A tile is labelled positive if more than 2% of its mask pixels are nonzero.

RemoteCLIP score: `1 - dot(L2(before_embedding), L2(after_embedding))`.
Pixel score: the unchanged `anveshan.baseline.pixel_score` function in the
locally staged source. The model is RemoteCLIP ViT-B/32 from a staged local
checkpoint. The script logs its SHA-256 and software/hardware versions.

The `rejection.classify_rejection` heuristic is **pre-existing** in the
staged code. A candidate passes this experimental gate only when that function
returns `unexplained`. Declined candidates get score -1. Its seven fixed rule
thresholds are cloud 0.5 and haze, shadow, seasonal, registration,
illumination, radiometric 0.3 each. They were not newly calibrated on these
14 train pairs, and their original selection history is unverified; all gate
results are exploratory. The script predeclares seven leave-one-rule-out
ablations, logs each raw rule score, and selects the RemoteCLIP score cutoff
for each variant on training pairs only. The published paper must not claim
the gate is confirmatorily superior on this basis.

Average precision uses `sklearn.metrics.average_precision_score`, not
trapezoidal precision–recall area. Precision and recall use a fixed threshold
selected on training data. Positive prevalence is the random precision–recall
reference line; finite-sample random-ranking AP is estimated from 1,000 seeded
rankings rather than asserted to be exactly equal to prevalence. The
pair bootstrap resamples whole test pairs (1,000 draws), preserving within-pair
tile correlation. Its percentile interval describes this small set of 10 test
pairs, not transfer to new regions or sensors.

The earlier 3-pair results in `reality_check/` remain frozen historical
measurements. Do not combine their denominators with the new full-OSCD run.
The 56-chip Noida retrieval judgments remain one-reviewer provisional labels;
the 12-query AOI probe was used for development. Neither is an untouched final
retrieval benchmark. Human independent labeling and a frozen new query set
are still required.
