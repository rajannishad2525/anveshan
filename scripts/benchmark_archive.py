"""Export measurements from a running local workstation; does not import/build data."""

import argparse
import json
from pathlib import Path
import urllib.request
from urllib.parse import urlparse

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8773")
parser.add_argument("--output", type=Path, default=Path("benchmark-output"))
args = parser.parse_args()
if urlparse(args.url).hostname not in {"127.0.0.1", "localhost", "::1"}:
    parser.error("Use the local offline workstation address")
request = urllib.request.Request(
    args.url.rstrip("/") + "/api/benchmark/current",
    data=b"{}",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(request, timeout=300) as response:
    report = json.load(response)
args.output.mkdir(parents=True, exist_ok=True)
(args.output / "benchmark.json").write_text(
    json.dumps(report, indent=2), encoding="utf-8"
)
(args.output / "benchmark.md").write_text(
    "# Measured archive benchmark\n\n"
    + "\n".join(
        f'- {key}: {value if value is not None else "not measured"}'
        for key, value in report.items()
    ),
    encoding="utf-8",
)
print(json.dumps(report, indent=2))
