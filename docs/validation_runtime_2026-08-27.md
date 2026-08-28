# Runtime validation — 2026-08-27

A local Streamlit instance was started from the repository on port 8501. The health endpoint returned `ok`.

The fresh Overview rendered successfully without a configured AISStream key. The sidebar showed the Miami real Bounding Box preset, the collection-window control, server-side key status `NOT CONFIGURED`, and the Overview showed `DISCONNECTED`, zero real messages, zero vessels, `COLLECTION —`, `TRACKS WITH HISTORY 0/3`, `EMBEDDINGS WAITING`, and explanatory empty states. No synthetic vessel, mock traffic, or fallback dataset appeared.


The second browser pass confirmed all nine workspace radio tabs are present, the collection selector displays `60 seconds`, the region expander opens, and the real Miami preset displays its Bounding Box. The application remained in the explicit disconnected/empty state without rendering data.


The collection combobox visibly exposed exactly four options: `30 seconds`, `60 seconds`, `120 seconds`, and `180 seconds`. Two automated attempts to select `120 seconds` did not persist because the Streamlit ARIA combobox rerendered its trigger between interactions; this is recorded as an interaction-tool limitation, not as evidence that the option is missing. The same value path is covered by unit tests (`test_collection_duration_options_are_preserved` and `test_engine_passes_selected_collection_duration_to_provider`).


After the combobox rerender, a browser view confirmed `120 seconds` persisted in the sidebar. The Vessels tab then rendered successfully and showed the explicit real-AIS empty state with zero observed vessels and no runtime exception.


The Vessel Intelligence tab rendered `NO TARGET SELECTED` with an explanatory real-AIS message. Trajectory Analysis rendered `NO TRAJECTORY SELECTED` with the same safe guidance. Both tabs loaded without runtime or DOM errors while the provider was disconnected.


Behavior rendered the scientific guard `Current: 0/3` for three distinct vessels with sufficient trajectory history. Anomalies rendered zero findings with an explicit statement that no finding is fabricated when data is insufficient. Both loaded without errors.


Traffic rendered no charts when there were no real observations, showing the explicit unavailable state. Data Quality rendered the full validation table, `100.0%` for an empty processed set, and the explicit `NO REAL AIS OBSERVATIONS` message with a note that no unobserved data is estimated.


System rendered the server-side AISStream pipeline, closed WebSocket state, configured Bounding Box and the explicit no-fabrication message. Browser console inspection returned no console output/errors during the navigation pass.


The region combobox visibly exposed six choices: Miami, Santos, Singapore, Rotterdam, English Channel and Custom. An automated click on Santos did not persist because the dynamic ARIA widget rerendered its trigger; unit tests validate the preset catalog and Bounding Box semantics, while no browser result is being claimed for the actual region transition.


Follow-up inspection showed that the Santos selection did persist after the Streamlit rerun. The sidebar displayed `Santos · -24.200, -46.800 → -23.700, -46.000`, and the app showed both the in-expander message and the top notice explaining that the previous session was cleared and a new real AIS collection is required. This supersedes the earlier transient interaction note for the actual region transition.


## P0/P1 consolidation validation

A fresh Streamlit instance on port 8502 booted successfully after restarting the process, avoiding stale module state from the previous process. The compact sidebar displayed `SESSION / CONTROL`, collection duration `60 s`, `Collect Real AIS`, `Clear Session`, a collapsed `REGION` Bounding Box control, essential `CONNECTION` state `NOT CONFIGURED`, and five workspace modules: Overview, Vessels, Movement & Behavior, Anomalies & Traffic, and Data & System.

The Overview rendered `DISCONNECTED`, zero real observations, `TRACKS WITH HISTORY 0/3`, and explicit `WAITING` states for trajectory and multitrack analyses. No synthetic traffic or fallback layer appeared.


## Navigation consolidation validation

The consolidated `Movement & Behavior` module exposed the subareas `Trajectory Analysis`, `Behavior` and `Similarity`. Trajectory Analysis rendered its existing no-target state, and Similarity rendered `NO REFERENCE TRACK` with guidance to collect real AIS data, without runtime errors.


The `Anomalies & Traffic` module exposed both subareas. Anomalies rendered zero findings with its no-fabrication explanation, and Traffic rendered the existing explicit unavailable state without charts when no real observations were present.


The `Data & System` module exposed both `Data Quality` and `System`. Data Quality rendered its full empty-session quality table, while System rendered the server-side AISStream pipeline and `DISCONNECTED` state without exceptions.


## Sidebar collapse validation

The native Streamlit sidebar control hid the sidebar, expanded the main content area, and exposed the corresponding reopen control. Reopening restored the compact sidebar and its five-module navigation. No custom JavaScript or DOM hack was used.


## P0 missing-vessel-name validation

All previous Streamlit processes were stopped by PID and a new clean instance started on port 8503. Its health endpoint returned `ok`. The fresh Overview booted without traceback or ImportError, showed `Collection duration · 60 s`, `Collect Real AIS`, `Clear Session`, the five consolidated modules, `NOT CONFIGURED`, `DISCONNECTED`, zero observations and the existing `WAITING` readiness state. No synthetic data appeared.


## Missing vessel-name regression validation

In the clean Streamlit instance, `Vessels` exposed `Fleet` and `Vessel Intelligence`; both loaded without traceback and showed safe empty states while AIS was not configured. The `vessel_name=None`, empty and whitespace cases are covered by the automated `_vessel_label` regression test because the disconnected runtime must not fabricate vessels merely to exercise the UI.


After the P0 fix, the clean instance navigated through Vessels/Fleet and Vessel Intelligence without traceback. Browser console inspection produced no errors. The collection-duration combobox exposed exactly `30 s`, `60 s`, `120 s` and `180 s`, with 60 s selected by default.


The clean instance navigated from Vessels to `Movement & Behavior`; its subareas remained visible and `Trajectory Analysis` loaded with the expected `NO TRAJECTORY SELECTED` state, without traceback.


The clean instance navigated through `Behavior` and `Similarity`. Behavior showed the unchanged three-track gate (`Current: 0/3`), and Similarity showed `NO REFERENCE TRACK` with real-AIS guidance. Both pages loaded without traceback.


The current clean instance exposed `Anomalies` and `Traffic` under `Anomalies & Traffic`. Anomalies showed zero findings with the explicit no-fabrication message, and Traffic showed `REAL AIS DATA UNAVAILABLE` with zero metrics and no artificial charts.


The clean instance exposed `Data Quality` and `System` under `Data & System`. Data Quality showed its empty-session quality table and `NO REAL AIS OBSERVATIONS`; System showed the AISStream server-side pipeline, `DISCONNECTED`, zero messages and no traceback.


A verificação final do console do navegador não registrou saída ou erros após a navegação completa pelas áreas principais e subáreas na instância limpa.


## Temporal semantics validation — clean instance

A fresh Streamlit instance on port 8504 booted successfully after stopping the previous process; its health endpoint returned `ok`. The Overview displayed `LAST RECEIVED = UNAVAILABLE` with no AIS key, `NOT CONFIGURED`, `DISCONNECTED`, zero observations, `WAITING` readiness, and no synthetic traffic. The sidebar exposed `DISPLAY` with operator timezone default `UTC`, while Collection duration remained 60 s and the five consolidated modules remained available.


The clean Overview timezone selector exposed exactly six controlled presentation options: UTC, America/Sao_Paulo, America/New_York, Europe/London, Europe/Amsterdam and Asia/Singapore. UTC was the default; the selector is presentation-only and does not alter canonical AIS data.


The operator timezone combobox exposed all six controlled IANA options. Native option selection was not persisted by the ARIA wrapper, but direct combobox input successfully applied and persisted `America/New_York`; the Overview remained in the safe no-AIS state with no data changes.


The temporal-clean instance loaded `Data Quality` under `Data & System` with `LAST RECEIVED = UNAVAILABLE`, zero messages, the full quality table and `NO REAL AIS OBSERVATIONS`; no traceback occurred. The operator timezone selection remained `America/New_York` without changing canonical data.


The clean instance loaded `System` with `MESSAGES RECEIVED`, `LAST RECEIVED = UNAVAILABLE`, `AIS UTC SECOND = UNAVAILABLE`, `Observation time = UNAVAILABLE` and `Latency = UNAVAILABLE`. AISStream remained server-side, `DISCONNECTED`, with zero messages and no fabricated traffic.


The clean temporal instance loaded `Fleet` and `Vessel Intelligence` under `Vessels` without traceback. Both displayed the expected real-AIS empty states with no fabricated vessel rows; the new vessel time fields were not exercised in the UI because no API key was configured.


The temporal-clean instance loaded `Trajectory Analysis` and `Behavior` under `Movement & Behavior` without traceback. Behavior showed `INSUFFICIENT REAL AIS DATA` with `Current: 0/3`, preserving the existing multitrack gate and no-data policy.


The clean temporal instance loaded `Similarity` with `NO REFERENCE TRACK` and `Anomalies` with `NO BEHAVIORAL ANOMALIES`; both preserved real-AIS gates and rendered no fabricated values.


The clean temporal instance loaded `Traffic` with `REAL AIS DATA UNAVAILABLE`, zero metrics and no charts in the no-key state. Final browser console inspection produced no errors after the complete navigation pass.


## Final temporal clean boot

After the final code changes, all prior Streamlit processes were stopped and a new instance was started on port 8505. The health endpoint returned `ok`; the Overview loaded without traceback or ImportError. It displayed `LAST RECEIVED = UNAVAILABLE`, operator timezone `UTC`, `NOT CONFIGURED`, `DISCONNECTED`, zero real messages, `WAITING` readiness and the explicit no-fabrication empty state.
