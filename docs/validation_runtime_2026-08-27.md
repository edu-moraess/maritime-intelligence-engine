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
