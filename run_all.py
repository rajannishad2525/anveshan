"""Recreate derived paper tables and figures from the frozen raw evaluation.

Run with the staged experiment Python:
  C:/Users/abcom/Downloads/anveshan/.venv/Scripts/python.exe -B run_all.py

This intentionally does NOT rerun the test split. Re-running test after looking
at results would defeat the one-shot freeze. To reproduce from scratch, use an
independent checkout and documented OSCD/config/checkpoint before inspection.
"""
import subprocess,sys
from pathlib import Path

root=Path(__file__).resolve().parent
required=[root/'results/oscd_full_v2/summary.json',root/'results/oscd_full_v2/raw_tile_scores.csv']
if not all(p.is_file() for p in required):
    raise SystemExit('Frozen raw evaluation missing. Review eval/oscd_full.py and configs/oscd_full.json before any fresh run.')
commands=['eval/baselines_random.py','eval/bootstrap_ci.py','eval/retrieval_chance.py',
          'tools/generate_paper_artifacts.py','tools/check_numbers.py']
for script in commands:
    print('RUN',script,flush=True)
    subprocess.run([sys.executable,'-B',str(root/script)],cwd=root,check=True)
print('Derived paper artifacts regenerated; frozen full-OSCD test was not rerun.')
