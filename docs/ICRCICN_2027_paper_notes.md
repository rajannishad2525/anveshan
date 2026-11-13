# ICRCICN 2027 — Research paper submission notes

Paper: `C:\Users\abcom\Downloads\ANVESHAN_Research_Paper_IEEE_Format.docx`
Authors: Raman Pratap Singh, Rajan Nishad (CSE, Greater Noida Institute of Technology)
Researched: 29 Oct 2026

## Venue decision

- **Chosen: IEEE ICRCICN 2027** — Kalyani Govt. Engg. College (WB), IEEE Conference Record #73691, ISBN 979-8-3195-6787-1.
- Why: **hybrid mode** → can present online from Delhi. IEEE no-show rule: an accepted paper that nobody presents is dropped from IEEE Xplore.
- Rejected: CVMI 2027 (IIITDM Kancheepuram) — better name, but in-person in Chennai only. ICCIDS 2027 — "IEEE approval pending", deadline unclear.
- Do NOT submit the same paper anywhere else at the same time (dual submission).

## Dates

| Step | Date |
|---|---|
| Full paper deadline | **30 Nov 2026** (target: submit by 20–25 Nov) |
| Notification | 1 Feb 2027 |
| Final paper + early-bird registration | 14 Feb 2027 |
| Conference (hybrid) | 27–28 Feb 2027 |

## Official rules (icrcicn.in/submission.html)

| Rule | Requirement |
|---|---|
| Template | Standard IEEE conference template, double column, 10pt |
| Page size | IEEE Word template **US Letter** |
| Page limit | **Max 6 pages**; up to 2 extra pages at ₹1000 each |
| Submission | **PDF** via Microsoft CMT: https://cmt3.research.microsoft.com/ICRCICN2027/ |
| Must include | Title, abstract, keywords, author names + affiliation + **email** |
| Names | No Dr./Mr./Prof. prefixes |
| **Plagiarism** | Turnitin/iThenticate **total ≤10%**, **any single source ≤1%** |
| **AI content** | Must be disclosed in Acknowledgment: which AI tool, which sections, how much |
| Review criteria | Originality, technical depth, correctness, relevance, contribution, readability |
| Welcome paper types | Works in progress, case studies, real-time model demonstrations (our system paper fits) |
| Presentation | One author presents, or a "qualified surrogate". Hybrid mode |
| Registration | One author pays full fee; no refund; paper cannot be withdrawn after registering |

Fees (student author, Indian): early bird ₹8,000 (IEEE member) / ₹8,500 (non-member); late ₹9,500 / ₹10,000.
Before submitting, **email the organizers to confirm in writing that an author can present online**.

## Paper vs rules — checklist (checked 29 Oct 2026)

| Check | Status |
|---|---|
| Double column, IEEE style | ✅ |
| Body font Times New Roman 10pt (Normal style) | ✅ |
| Pages: 4 of 6 | ✅ room for 2 more pages |
| Section structure (Abstract → Index Terms → I–VII → Ack → References) | ✅ |
| Table captions ("TABLE I" above the table) | ✅ |
| Table II numbers (TP/FP, precision, recall) | ✅ recalculated, all match |
| Page size | ❌ currently **A4** (11909×16834 twips) → change to **US Letter** |
| Author email | ❌ missing — compulsory |
| AI disclosure | ❌ missing from Acknowledgment |
| Figures | ❌ zero figures |
| Precision/recall definitions (Sec. IV-B) | ❌ FP and FN definitions are wrong |
| References | ⚠️ only 12, some outdated / arXiv versions |
| Plagiarism | ⚠️ not checked; report and paper share text → self-plagiarism risk |

## Fixes to make

**(a) Correctness — Section IV-B**
- Paper says FP = "positive examples incorrectly identified" → correct: **FP = negatives wrongly flagged as positive**.
- Paper says FN = "negative examples incorrectly identified" → correct: **FN = positives that were missed**.
- Write as numbered equations: Precision = TP/(TP+FP), Recall = TP/(TP+FN).
- Simplify the confusing "AP ... integrated trapezoidal rule" sentence.

**(b) Add 2 figures (2 pages are free)**
- Fig. 1: system architecture — Import → Metadata/SQLite → RemoteCLIP → FAISS → Registration → Change screening → Review.
- Fig. 2: an example — a query with its top-5 results, or a before/after pair with its candidate difference map.

**(c) Author block** — add an email for both authors (college email preferred).

**(e) References**
- [11] RS5M/GeoRSCLIP → cite the published IEEE TGRS version (DOI 10.1109/TGRS.2024.3449154) instead of arXiv.
- [6] Cheng et al. change-detection review → find and cite its published journal version.
- [2] RemoteCLIP and [4] Faiss → verify volume/number on IEEE Xplore. The Faiss journal version went online Oct 2025 (DOI 10.1109/TBDATA.2025.3618474); confirm "vol. 12, no. 2, 2026".
- Grow to 15–20 references: add 2023–2025 change-detection and remote-sensing VLM papers. **Verify every one**.

**(f) Plagiarism (10% / 1% limit)**
- Run college Turnitin first.
- Paraphrase paragraphs shared with the project report.
- Don't upload the report anywhere public before submission.

**(g) Framing** — the abstract currently leads with results, which read as negative. Lead with the contribution (offline system + auditable workflow + honest evaluation), then the results. Keep the numbers, change only the order.

## College project report vs IEEE paper

- They are 2 separate documents. The report follows the **college format** (TNR 12pt, headings 14pt, double spacing, 70–100 pages, the 13 fixed sections). IEEE rules apply only to the paper.
- If the college puts the report into the Turnitin **repository**, the paper can later match against it (single-source limit is 1%). Ask for a "no repository" check, or keep the paper text clearly paraphrased.
- In the report, call the paper "**submitted**" to IEEE ICRCICN 2027, never "published" or "accepted" until it actually is.
- IEEE-style habits worth using inside the college format: IEEE-style references with numbered [1] in-text citations, numbered figures/tables with captions, real measured numbers (no unbacked claims).

## Turnitin check history (same PDF)

| Check | Similarity | AI |
|---|---|---|
| ~mid Oct 2026 | 1% | 21% |
| 29 Oct 2026 | 9% | 98% |

- The AI jump matches Turnitin's **English AI model update of 14 Oct 2026** ("improved AI detection while minimizing false positives"). Resubmitted files get re-scored; old reports don't change. Since Aug 2025, the detector also flags AI-bypasser/humanizer tools.
- For the similarity jump, check the Match Overview sources: "Submitted to <college>" = repository self-match; otherwise newly indexed internet sources.
- Plan: rewrite in our own words + AI disclosure in the Acknowledgment. **No humanizer tools.** Keep Git/Word history as proof of authorship.

## Review of 29 Oct 2026 (paper + report)

Overall ratings: **Paper 5/10**, **Report 6/10**. Acceptance chance today: low-medium; after fixes: medium-high.

**Paper:** issues as listed above. Measured 8-gram text overlap with the report is 1.9%, all of it in the reference list, so self-plagiarism risk is low.

**Report** (84 pages; coding chapter on pp. 69–80 → ~72 pages without code):
- Missing: System Analysis (5.1 Identification of Need, 5.2 Preliminary Investigation); an Analysis chapter with DFD Level 0/1/2, ER diagram and table/data structure.
- Feasibility needs separate 6.1/6.2/6.3 subheadings.
- Chapter order doesn't match the college list.
- Spacing is mostly 1.5 → must be **double**.
- Headings are 16/13pt → must be **14pt**. Captions/tables are 9pt, code is Consolas 8pt.
- **Conflict with the paper:** report §1.5/§6 claims the quality gate improves precision (169-tile pilot), but the paper's full 663-tile OSCD test shows the gate is worse (AP 0.464 vs 0.475). Update the report to the full-split result.
- Top/bottom margins 0.5"; add a bigger left margin for spiral binding.
- Certificate says "He" for both students.
- References: only 10, and [10] is generic docs.

## Novelty / prior-work check (29 Oct 2026)

**The idea is NOT unique.** The task "Semantic Retrieval and Multi-Temporal Change Analysis of Satellite Imagery" already has 10+ public GitHub prototypes with almost the same stack (offline, RemoteCLIP/OpenCLIP + FAISS + change detection), e.g.:
- IRIS
- SentinelEye
- GeoNexa
- MiraeNova
- ORBITRACE
- ASTREVA
- Subhajit-Masanta (OSCD text mAP 0.16 vs random 0.12)

No published IEEE paper from these teams was found as of 29 Oct 2026.

Closest academic work — **must cite and differentiate**:
- arXiv **2607.28571** "Finding Change in Satellite Archives from Text" — CLIP-encoded frames offline, subtraction filter, re-rank. It notes RemoteCLIP lacks bi-temporal mechanisms.
- also check arXiv 2604.14044 (Decoding the Delta) and 2512.23244 (ViLaCD-R1).

Our real differentiator: an honest, measured evaluation of this common pipeline.
- Full OSCD split with random-AP baseline + pair-level bootstrap CI
- Pixel diff ≥ RemoteCLIP
- Nuisance perturbation tests
- Registration refusal
- Verified offline (zero socket attempts)
- Provenance/review record

Frame the paper as: "a widely-built pipeline, measured honestly — what it can and cannot do."

To add:
- Related Work paragraph + comparison table (ours vs typical prototypes vs 2607.28571)
- optional: one stronger change baseline (e.g. CVA)
- never copy text from those READMEs

## GitHub competitor comparison (29 Oct 2026)

Scanned ~36 PS 26227-style repos with `gh api`. Ratings come from READMEs + file/test counts only; we did not run their code.

| Repo | What stands out |
|---|---|
| **Nani4481/geoseek** — best engineering | 91+ commits, 351 tests; trained FC-Siam-diff on OSCD, F1 56.0% held-out; RemoteCLIP search; React; limitations section |
| **Subhajit-Masanta/satellite-semantic-retrieval-change-analysis** — most truthful | 4 datasets (OSCD, LEVIR-CD, SYSU-CD, EuroSAT) with random baselines, held-out splits, a "What we do not claim" section. OSCD tile AUC: patch features 0.70 vs pixel diff 0.64 vs whole tile 0.56. EuroSAT text mAP 0.44. No tests, Streamlit demo |
| **25cseb50robindanie/IRIS** — best desktop packaging | Electron IRIS.exe; only ops metrics, no labelled accuracy; marketing tone |
| hackteam29114 | honest MVP docs + eval scripts |
| AstraTrace | "100% complete & verified" overclaim |
| GeoNexa | big claims, thin evidence |

**ANVESHAN position:** top 3.
- Unique: honesty + full-OSCD bootstrap CI + nuisance tests + provenance/review + packaged offline desktop.
- Weak:
  - no trained change model
  - retrieval eval only 3 queries
  - whole-tile embeddings
  - only 3 git commits

Learn and add (also strengthens the paper):
1. Patch-level RemoteCLIP features on OSCD — Subhajit shows they beat pixel diff.
2. EuroSAT retrieval eval (mAP + random baseline) instead of the 3-query probe.
3. A trained FC-Siam-diff baseline (or cite the published ~52.8% F1).
4. Commit regularly (authorship evidence).

## Deep code read: geoseek, Subhajit, IRIS (29 Oct 2026)

Cloned read-only; none of their code was run. **Neither repo has a LICENSE file → reimplement ideas ourselves, never copy code.**

**Subhajit** — `experiments/run_oscd_v2.py`, `patch_models.py`, `results/oscd_v2_results.json`:
- Uses ViT patch tokens (`model.visual.output_tokens=True`) and computes a per-patch cosine distance between dates. Tile score = mean of the top 10% patch distances.
- "Centred" variant: subtract each tile's mean token first (cancels whole-tile season/light shifts).
- Variant and threshold picked on 14 train cities, reported on 10 test cities.

  | OSCD test AUC | Score |
  |---|---|
  | RemoteCLIP whole-tile | 0.553 |
  | RemoteCLIP patch top-10% | 0.678 |
  | RemoteCLIP centred top-10% | 0.707 |
  | DINOv2-S patch top-10% | 0.737 |
  | Pixel diff, brightness-matched | 0.640 |
  | Pixel diff, raw | 0.579 |

- Pixel-level F1 stays weak (~0.21–0.25).
- ⚠️ `report_tools/noobify.py` deliberately inserts typos into their report to look like a "hurried student draft" (AI-detection evasion). Do NOT adopt.

**geoseek** — `docs/EVALUATION_REPORT.md`, `scripts/train_change.py`:
- Change model: FC-Siam-diff trained on OSCD with 5 bands (RGB+NIR+SWIR).
  - Split: 11 fit / 3 validation / 10 test, with asserts against leakage.
  - Threshold picked by F0.5 on validation, then frozen.
  - Test F1 56.0% (published FC-Siam-diff: 52.8%).
  - Reports per-region F1 (valencia 3.8%).
  - Leakage red-flag if more than +8 pts above published.
- Retrieval eval: non-circular. A spectral "judge" uses NIR/SWIR indices that the RGB model can't see.
  - Pool per query = RemoteCLIP top-20 ∪ vanilla-CLIP top-20 ∪ a random sample.
  - 16 queries, 3,267 tiles. Reports P/R/nDCG@K vs the vanilla CLIP control and vs chance.
  - Withdrew their own wrong claim (12.7× → 1.16×).

**IRIS:** the "standalone .exe" claim is false.
- Electron loads `http://127.0.0.1:5173` (Vite dev server).
- `launch.ps1` starts the backend from `.venv\Scripts\python.exe`.
- So it needs a dev environment.
- ANVESHAN's Inno installer + bundled runtime + WebView2 is the real thing.

**Adopt for ANVESHAN, in priority order:**
1. Patch top-10% (+ centred) RemoteCLIP scoring on our OSCD split, train-selected. Expected to beat pixel diff (paper Table II).
2. Retrieval eval with a non-circular judge + vanilla-CLIP control + random pool (replaces the 3-query probe).
3. Optional: FC-Siam-diff trained baseline with a validation-only threshold.
4. Leakage asserts in eval scripts.

## Software audit (29 Oct 2026)

**Verified:**
- pytest: **125 passed** (needs a fresh `--basetemp`; the stale `%TEMP%\anveshan-pytest-abcom` gives WinError 5).
- Installed app (Start Menu → `C:\Program Files\ANVESHAN`, v0.9.4, 16 Sep):
  - starts in ~18 s
  - `/api/status`: `offline:true`
  - closing the window leaves no process (A3 ✓)
- Code: no external URLs in `web/`; scan default = `append`; data dir = `%LOCALAPPDATA%\ANVESHAN\datasets`; NDVI gated on NIR; scores labelled as screening cues.

**Problems:**
- The Desktop `ANVESHAN.lnk` points to the **repo's `benchmark-output\package-0.9.4`**, not the installed copy.
- 3 diverging copies (repo / package / installed). `app/main.py`, `semantic_clusters.py`, `desktop.py`, `web/app.js` have **uncommitted** changes missing from the installed 0.9.4.
- Only 3 git commits.
- Repo root clutter: `_page*.png`, `_fixed*.png`, report build scripts, `.pytest-tmp`.

**Not verified yet:**
- A1 clean machine
- A2 network-off import→search→export inside the packaged app
- A4 unseen imagery
- A5 kill mid-import / disk full

## New measured results (29 Oct 2026) — use these in the paper

**Hardware:** Intel i5-8365U, 4 torch threads, CPU only. Zero network attempts in both runs.

**OSCD patch-token scoring** (`eval/oscd_patch.py` → `results/oscd_patch/`):

| Method (663 test tiles) | AP |
|---|---|
| Patch top-10% (train-picked) | 0.461 |
| Whole-tile | 0.475 |
| Pixel diff | 0.492 |
| Random | 0.429 |

- At the train threshold, patch top-10% gets P 54.2% / R 68.3% / FP 162, vs pixel P 48.0% / R 91.8% / FP 279.
- Per pair: patch ≥ pixel on 6 of 10 test pairs; it loses badly on pairs 04 and 08.
- Centred-max has test AP 0.495, but it was NOT train-picked, so it cannot be claimed.
- **Not added to the app.**

**EuroSAT retrieval** (`eval/eurosat_retrieval.py` → `results/eurosat_retrieval/`): 16,200 labelled patches, 10 classes, one fixed prompt per class, 39 min.

| Query type | mAP | P@10 | Chance |
|---|---|---|---|
| Text | **0.331** | 0.50 | 0.10 |
| Image | **0.589** | 0.896 | 0.10 |

- Best text classes: industrial 0.818, river 0.61.
- Failures: forest 0.067 (below chance), sea/lake 0.103 (at chance).
- This replaces the 3-query Noida probe as the main retrieval result.

**Software:**
- Installer **0.9.5** built and installed (Program Files). Desktop shortcut repointed to it.
- 0.9.5 starts in ~16 s, offline, and leaves no process after the window closes.
- Deleted old setups 0.9.0–0.9.3 and `benchmark-output/package-0.9.4` (disk was full; user approved).

## Paper v2 (29 Oct 2026, afternoon)

File: `C:\Users\abcom\Downloads\ANVESHAN_Research_Paper_IEEE_Format_v2.docx` (+ `_v2.pdf`). Original kept; backup `...BACKUP_2026-10-29.docx`.

Done in v2: (a) FP/FN + equations (1)(2), AP defined as step-wise sum; (b) Fig. 1 architecture, Fig. 2 per-pair OSCD AP; (c) email added for Rajan, **Raman's is a yellow placeholder**; (d) AI disclosure in Acknowledgment; (e) 20 references, all checked against OpenAlex/arXiv; (g) abstract leads with the contribution; EuroSAT is now the main retrieval result (Table II); OSCD patch top-10% row + 95% CI column in Table III; Related Work + Table I vs Roy et al. / Delta-LLaVA; new Sec. III-C packaging. US Letter, 5 of 6 pages (Word count).

Correction: arXiv 2607.28571 (Roy, Bong, Beltrame) trains fusion designs on a frozen CLIP encoder and tests on LEVIR-CC / Dubai-CC with a difference-model shortlist. It does not mention RemoteCLIP. The novelty section above described it wrongly.

Emails now added for both authors. Still open: authors to confirm the AI-disclosure wording; Turnitin check; sync the college report with these numbers.

## Standard IEEE conference paper structure

1. Title (24pt, centered)
2. Authors: name, department, college, city/country, email
3. Abstract: 150–250 words, one paragraph
4. Index Terms: 4–6 keywords
5. I. Introduction: problem, gap, contributions
6. II. Related Work
7. III. Proposed System / Methodology (with architecture figure)
8. IV. Experimental Setup: dataset, metrics, baselines
9. V. Results: tables + figures
10. VI. Discussion & Limitations
11. VII. Conclusion (+ future work)
12. Acknowledgment: guide + AI disclosure
13. References: IEEE style [1], [2]… in order of first citation

## Timeline

- Now → 10 Nov: fixes (a)–(e) + figures
- 10–15 Nov: Turnitin check, paraphrase
- 15–20 Nov: final PDF in the US Letter template
- 20–25 Nov: create a CMT account and submit (don't wait for the last day)

## Sources

- https://icrcicn.in/submission.html
- https://icrcicn.in/registration.html
- https://icrcicn.in/call-for-papers.html
- https://icrcicn2025.icrcicn.in/html/registration.html (extra page fee)
- https://www.ieee.org/conferences/publishing/templates
- https://api.openalex.org/works/doi:10.1109%2FTBDATA.2025.3618474
- https://arxiv.org/abs/2306.11300v5
