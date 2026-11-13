# How Turnitin works — research notes (29 Oct 2026)

Based on Turnitin's public docs and university help pages. We did NOT reverse engineer it: the detection runs on Turnitin's servers and their terms forbid reverse engineering.

## 1. Similarity (plagiarism)

1. Splits the document into **phrases** and gives each one an ID. Common words ("and", "the") are skipped.
2. Compares them against a huge database:
   - web pages, current and archived
   - journals and publications
   - the **repository of earlier student submissions**
3. Uses NLP + strict matching heuristics to cut false positives.
4. Links each match to one **primary source**. Excluding that source may leave the score unchanged, because a second source can cover the same text.
5. **Similarity % = share of the document that matched.** Turnitin says it is not a plagiarism verdict; a human decides.

Exclusions (settings dependent):
- text inside **"quotation marks"**
- **bibliography** (detected automatically in English papers)
- **small matches** (default 8 words)

How to fix our documents:
- Any run of **8 or more words** copied from a source gets caught. Write in your own words and cite with [n].
- Use quotes rarely, and always with a citation.
- Write references in standard IEEE style so they are excluded as a bibliography.
- A repository self-match (our 1% → 9% jump) → ask the teacher to exclude our own earlier submission.
- ICRCICN: **any single source must stay ≤1%** → rewrite every passage whose source goes over 1%.

## 2. AI writing detection

- Classifier trained on **human-written vs AI-written** academic text.
- Splits the text into overlapping segments and **scores each sentence** as AI-like or human-like. Teachers see the flagged sentences highlighted.
- Checks only **long-form prose**, minimum ~300 words. Prose inside tables is included; the **bibliography is excluded**.
- Scores of **1–19% are shown as "\*"**, with no number (to avoid false alarms).
- Detects AI-paraphrased text (since Dec 2023) and **AI bypasser/humanizer tools (since 27 Aug 2025)**.
- AI-written text tends to be smooth and predictable: generic phrases, even sentence lengths, perfect flow.
- Turnitin's own disclaimer: the AI score **must not be the only basis** for action against a student.

Model update timeline:

| Date | Update |
|---|---|
| 14 Oct 2026 | English model improved — this is why our score jumped 21% → 98% |
| 6 Oct 2026 | Turkish, German, Dutch |
| 18 Aug 2026 | Arabic; lists GPT-5.x, Claude 4.x, Gemini 3, DeepSeek and others |
| 5 May 2026 | Spanish |
| 12 Feb 2026 | Recall update |
| 14 Oct 2025 | Recall update |
| 27 Aug 2025 | Bypasser detection added |

Old reports don't change; only a resubmitted file gets the new model's score.

Other Oct 2026 features:
- Authorship Dashboard filters (13 Oct)
- Microsoft SSO (8 Oct)
- Clarity Writing Report timestamps (Aug)

How to fix our documents (honest route only):
- **Rewrite the flagged paragraphs yourself.** Swapping words doesn't help.
- Add specific details only we know: the 56 Noida chips, why the farmland query failed, the i5-8365U / 335 ms numbers.
- **No humanizer / paraphraser / Quillbot.** Turnitin flags them separately.
- **Disclose AI use**: the Acknowledgment for the IEEE paper, and tell the teacher.
- Keep Git history and Word version history as proof of authorship.

## Sources
- https://guides.turnitin.com/hc/en-us/articles/28294949544717-AI-writing-detection-model
- https://guides.turnitin.com/hc/en-us/articles/27251688507533-Turnitin-release-notes
- https://www.turnitin.co.uk/blog/how-to-bring-deeper-meaning-to-the-similarity-score
- https://help.turnitin.com/simcheck/user/the-similarity-report/excluding-content-from-the-similarity-report.htm
- https://fa-help.turnitin.com/ithenticate/user/the-similarity-report/excluding-content-from-the-similarity-report.htm
- https://helpdesk.lsua.edu/support/solutions/articles/48001269897-turnitin-similarity-scoring-using-exclusions-and-filters
- https://learningsystems.vcu.edu/instructional-tools/turnitin/faculty/similarity-reports-explained/report-exclusions
