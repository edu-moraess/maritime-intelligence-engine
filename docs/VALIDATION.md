# Validation record

Data: 2026-08-27. Repositório: `edu-moraess/maritime-intelligence-engine`.

## Technical checks

| Check | Result |
| --- | --- |
| `pytest -q` | Passed: 34 tests |
| `python3 -m compileall -q app.py src tests` | Passed |
| `git diff --check` | Passed |
| Streamlit health endpoint | Returned `ok` on local port 8501 |
| Streamlit clean boot | Passed after full process restart |
| Streamlit navigation rerun | Overview → Vessels rendered without runtime or DOM exception |
| Bounding Box UI reversal | Rejected with `min_lat must be strictly less than max_lat.` |
| Valid region edit | Displayed `Region updated. Collect again to open a new subscription.` |
| GitHub publication | Existing repository on branch `main`; hotfix push pending in this audit |

The tests cover strict Bounding Box limits, partial and invalid runtime configuration, exact AISStream subscription fields, documented PositionReport parsing, invalid JSON/UTF-8 and non-position rejection, AIS second-of-minute timestamp handling, real-record state transition, no-message unavailability, trajectory math and insufficient tracks, quality validation, duplicate counting, bounded message/vessel storage, missing credentials, unsupported providers, session configuration errors, and explicit no-pretrained-checkpoint provenance. The test suite does not provide a synthetic traffic dataset to the application.

## Visual and state checks

The local Streamlit shell was opened without an AISStream credential. Overview and Vessels rendered through the unified MIE shell. The observed state was `DISCONNECTED`, with `AISSTREAM API KEY NOT CONFIGURED`, zero observed vessels and the relevant empty or insufficient-real-data messages. The application exposes the corrected default region: Min latitude `25.603`, Min longitude `-80.208`, Max latitude `25.835`, Max longitude `-79.879`.

The Monitoring region controls reject reversed latitude limits and recover cleanly after a valid value is restored. A valid region change recreates the session engine before the next subscription, preventing observations from different regions from being mixed. Removing cross-element raw HTML panel wrappers eliminated the DOM-reconciliation risk associated with the reported `removeChild` failure; the hotfixed local app rendered and navigated without that exception.

This is the expected safe state. It is not evidence of live AIS operation. A real-time validation still requires an AISStream key configured by the user in Streamlit Secrets and a successful collection window after deployment.

## Integrity audit

The repository excludes `.env`, Streamlit secrets, local databases, caches, compiled Python artifacts and temporary files. No synthetic provider is implemented. No browser-side AISStream connection is implemented. AISStream `Timestamp` is retained as a second-of-minute field, while receipt time is used for freshness and ordering. The deployed app must never relabel session data as `HISTORICAL AIS` and must not show fabricated vessels if AISStream is unavailable.

## Remaining user action

After the hotfix is pushed, the user can create or refresh the Streamlit Community Cloud app, configure `AISSTREAM_API_KEY` and the four `AIS_AREA_*` values under Secrets, and perform the online `LIVE AIS` verification described in `docs/STREAMLIT_DEPLOY.md`. The agent is not performing the deployment.
