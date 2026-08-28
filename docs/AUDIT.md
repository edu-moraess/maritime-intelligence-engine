Technical Audit Record

Audit scope: Maritime Intelligence Engine (MIE)
Repository: "edu-moraess/maritime-intelligence-engine"
Initial audit date: 2026-08-27
Latest documented update: 2026-08-28
Branch: "main"

This document records technical findings, corrective actions, runtime validation checkpoints, architectural decisions, and integrity constraints identified during the MIE repository audit.

The purpose of this document is to provide an evidence-oriented record of what was identified, what was corrected, and what remains subject to further validation.

---

1. Executive Summary

The audit identified several issues affecting configuration safety, geographic semantics, AIS timestamp interpretation, parser strictness, session storage, UI state, and runtime compatibility.

The identified issues were addressed through source changes and corresponding validation.

No synthetic AIS provider or fabricated vessel fallback was introduced as part of the remediation.

The current validation boundary remains explicit:

«Local technical validation has passed. Live AIS validation after deployment remains dependent on valid AISStream credentials and a successful real-data collection session.»

---

2. Audit Findings

Area| Finding| Severity| Resolution
Bounding Box| "DEFAULT_BBOX" used AISStream corner ordering instead of semantic "(min, max)" names, and "_validate_bbox" allowed reversed limits.| High| Corrected in source; tests added
Runtime configuration| Partial or invalid environment/Secret Bounding Box values could silently fall back to defaults.| High| Corrected to retain "config_error" and block collection
Provider selection| A non-AISStream provider value could reach the AISStream client when an API key existed.| High| Corrected in "AppSettings.from_runtime"
AIS timestamp| AIS "Timestamp" was interpreted as a Unix epoch even though it represents the second within the UTC minute.| High| Corrected; receipt time is used for freshness/order
Parser validation| Missing "Valid" could default to true; MMSI and numeric bounds were insufficiently strict.| High| Corrected with strict "PositionReport" validation
Session store| Duplicate payloads were retained without stable duplicate accounting, and vessel limits were not enforced.| Medium| Corrected with bounded deduplicating storage
Map| Current monitoring region was not visibly outlined.| Medium| Corrected with Bounding Box "PathLayer"
Similarity provenance| Session tracks could appear with a "HISTORICAL AIS" label.| High| Corrected to "REAL AIS SESSION"
Streamlit runtime| Rewritten engine temporarily lacked the "create_engine" factory expected by "app.py".| High| Factory restored; clean restart validated

---

3. Runtime Compatibility Audit

During the source rewrite, the first browser reload exposed two runtime issues:

1. the running Streamlit process retained an older imported "AppSettings";
2. the rewritten engine temporarily lacked the "create_engine" factory expected by "app.py".

The factory was restored and direct imports passed.

The Streamlit process was then fully restarted from the repository source.

A fresh browser session subsequently rendered the hotfixed Overview and Vessels pages without the previously observed runtime or DOM errors.

---

4. Clean Boot Validation

After a complete process restart:

- the Streamlit application booted without import errors;
- the application rendered the unified MIE shell;
- the default region was displayed using semantic minimum/maximum ordering;
- the application correctly reported the missing AISStream credential;
- zero targets were shown;
- no fabricated traffic was introduced.

The validated default region was:

Parameter| Value
Min latitude| "25.60300"
Min longitude| "-80.20800"
Max latitude| "25.83500"
Max longitude| "-79.87900"

Without credentials, the expected state is:

DISCONNECTED
AISSTREAM_API_KEY is not configured.
REAL AIS DATA UNAVAILABLE

This is considered the correct safe state.

---

5. Bounding Box Validation

Invalid configuration

The Monitoring interface was tested with:

Min latitude = 30
Max latitude = 25.835

The application correctly rejected the reversed range with:

min_lat must be strictly less than max_lat.

The engine remained disconnected and no collection was initiated.

Recovery

Restoring:

Min latitude = 25.603

removed the validation error and returned the application to the expected disconnected state caused by the missing AISStream credential.

This confirms that invalid geographic regions do not trigger collection and that valid corrections recover cleanly.

---

6. Region Propagation

A valid change to Max longitude:

-79.878

produced:

Region updated. Collect again to open a new subscription.

The sidebar retained the new value while the provider remained safely disconnected because no AISStream key was configured.

No observations from the previous region were presented as belonging to the new region.

The valid configuration path is therefore:

Monitoring UI
      ↓
AppSettings
      ↓
Engine configuration
      ↓
Provider / subscription

A valid region change creates a fresh provider/store session before the next subscription.

---

7. Published Rendering and DOM Hotfix

The published application initially returned Streamlit's:

Oh no. Error running app.

The associated browser-side failure was:

Failed to execute 'removeChild'

The UI audit identified cross-element raw HTML panel wrappers in "src/ui/pages.py".

The problematic pattern consisted of HTML elements being opened in one Streamlit element and closed in another. This could leave the Streamlit virtual DOM attempting to manipulate nodes that it no longer owned during reruns.

The hotfix removed those cross-element wrappers while retaining balanced, single-element HTML where required for labels, notices, and CSS.

---

8. DOM-Hotfix Validation

A fresh local browser session subsequently rendered the complete Overview page without exceptions.

The validated state included:

- corrected Bounding Box values;
- "DISCONNECTED" status;
- "REAL AIS DATA UNAVAILABLE";
- zero observations;
- successful navigation to Vessels;
- clean Streamlit rerun.

No "removeChild" error or runtime exception appeared during the validation pass.

An earlier browser capture that ended on "about:blank" was treated as a browser-session capture issue rather than application evidence because the local health endpoint and automated tests remained passing.

---

9. Streamlit Cloud Dependency Manifest

The deployment log showed "apt-get" attempting to interpret comment text in "packages.txt" as operating-system packages.

The manifest was corrected to an empty package manifest because the current project does not require additional OS-level packages.

The resulting manifest contains no unintended apt package tokens.

The correction was followed by:

pytest -q
34 passed

and successful Python compilation validation.

---

10. AIS Parsing and Data Integrity

The audit identified overly permissive AIS parsing behavior.

The parser was strengthened to validate:

- "PositionReport" structure;
- "Valid";
- MMSI;
- numeric field ranges;
- geographic values;
- required position information.

The system rejects invalid JSON, invalid UTF-8, unsupported message types, and invalid position records rather than silently converting them into observations.

No synthetic observations are introduced when parsing or ingestion fails.

---

11. Session Store Integrity

The session store was corrected to provide bounded storage behavior.

The remediation includes:

- duplicate detection;
- stable duplicate accounting;
- bounded message storage;
- bounded vessel storage;
- trajectory sufficiency checks.

This prevents unbounded growth of the live session state and avoids treating duplicate AIS payloads as independent observations.

---

12. Operational Prototype Extension

The operational prototype now exposes collection windows of:

30 seconds
60 seconds
120 seconds
180 seconds

with 60 seconds as the default.

The selected duration is propagated from the sidebar through:

Sidebar
   ↓
MaritimeIntelligenceEngine.collect()
   ↓
AISStream WebSocket collection window

The previous 10-second configuration clamp was removed and replaced with explicit 30–180 second bounds.

The Overview reports:

- effective collection duration;
- real messages received;
- distinct vessels;
- tracks containing at least two real "PositionReport" observations;
- embedding status;
- anomaly count.

Behavior, Similarity, and ML Anomaly readiness remains gated by the availability of sufficiently long real tracks.

Empty states explain the analytical requirements and may suggest longer real collection windows or denser real monitoring regions.

They do not suggest simulated data.

---

13. Geographic Presets

The sidebar provides real-region Bounding Box presets for:

- Miami;
- Santos;
- Singapore;
- Rotterdam;
- English Channel;
- Custom.

A valid region change creates a fresh provider/store session and requires a new collection before observations are displayed.

Regional metadata includes the appropriate IANA timezone information where applicable.

English Channel and Custom configurations follow an explicit UTC policy.

---

14. Missing Data Handling

Missing SOG values are not rendered as zero in traffic distributions or map rows.

Heading vectors are omitted when no real heading or COG is available.

This prevents missing telemetry from being converted into artificial measurements.

The principle is:

Missing value
     ↓
Represent as missing

rather than:

Missing value
     ↓
Invent a numeric value

---

15. Provider and Store Separation

The provider/store dual-state architecture was intentionally retained.

The current responsibilities are:

AIS Provider
    ↓
Live vessel/status snapshots

and:

ObservationStore
    ↓
Bounded session observations
    ↓
Tracks

This was preserved as a compatibility decision until regression coverage exists for all relevant selection, clear-session, and map-update paths.

This decision avoids introducing a broad architectural refactor without sufficient regression evidence.

---

16. Historical Data Provenance

Session tracks must not be represented as historical AIS.

The corrected provenance label is:

REAL AIS SESSION

rather than:

HISTORICAL AIS

Historical AIS claims must originate from the historical persistence layer.

This distinction is important because session persistence in memory does not establish historical provenance.

---

17. Temporal Integrity

The MIE uses UTC as its canonical storage reference.

"received_at"

"AISObservation.received_at" represents the timezone-aware UTC instant at which the MIE receives/processes an AIS frame.

It is used for:

- freshness;
- ordering;
- trajectory timing;
- Traffic grouping.

"ais_timestamp_second"

"ais_timestamp_second" retains the AIS "PositionReport.Timestamp" field as the reported second within the UTC minute.

Normal values are:

0–59

Values:

60–63

are retained as AIS special states and are not converted into fabricated datetimes.

"observed_at"

"observed_at" remains "None" because the current AISStream envelope does not establish a trusted absolute observation datetime.

"MetaData.time_utc"

"MetaData.time_utc" remains inside the raw payload and is not promoted to observation time.

---

18. Latency Integrity

Network latency is currently:

UNAVAILABLE

The previous modulo-60 pseudo-latency calculation was removed.

The system does not infer network latency from the AIS second-of-minute field because that value does not establish a trusted absolute transmission timestamp.

---

19. Timezone Presentation

UTC remains canonical for storage and analytical ordering.

Regional/operator conversions are performed using the standard-library:

zoneinfo

only at presentation time.

This keeps analytical timestamps independent from display preferences.

---

20. No Synthetic Data Policy

No synthetic AIS provider or fabricated vessel fallback was introduced.

The system follows:

Real AIS available
       ↓
Validate
       ↓
Analyze
       ↓
Display

When real AIS data is unavailable:

AIS unavailable
       ↓
Explicit unavailable / insufficient-data state

not:

AIS unavailable
       ↓
Fabricated vessel traffic

This is a deliberate project integrity constraint.

---

21. Machine Learning and Deep Learning Scope

The current behavioral analytics remain based on the implemented pipeline.

Deep Learning was not added as part of the audit remediation.

Future Deep Learning work remains conditional on:

- a real historical dataset;
- documented data provenance;
- train/validation/test separation;
- reproducible evaluation;
- appropriate validation methodology.

The absence of a pretrained checkpoint is explicitly represented rather than hidden or replaced with an unverified model.

---

22. No Fabricated Intelligence

The MIE does not fabricate:

- AIS observations;
- vessel positions;
- trajectories;
- historical records;
- behavioral findings;
- embeddings;
- timestamps;
- network latency.

Analytical outputs remain bounded by the evidence available to the system.

An anomaly is an analytical signal for investigation, not proof of malicious intent.

---

23. Validation Boundary

The audit and local validation establish evidence for the tested application state.

They do not establish successful production AIS operation.

Live operational validation still requires:

1. a valid AISStream API key;
2. Streamlit Secrets configuration;
3. valid "AIS_AREA_*" values;
4. a deployed application;
5. a successful collection window;
6. receipt of real AIS observations;
7. confirmation that real vessels and trajectories are rendered correctly.

The deployment procedure is documented in:

""STREAMLIT_DEPLOY.md"" (STREAMLIT_DEPLOY.md)

---

24. Current Audit Status

Corrected and validated

- Bounding Box semantic ordering;
- Bounding Box validation;
- runtime configuration safety;
- provider selection;
- AIS timestamp semantics;
- strict AIS parsing;
- bounded session storage;
- duplicate handling;
- map region visualization;
- AIS provenance labeling;
- Streamlit engine compatibility;
- Streamlit clean boot;
- DOM hotfix;
- dependency manifest;
- temporal integrity;
- missing-value handling;
- no-synthetic-data policy.

Remaining validation

- live AISStream authentication;
- production collection with real AIS;
- end-to-end deployed validation;
- long-running operational stability;
- historical behavioral baselines;
- expanded vessel identity enrichment.

---

25. Audit Conclusion

The audit identified and addressed multiple high- and medium-severity engineering issues across configuration, ingestion, temporal semantics, storage, visualization, and runtime compatibility.

The remediation was performed without introducing synthetic operational data.

The current evidence supports the following engineering statement:

«The MIE has undergone documented local technical validation and corrective auditing. Production live-AIS validation remains explicitly pending until a deployed instance successfully receives and processes real AISStream observations.»

This distinction is intentional and forms part of the project's data-integrity and scientific-validation policy.