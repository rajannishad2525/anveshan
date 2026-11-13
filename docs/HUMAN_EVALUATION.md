# Human work required before publication-level claims

1. Freeze 30–50 text/example-image queries **before** any new score inspection.
   Record query texts, concepts, candidate pool, selection rule and a Git tag.
2. Pool top-k images from all methods plus sampled negatives, deduplicate,
   randomise with a saved seed and remove method names. Package the images and
   `data/labels/manifest_template.json` in the format expected by
   `tools/label_tool.html`. Check redistribution rights before packaging.
3. Two independent reviewers should use pseudonyms and export separate CSVs.
   They should not see each other's labels. Resolve disagreements in a third
   adjudication file; preserve both originals. Uncertain/unusable is not a
   negative label by default.
4. Only after adjudication, compute metrics and inter-rater agreement.
   Do not tune prompts or ranking on this final set.
5. A user-study benefit claim needs a separate consented, counterbalanced
   study. Until then, the paper may describe a proposed review workflow but
   may not claim that it improves analyst accuracy or speed.

No human labels or user-study outcomes are manufactured by the software.
