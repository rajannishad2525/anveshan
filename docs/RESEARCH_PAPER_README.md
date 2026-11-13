# ANVESHAN research-paper evidence package

This is a college IEEE-style manuscript and evaluation package, **not** an
accepted IEEE/Springer/Scopus publication. `paper/main.tex` is the IEEEtran
source; `ANVESHAN_IEEE_Research_Paper.docx` and `.pdf` are an editable/printable
college draft. The older three-pair paper claims were replaced after the full
OSCD test reversed their direction.

## Frozen evaluation

- Config: `configs/oscd_full.json` (seed `20261010`).
- Raw full-split run: `results/oscd_full_v2/raw_tile_scores.csv`.
- Train-selected cutoffs: `results/oscd_full_v2/train_thresholds.json`.
- Test summary and pair table: `results/oscd_full_v2/summary.json` and
  `test_pair_summary.json`.
- Derived random, pair-bootstrap, gate ablation, registration and synthetic
  nuisance outputs are under `results/`.
- `reality_check/` holds untouched historical pilot results. `results/oscd_full/`
  holds a train-only interrupted run; it has **no** test output. The new
  full test was run once in `results/oscd_full_v2/`.
- Baseline Git tag points to HEAD only. It does not snapshot pre-existing
  uncommitted user changes; hashes are in `results/BASELINE_MANIFEST.md`.

Run `python -B run_all.py` with the staged experiment environment to recreate
tables and figures from frozen raw outputs. This deliberately does not rescore
the test split. Running the whole model pipeline from scratch requires the
staged OSCD RGB mirror, RemoteCLIP checkpoint and the original local Python
source in `C:/Users/abcom/Downloads/anveshan`; see `docs/METHODS_PARAMS.md`.

## Unfinished before external submission

The RGB mirror's redistribution rights and every capture-derived source must
be verified. Retrieval needs a new frozen query set and two independent blind
reviewers; `tools/label_tool.html` and `eval/analyze_labels.py` support this
manual stage. A plain CLIP baseline, trained change detector, real-pair labels,
registration-under-real-change evaluation, and a new untouched test set are
not supplied. No user study has been conducted. Therefore the manuscript does
not claim analyst benefit or reliable autonomous change detection. A specific
venue and its official page limit/metadata rules have not yet been selected.

The native LaTeX preview compiler returned a host setup error in this session,
so `paper/main.tex` has static checks but no successful LaTeX compilation claim.
The DOCX-to-PDF export was paginated in Word and inspected separately.
