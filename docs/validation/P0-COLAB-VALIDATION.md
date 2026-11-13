# P0 Colab Validation

This is the first deterministic validation gate for `feat/mie-p0-operational-reliability`.

It intentionally does **not** run model-training tests or open a real AIS connection. It compiles the application and executes only the P0 regression tests for worker lifecycle, engine integration, provider states, map freshness, metrics, temporal availability, environmental failure semantics, and process-wide engine ownership.

Run this as one Colab cell in the existing checkout:

```python
from pathlib import Path
import subprocess

REPO = Path("/content/mie_recovery")
BRANCH = "feat/mie-p0-operational-reliability"

if not (REPO / ".git").exists():
    raise RuntimeError(f"Expected an existing Git checkout at {REPO}")

def run(command):
    print("\n$", " ".join(command), flush=True)
    subprocess.run(command, cwd=REPO, check=True)

run(["git", "fetch", "origin", BRANCH])
run(["git", "checkout", BRANCH])
run(["git", "pull", "--ff-only", "origin", BRANCH])
run(["git", "rev-parse", "HEAD"])
run(["python", "scripts/validate_p0.py"])
```

## Acceptance interpretation

- `TARGETED_VALIDATION=PASS`: deterministic P0 regression suite and Python compilation passed in this checkout.
- It does **not** establish 30-minute AIS uptime, network reconnect behavior against AISStream, multi-session browser behavior, replica exclusivity, or production readiness.
- After this gate passes, run the complete repository suite in a separate step and then perform the 30-minute live-network acceptance test with the real deployment credentials.
- Do not merge this branch to `main` until those gates are recorded with logs and timestamps.
