# MIE P0 Colab Validation

- Repository: `edu-moraess/vyra-maritime-intell`
- Branch: `feat/mie-p0-operational-reliability`
- Expected implementation commit: `104e7e99b8628a468472d4546a0d31e08db16010`
- Baseline: `5bbe456f657bd4524e71937cf73da420db4f0898`

Run the following as **one Colab cell**. It creates a separate checkout and does not overwrite the existing `/content/mie_recovery` working directory.

```python
from pathlib import Path
import subprocess
import sys

REPO_URL = "https://github.com/edu-moraess/vyra-maritime-intell.git"
BRANCH = "feat/mie-p0-operational-reliability"
EXPECTED_HEAD = "104e7e99b8628a468472d4546a0d31e08db16010"
WORKDIR = Path("/content/mie_p0_validation")

if WORKDIR.exists():
    raise RuntimeError(
        f"{WORKDIR} already exists. Preserve it and choose a new WORKDIR path in this cell; "
        "the validator will not delete or overwrite an existing checkout."
    )

def run(command):
    print("\\n$", " ".join(map(str, command)), flush=True)
    subprocess.run(command, check=True)

run(["git", "clone", "--branch", BRANCH, "--single-branch", REPO_URL, str(WORKDIR)])
actual_head = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=WORKDIR, text=True
).strip()
if actual_head != EXPECTED_HEAD:
    raise RuntimeError(f"Unexpected branch commit: {actual_head}; expected {EXPECTED_HEAD}")

run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"])
run([sys.executable, "scripts/validate_p0.py"])

print("\\nP0 deterministic validation completed.")
print("Checkout:", WORKDIR)
print("Commit:", actual_head)
print("LIVE_AIS_30_MINUTE_ACCEPTANCE=NOT_RUN")
print("FULL_REPOSITORY_SUITE=NOT_RUN")
```

## What this gate proves

The script runs:
- patch whitespace/integrity check against the recorded baseline;
- Python compilation for `app.py`, `src/`, and `tests/`;
- deterministic P0 regression tests for worker lifecycle, engine integration, AIS provider states, stale map presentation, canonical metrics, temporal availability, environmental failure semantics, runtime settings, and process-wide engine ownership.

## What this gate does not prove

A PASS does **not** establish:
- 30-minute uninterrupted AISStream operation;
- successful recovery from a real network interruption;
- browser navigation persistence across multiple real user sessions;
- exclusivity across separate Python processes or deployment replicas;
- production readiness.

After this gate passes, run the complete repository suite and then perform the 30-minute live-network acceptance test with real deployment credentials. Record logs, timestamps, observed reconnects, queue depth/drops, and vessel freshness. Do not merge to `main` until all gates are evidenced.
