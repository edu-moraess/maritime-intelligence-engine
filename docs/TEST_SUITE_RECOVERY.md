# Test Suite Recovery

Temporary engineering checkpoint for the seven pre-existing failures reported by the local validation of `main` at commit `72382f15fd26ddea0ffe82794868d3923e8040fe`.

Known failures:
- `tests/test_gemini_llm.py` — 2 failures related to `EngineSnapshot` construction / optional fields
- `tests/test_historical_migrations.py` — 1 failure in migration statement splitting/count
- `tests/test_presentation_helpers.py` — 1 failure in map render contract
- `tests/test_temporal_diagnostics.py` — 1 failure in sliding-window count
- `tests/test_temporal_publish.py` — 2 failures in preprocessing/shape and trainer/sequences

Scope:
- Diagnose the actual current failure in each test before editing.
- Make the smallest compatibility/correctness fix required.
- Preserve real-AIS-only behavior.
- Do not change anomaly-model semantics.
- Do not add new ML models or product features.
- Do not restore GitHub Actions.
- Do not touch experimental PRs #45 or #47.
- Add focused regression coverage only where the existing test does not adequately protect the corrected behavior.

Acceptance target:
- `python -m compileall -q src tests` passes.
- `git diff --check` passes.
- Full `pytest -q` reaches 0 failures.
- No new failures are introduced.
