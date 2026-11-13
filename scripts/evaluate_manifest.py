"""Run the offline labelled change/no-change benchmark from a CSV or JSON manifest."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import evaluate_manifest_file

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('manifest', help='CSV/JSON file with before,after,label columns')
parser.add_argument('--pixel-threshold', type=float, default=0.18)
parser.add_argument('--change-ratio-threshold', type=float, default=0.03)
args = parser.parse_args()
print(json.dumps(evaluate_manifest_file(args.manifest, args.pixel_threshold, args.change_ratio_threshold), indent=2))
