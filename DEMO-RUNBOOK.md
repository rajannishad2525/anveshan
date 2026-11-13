# ANVESHAN operator demo

This runbook exercises the offline workflow without a terminal after the local server is started.

1. Run `run_offline.ps1` once and open `http://127.0.0.1:8765/`.
2. In **Data Library**, enter an imagery folder and choose **SCAN FOLDER**. Use a folder containing GeoTIFF/COG files and sidecar JSON when available.
3. In **Search & Discover**, search by filename, sensor or date. Each result can be sent to comparison.
4. In **Compare Timeline**, use **SUGGEST PAIRS**, inspect the two source previews, then run the change screening. Read quality flags before treating a candidate as evidence.
5. Use **SHOW FOOTPRINTS** when sidecar `bbox`, `footprint` or `geometry` metadata exists. A missing footprint remains unverified.
6. In **Review Queue**, record accepted, rejected or needs-review decisions with a reason.
7. Export the scene provenance JSON for a reproducible evidence record.
8. For evaluation, prepare a local CSV with `before,after,label` where label is `change` or `no-change`, then run the benchmark from the Evaluation workspace or with `scripts/evaluate_manifest.py`.

The current change score is a screening baseline. It does not claim semantic understanding, object classification or military intelligence. Final accuracy claims require a held-out labelled set and should be reported with precision, recall, F1 and false alarm rate.
