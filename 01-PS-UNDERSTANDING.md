# ANVESHAN — Problem Understanding & Proof of Success

**Team ka first shared document | 10 September 2026 | v0.1**


**Title:** Semantic Retrieval and Multi-Temporal Change Analysis of Satellite Imagery.

**Category:** Software. **Theme:** Space Technology.

This is our paraphrased understanding, not a replacement for the official PS. “Official requirement” and “team proposal” are separated below. No existing implementation has been audited yet. No technology, model or performance claim is approved by this document.

## 1. Problem ko ek minute mein samjho

Satellite images ka archive bahut bada hai. Aaj analyst coordinates, date aur sensor se images nikaal sakta hai, lekin interesting jagah dhoondhne ke liye use pehle se pata hona pad sakta hai ki kahan aur kab dekhna hai.

Humein archive ko **image ke meaning aur time ke saath hue changes** se searchable banana hai. Analyst text ya example image de, relevant locations discover kare, evidence dekhe aur decide kare ki result useful hai ya false alarm.

**Product promise — our interpretation:** “Analyst ko imagery archive mein relevant sites aur meaningful changes dhoondhne, verify karne aur traceable evidence export karne mein madad mile, poora workflow offline chale.”

Example: “Nadi ke paas naye structures” query par system relevant candidates rank kare. Analyst ek result khole, earlier/later usable imagery compare kare, similar sites dekhe, candidate confirm/reject kare aur source details ke saath export kare. Yeh example hai; isi ek query ke liye solution hard-code nahi karna.

## 2. Official requirements → working proof

Proof column team ka proposed demonstration hai; organiser ka published scoring rubric nahi.

| Official capability | Simple meaning | Demo mein kya evidence dikhayenge |
|---|---|---|
| Semantic and multimodal retrieval | Free-text aur example image se ranked results; AOI, date, sensor/metadata filters | Ek unseen text query aur ek image query; results ki relevance aur working filters |
| Multi-temporal change analysis | Specified area/time mein appearance, disappearance, expansion/contraction; supported change classes; earliest supported observation | Multiple dated observations, change class/region, first usable observation supporting change |
| False-alarm suppression and quality | Clouds, haze, snow, season, illumination, view geometry, radiometry aur registration errors ko handle karna; precision ko importance | Real-change example ke saath difficult no-change cases; uncertain/unusable imagery visibly identified |
| Discovery and clustering | Ek site se wider archive mein comparable sites discover karna | Selected result se similar-site group open karna, members ko inspect karna |
| Analyst workflow and provenance | Ranked review queue; before/after, location, time, source/sensor, confidence, processing history; persistent confirm/reject and export provenance | Review decision save karke reopen; exported result se source scene aur processing trace karna |
| Scale, incremental ingestion and sovereignty | Efficient index; new acquisitions without full rebuild; complete on-premises operation; georeferencing/metadata; organiser-defined formats such as GeoTIFF/COG | Naya scene add, affected tiles index, new result searchable; old index retained; network disabled end-to-end run |

Feedback ko subsequent reranking/refinement mein use karna official wording mein chosen approach ke support par conditional hai. Decisions preserve karna required hai.

## 3. Constraints jo architecture ko shape karte hain

- **Official:** Approved models, libraries aur data locally stage hone ke baad complete demonstration network disabled chalega. Evaluation mein cloud services/external APIs par dependency nahi ho sakti.
- **Official:** Public pretrained models allowed hain, lekin origin/licence declared aur weights offline packaged hon.
- **Official:** Evaluation imagery public ya organiser-generated hogi; classified, operational ya service-generated imagery nahi hogi.
- **Official:** Georeferencing aur acquisition metadata preserve hon. Export mein source-scene aur processing provenance rahe.
- **Official:** Demonstration organiser-defined area aur time span par hoga. Apni chosen city/date ko permanent product assumption nahi bana sakte.

Public dataset availability useful hai, lekin resolution aur temporal coverage ko task ke against verify karna hoga. PS ka vehicle-concentration example har public image resolution par feasible nahi maana ja sakta. Yeh engineering risk hai, data availability ka verified claim nahi.

## 4. Evaluation se kya samajh aata hai

**Official:** Retrieval unseen semantic queries aur relevance judgements par evaluate hoga. Change analysis unseen labelled change/no-change cases par evaluate hoga.

**Team inference:** Rehearsed screenshots se zyada valuable repeatable behaviour hai. Humein relevant retrieval, hard negatives, uncertainty handling aur offline reproducibility ka evidence chahiye. Exact scoring weights aur numerical pass thresholds PS description mein specified nahi hain; hum invent nahi karenge.

**Proposed internal measurements — organiser metrics nahi:**

| Area | Hum kya measure kar sakte hain |
|---|---|
| Retrieval | Precision@k and/or nDCG@k on withheld, independently judged queries; text and image queries separately |
| Change | Precision/recall, confusion by supported class, false positives on no-change cases; localisation metric if labels support it |
| Timing | Earliest supported observation ki correctness; dates ke beech unknown interval clearly stated |
| System | Index area, scenes/tiles, build time, storage, query latency, hardware; incremental ingestion time |
| Workflow | Saved review survives reopen; exported evidence resolves to original scene and processing history; offline demo succeeds |

Internal evaluation set tuning/demo cases se separate rakhenge. Metrics ke saath sample count, label process aur known limitations report karenge. Targets representative data aur baseline ke baad set honge.

## 5. First end-to-end demo — team proposal

1. Small, clearly documented public imagery archive locally ingest karo, with multiple dates and usable metadata.
2. Text search se ranked candidates dikhao; metadata filter apply karo.
3. Reference-image search aur a selected site se similar locations dikhao.
4. Candidate ke dated observations inspect karke supported change aur earliest evidence dikhao.
5. Cloud/season/alignment jaise confounder wala no-change example dikhao; weak evidence par uncertainty explain karo.
6. Analyst confirm/reject kare; saved decision aur provenance-rich export inspect karo.
7. Nayi acquisition ingest karke search update dikhao, without complete index rebuild.
8. Staged machine par network disable karke complete workflow repeat karo.

Yeh first complete slice hai. Supported classes aur imagery scale evidence ke according narrow ho sakte hain, par missing core capability ko optional bolkar hide nahi karenge. Unimplemented features ko honestly label karenge.

## 6. Sabse pehle resolve hone wale risks

| Open question | First investigation / decision evidence |
|---|---|
| Required concepts image resolution par visible hain? | Candidate public scenes inspect; query concepts vs sensor/resolution table |
| Enough usable dates and genuine change/no-change cases milte hain? | Cloud/quality/coverage check with independent labels |
| Text and image embeddings local data par relevant hain? | Small baseline retrieval evaluation before model commitment |
| Seasonal and sensor differences false alarms bana rahe hain? | Confounder-heavy no-change baseline; alignment/quality checks |
| Offline hardware par pipeline fit hoti hai? | Actual RAM/VRAM/storage/build/query measurements; hardware still to be confirmed |
| Organiser formats, area, time span and evaluation details kya honge? | Track official clarifications; leave configurable and mark unknowns |

## 7. Submission checklist from official PS

- Source code and architecture note.
- Index-build and incremental-ingestion procedure.
- Model and dataset provenance, including applicable licences and offline weights.
- Reproducible evaluation report: indexed area, scene/tile count, build time, storage footprint, query latency and hardware.

## 8. Team ka first meeting outcome

Har teammate apne words mein user, problem aur six capabilities explain kar sake. Requirements table ke har row par ek owner aur first proof assign ho; assignments team availability ke baad fill honge. Sab agree karein ki kaunsi baat official hai, kaunsi proposal hai aur kaunsi abhi unknown hai.

**Next concrete step:** Existing project ka isi matrix ke against evidence-based gap audit: working / partial / absent / unverified. Uske baad data feasibility aur measured baseline se architecture decisions lenge. Existing code ko inspect kiye bina keep/rewrite ka verdict nahi.

**Our proposed winning thesis:** Analyst ko useful discovery, trustworthy change evidence aur reproducible offline operation ek coherent workflow mein dena. Yeh strategy hai, winning guarantee ya official scoring formula nahi.
