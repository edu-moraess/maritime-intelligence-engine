# Technical audit record

This document records findings from the repository audit requested on 2026-08-27.

## Findings identified so far

| Area | Finding | Severity | Resolution status |
| --- | --- | --- | --- |
| Bounding Box | `DEFAULT_BBOX` used the AISStream corner order instead of semantic `(min, max)` names, and `_validate_bbox` allowed reversed limits. | High | Corrected in source; tests added |
| Runtime configuration | Partial or invalid environment/Secret Bounding Box values were silently replaced by defaults. | High | Corrected to retain `config_error` and block collection |
| Provider selection | A non-AISStream provider value could still reach the AISStream client when an API key existed. | High | Corrected in `AppSettings.from_runtime` |
| AIS timestamp | AIS `Timestamp` was interpreted as a Unix epoch even though it is the second within the UTC minute. | High | Corrected: receipt time is used for freshness/order and AIS second is retained separately |
| Parser validation | Missing `Valid` could default to true; MMSI and numeric field bounds were loose. | High | Corrected with strict PositionReport validation |
| Session store | Duplicate payloads were retained without a stable duplicate count, and storage did not enforce the vessel limit. | Medium | Corrected with bounded deduplicating store |
| Map | The current monitoring region was not visibly outlined. | Medium | Corrected with a Bounding Box PathLayer |
| Similarity provenance | Session tracks could appear with a `HISTORICAL AIS` default label. | High | Corrected to `REAL AIS SESSION` |
| Streamlit runtime | The refreshed app exposed an import error because the rewritten engine lacked the `create_engine` factory expected by `app.py`. | High | Resolved and validated after clean restart |

The runtime fix was completed and validated. No AIS synthetic or fallback data was introduced.

## Runtime validation checkpoint

The first browser reload exposed two issues caused by the in-progress source rewrite: the existing Streamlit process retained an older imported `AppSettings`, and the rewritten engine temporarily lacked the `create_engine` factory expected by `app.py`. The factory was restored, direct imports passed, and the process was fully restarted from the repository source. A fresh browser session subsequently rendered the hotfixed Overview and Vessels pages without runtime or DOM errors.

## Clean boot validation

After a full process restart, the Streamlit app booted without import or runtime errors. The sidebar now displays the semantically ordered default region: Min latitude `25.60300`, Min longitude `-80.20800`, Max latitude `25.83500`, Max longitude `-79.87900`. With no credential, the app reports `DISCONNECTED: AISSTREAM_API_KEY is not configured.`, renders zero targets, and shows `REAL AIS DATA UNAVAILABLE` without fabricated traffic.

## Bounding Box UI validation

The Monitoring region expander exposes the corrected default values. A browser test entered `Min latitude = 30` while `Max latitude = 25.835`; Streamlit displayed `Press Enter to apply` and held the invalid candidate for validation. The edit will be applied next to confirm that the error is rejected and collection remains disabled.

## Bounding Box recovery validation

After the invalid reversal was applied, the UI displayed `min_lat must be strictly less than max_lat.`, set the engine status to `DISCONNECTED` with the same reason, and showed no data. Restoring Min latitude to `25.603` removed the validation error and returned the app to the expected disconnected state caused only by the missing AISStream key. This confirms that invalid regions do not trigger collection and valid edits recover cleanly.

## Region propagation validation

A valid change to Max longitude (`-79.878`) produced the required `Region updated. Collect again to open a new subscription.` message. The sidebar retained the new value while the provider stayed safely disconnected because no key was configured; no old observations or old-region vessels appeared. This validates the UI → AppSettings → engine/provider configuration path in the no-data state.

## Published-rendering hotfix

The published URL currently returns Streamlit's `Oh no. Error running app.` page, while the reported browser-side failure was `Failed to execute 'removeChild'`. The UI audit found cross-element raw HTML panel wrappers (`<div class='panel'>` opened in one Streamlit element and closed in another) in `src/ui/pages.py`; these wrappers can leave Streamlit's virtual DOM with nodes it no longer owns during reruns. The hotfix removes those wrappers while retaining balanced, single-element HTML for labels, notices, and CSS. The local process was restarted for browser validation, and the repository still contains no synthetic provider or fallback data.

The first post-hotfix browser capture did not provide a reliable application view: navigation returned transient controls, then the follow-up view was on `about:blank` with no DOM. This is treated as a browser-session capture issue, not evidence of an application exception; the local health endpoint and automated tests remain passing. A fresh navigation will be used for confirmation.

## DOM-hotfix validation

A fresh local browser session now renders the complete Overview without exceptions. It shows the corrected Bounding Box values, `DISCONNECTED` plus `REAL AIS DATA UNAVAILABLE` when no key is configured, and zero observations. Navigating to Vessels triggers a Streamlit rerun and renders its empty state cleanly. No `removeChild` error or runtime exception appeared during this validation pass.

## Streamlit Cloud dependency-manifest hotfix

The deployment log showed `apt-get` attempting to install the words from a comment in `packages.txt` (`#`, `No`, `OS`, `packages`, and so on). The file was corrected to an empty manifest because this project requires no operating-system packages. The resulting manifest contains no apt package tokens, while `pytest -q` passes all 34 tests and Python compilation remains clean.
