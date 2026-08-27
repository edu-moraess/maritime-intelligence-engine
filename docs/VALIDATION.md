# Validation record

Data: 2026-08-27. Repositório: `edu-moraess/maritime-intelligence-engine`.

## Technical checks

| Check | Result |
| --- | --- |
| `pytest -q` | Passed: 9 tests |
| `python3 -m compileall -q app.py src tests` | Passed |
| `git diff --check` before update commit | Passed |
| Streamlit health endpoint | Returned `ok` on local port 8501 |
| GitHub publication | Completed on branch `main` |
| Last pushed commit | `644434c54dc01298945609adb73fc0f13238ab2a` |

The tests cover the AISStream envelope parser, ignored non-position messages, missing credentials, coordinate and distance validation, insufficient track handling, empty anomaly output, and explicit no-pretrained-checkpoint provenance. The test suite does not provide a synthetic traffic dataset to the application.

## Visual and state checks

The local Streamlit shell was opened page by page without an AISStream credential. Overview, Vessels, Vessel Intelligence, Trajectory Analysis, Behavior, Anomalies, Traffic, Data Quality and System all rendered through the unified MIE shell. The observed state was `DISCONNECTED`, with `AISSTREAM API KEY NOT CONFIGURED`, zero observed vessels and the relevant empty or insufficient-real-data messages.

This is the expected safe state. It is not evidence of live AIS operation. A real-time validation still requires an AISStream key configured in Streamlit Secrets and a successful collection window after deployment.

## Integrity audit

The repository excludes `.env`, Streamlit secrets, local databases, caches, compiled Python artifacts and temporary files. No synthetic provider is implemented. No browser-side AISStream connection is implemented. The deployed app must never relabel session data as `HISTORICAL AIS` and must not show fabricated vessels if AISStream is unavailable.

## Remaining user action

The project is published and ready for the user to create the Streamlit Community Cloud app, configure `AISSTREAM_API_KEY` under Secrets and perform the online `LIVE AIS` verification described in `docs/STREAMLIT_DEPLOY.md`.
