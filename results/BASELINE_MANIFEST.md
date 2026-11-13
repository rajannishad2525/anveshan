# Baseline manifest before research-evaluation fixes

The Git tag `baseline-before-fixes` points to the pre-existing HEAD commit.
The checkout already contained many unrelated uncommitted user changes; the tag
does **not** snapshot those edits. No pre-existing edits were staged or reset.
Historical results remain in `reality_check/` and have not been overwritten.

SHA-256 at baseline inspection:

| File | SHA-256 |
|---|---|
| `reality_check/benchmark_summary.json` | `3AEE3FD242E72AA9D4A4FE9AD3E9C43C1C2F1F120E6FEA9A89BBD03BF80985CF` |
| `reality_check/results.json` | `520E61E109C77D8F32C9E324C500B5431C7FD8F43D65DA75D09C268707611176` |
| `reality_check/retrieval_eval_final.json` | `6963982E50FF5DF0E8F0F6A5D9CF8B15BBB0E1949EEE7FAFF7E38C0B7F6535B7` |
| `ANVESHAN_IEEE_Research_Paper.docx` | `6207D00900A99C8CD8446B07916850CC47D29680D3BCBE037AE7B9364763D675` |

This manifest is the safe baseline for comparing newly generated numbers.
