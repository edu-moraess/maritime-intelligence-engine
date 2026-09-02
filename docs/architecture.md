MIE Architecture

Maritime Intelligence Engine

The Maritime Intelligence Engine (MIE) is an end-to-end platform for real-time maritime behavioral intelligence built around real AIS telemetry.

Its architecture separates data acquisition, validation, domain representation, session state, trajectory processing, behavioral analysis, persistence, and operational visualization.

The system is designed around one principle:

«Real telemetry → validated observations → behavioral context → explainable intelligence.»

---

1. Architecture Overview

                         ┌─────────────────────────┐
                         │        AISStream        │
                         │     Real AIS Feed       │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │     AIS Ingestion       │
                         │ WebSocket + Subscription │
                         │      + Bounding Box     │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │ Validation & Integrity  │
                         │   Schema / Bounds /     │
                         │    Temporal Checks      │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │    AIS Observation     │
                         │     Domain Model       │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │      Session Store      │
                         │ Observations / Tracks   │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │   Trajectory Engine     │
                         │ Tracks / Temporal Math  │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │   Feature Engineering   │
                         │ Spatial / Temporal /    │
                         │      Behavioral         │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │ Behavioral Analytics     │
                         │ PCA / KMeans /           │
                         │ Isolation Forest        │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │   Intelligence Layer    │
                         │ Rules / Findings /      │
                         │ Behavioral Context      │
                         └────────────┬────────────┘
                                      │
                         ┌────────────┴────────────┐
                         ▼                         ▼
                ┌──────────────────┐      ┌──────────────────┐
                │ Operational UI   │      │ Historical Store │
                │ Streamlit / Maps │      │ PostgreSQL/PostGIS│
                └──────────────────┘      └──────────────────┘

The architecture is intentionally layered so that external AIS messages are not directly coupled to machine-learning models or the user interface.

---

2. Architectural Principles

MIE follows six primary principles:

OBSERVE
   ↓
VALIDATE
   ↓
REPRESENT
   ↓
ANALYZE
   ↓
EXPLAIN
   ↓
INVESTIGATE

Each stage has a distinct responsibility.

2.1 Real Data First

The system operates on real AIS observations.

MIE does not introduce synthetic vessels, artificial trajectories, or fabricated analytical findings when live AIS data is unavailable.

Real AIS
   ↓
Real Observation
   ↓
Real Track
   ↓
Real Features
   ↓
Analytical Signal

If the required data is unavailable, the system exposes the unavailable state instead.

---

2.2 Separation of Concerns

The architecture separates:

- external data acquisition;
- validation;
- domain models;
- session state;
- trajectory processing;
- behavioral analytics;
- persistence;
- presentation.

This prevents UI behavior or persistence failures from silently changing the meaning of the analytical pipeline.

---

2.3 Explicit Operational States

Operational state is explicit.

Examples include:

- "LIVE AIS"
- "CONNECTING"
- "DISCONNECTED"
- "STALE"
- "REAL AIS DATA UNAVAILABLE"
- "INSUFFICIENT DATA"
- "HISTORICAL DATABASE NOT CONFIGURED"
- "HISTORICAL PERSISTENCE OFF"
- "HISTORICAL DATABASE UNAVAILABLE"

These states are not interchangeable.

For example:

AIS disconnected
      ≠
No vessels exist

and:

Historical database unavailable
      ≠
Live AIS unavailable

---

3. Data Acquisition

3.1 AISStream

MIE receives AIS data through the AISStream WebSocket service.

The application creates a server-side subscription using the configured geographic Bounding Box and supported AIS message types.

The browser does not establish a direct AISStream connection.

Conceptually:

Streamlit Server
      │
      ▼
AISStream WebSocket
      │
      ▼
AIS Messages

This keeps credentials and provider communication on the server side.

---

3.2 Bounding Box

The monitoring region is represented semantically as:

min_lat
min_lon
max_lat
max_lon

The system validates that:

min_lat < max_lat
min_lon < max_lon

Invalid geographic regions block collection rather than silently falling back to another region.

This is important because an invalid monitoring region should never result in an apparently valid analytical session.

---

4. AIS Message Processing

Incoming AIS messages pass through the ingestion layer before becoming internal observations.

Conceptually:

Raw AIS Message
      ↓
Message Type Validation
      ↓
Payload Validation
      ↓
PositionReport Parsing
      ↓
AISObservation

The PositionReport parser validates required fields and numerical bounds before accepting an observation.

Unknown or unsupported message types are ignored rather than converted into position observations.

---

5. Domain Model

The external AIS message format is not used directly throughout the application.

MIE introduces an internal domain representation.

AISStream Message
       ↓
AISObservation
       ↓
Session Observation
       ↓
Vessel Track
       ↓
Vessel Snapshot

AISObservation

An "AISObservation" represents a validated position observation.

It contains the information required by the live analytical pipeline, including vessel identity, navigation values, geographic position, and temporal information.

The domain model intentionally separates:

Receive time

"received_at" represents the timezone-aware UTC instant at which MIE receives/processes the frame.

This is the trusted time used for:

- freshness;
- ordering;
- trajectory calculations;
- traffic grouping.

AIS timestamp second

"ais_timestamp_second" retains the AIS PositionReport timestamp as the reported UTC second within the minute.

Normal values are "0–59".

AIS special values "60–63" are preserved as AIS states and are not converted into fabricated datetimes.

Absolute observation time

"observed_at" remains unset when the AISStream envelope does not establish a trusted absolute observation datetime.

This prevents the system from manufacturing a timestamp from incomplete temporal information.

---

6. Session Store

The session store maintains bounded live observations and vessel tracks during an active collection.

Conceptually:

                     Session
                        │
             ┌──────────┴──────────┐
             ▼                     ▼
       Observations             Tracks
             │                     │
             └──────────┬──────────┘
                        ▼
                  Vessel State

The store is responsible for:

- retaining validated observations;
- associating observations with MMSI;
- reconstructing tracks;
- preventing uncontrolled growth;
- handling duplicates;
- enforcing configured limits.

The session store represents the live analytical state.

---

7. Live Provider State

The current architecture deliberately maintains a distinction between the live provider snapshot and the bounded observation store.

AIS Provider
     │
     └──────► Live vessel/status snapshot

Observation Store
     │
     └──────► Bounded observations/tracks

This dual-state design is retained as a compatibility boundary because different UI and session flows depend on each representation.

It should not be interpreted as duplicated analytical truth.

---

8. Trajectory Processing

MIE reconstructs vessel movement from sequential observations belonging to the same MMSI.

Conceptually:

P₁ → P₂ → P₃ → P₄ → ... → Pₙ

From the sequence, the system can derive movement characteristics such as:

- displacement;
- elapsed time;
- computed speed;
- heading changes;
- course changes;
- track duration;
- continuity;
- signal gaps.

The trajectory layer converts raw position observations into a temporal representation of vessel movement.

---

9. Feature Engineering

Raw AIS telemetry is transformed into a behavioral feature representation.

Position
Speed
Course
Heading
Time
Track History
      ↓
Spatial Features
Temporal Features
Movement Features
      ↓
Behavioral Feature Matrix

Feature engineering is separated from model execution so that analytical methods can evolve without requiring changes to the underlying ingestion layer.

---

10. Behavioral Analytics

The current analytical architecture uses unsupervised methods for exploratory behavioral analysis.

The principal components are:

PCA

Principal Component Analysis is used to reduce the dimensionality of the behavioral feature space and provide a compact representation of vessel behavior.

KMeans

KMeans is used to identify groups of observations or vessels with similar characteristics within the available analytical session.

Isolation Forest

Isolation Forest provides an anomaly score for observations that appear structurally different from the learned session distribution.

Conceptually:

Behavioral Features
        ↓
Standardization
        ↓
PCA
        ↓
 ┌──────┴────────┐
 ▼               ▼
KMeans       Isolation Forest
 │               │
 └──────┬────────┘
        ▼
Behavioral Signals

---

11. Session-Relative Intelligence

The current MIE behavioral models are session-relative.

The system learns the structure of the real observations available during the current analytical session.

Current Real AIS Session
          ↓
Behavioral Distribution
          ↓
Relative Deviation
          ↓
Anomaly Signal

This means the current system should not be described as a universal maritime behavior classifier.

It is better characterized as:

«Real-time exploratory maritime behavioral intelligence.»

A future historical baseline layer can extend this toward long-term behavioral comparison.

---

12. Intelligence Layer

Machine-learning output is not treated as a final operational conclusion.

The intelligence layer combines analytical signals with interpretable behavioral rules.

             ML Signals
                 │
                 ▼
          Behavioral Rules
                 │
                 ▼
             Findings
                 │
                 ▼
       Human Investigation

Potential interpretable signals include:

- unusual speed;
- prolonged stops;
- signal gaps;
- significant heading changes;
- unusual trajectory characteristics.

A finding is therefore an analytical signal, not proof of intent.

---

13. Vessel Intelligence

The Vessel Intelligence layer consolidates the available information for an individual MMSI.

                  Vessel
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
     Identity     Telemetry     Track
        │            │            │
        └────────────┼────────────┘
                     ▼
             Behavioral Data
                     │
                     ▼
              Findings/Signals

This allows the operator to move from the global maritime operating picture to an individual vessel investigation.

---

14. Data Quality

Data quality is part of the intelligence architecture rather than an afterthought.

Validation covers conditions such as:

- invalid MMSI;
- invalid latitude/longitude;
- impossible speeds;
- impossible geographic jumps;
- duplicate observations;
- missing data;
- stale observations;
- invalid configuration;
- insufficient analytical observations.

The principle is:

Bad Input
   ↓
Rejected / Explicitly Flagged
   ↓
Never silently converted
   ↓
No fabricated intelligence

---

15. Temporal Integrity

Time handling is explicitly designed around UTC.

AIS / Runtime
      ↓
Canonical UTC
      ↓
Analysis / Storage
      ↓
Presentation-Time Conversion

The system distinguishes between:

received_at
     │
     ├── freshness
     ├── ordering
     ├── trajectories
     └── traffic grouping

ais_timestamp_second
     │
     └── AIS protocol information

The current architecture does not infer network latency from the AIS second-of-minute field.

When trusted latency information is unavailable:

Network Latency = UNAVAILABLE

rather than a synthetic estimate.

---

16. Historical Persistence

PostgreSQL/PostGIS provides optional historical persistence.

The live pipeline does not depend on the historical database.

                       Real AIS
                          │
                          ▼
                    Session Store
                     /          \
                    /            \
                   ▼              ▼
            Live Analysis    PostgreSQL
                                  │
                                  ▼
                               PostGIS

Historical persistence is explicitly controlled.

The architecture distinguishes:

DATABASE_URL configured
        ≠
Historical persistence enabled

Persistence requires explicit opt-in.

This prevents the presence of database credentials alone from silently enabling historical writes.

---

17. Live vs Historical Failure Isolation

One of the architectural goals is to isolate live operations from historical storage.

For example:

PostgreSQL unavailable
        │
        ▼
Historical persistence unavailable
        │
        └──────────────► Live AIS can continue

Likewise:

AISStream unavailable
        │
        ▼
No live observations
        │
        └──────────────► No fabricated vessels

This separation is critical for trustworthy operational behavior.

---

18. Streamlit Operational Layer

Streamlit provides the operational interface.

It consumes structured application state and presents:

- collection status;
- connection status;
- vessel counts;
- vessel positions;
- trajectories;
- vessel intelligence;
- behavioral findings;
- traffic analysis;
- data quality;
- system diagnostics;
- historical persistence state.

The UI is not the source of analytical truth.

The analytical state is produced by the underlying ingestion, validation, processing, and intelligence layers.

---

19. Operational Flow

A typical collection session follows:

Operator
   │
   ▼
Configure Region
   │
   ▼
Validate Configuration
   │
   ▼
Create Session
   │
   ▼
Open AISStream Subscription
   │
   ▼
Receive Real AIS Messages
   │
   ▼
Validate Messages
   │
   ▼
Create AISObservations
   │
   ▼
Update Session Store
   │
   ▼
Build Tracks
   │
   ▼
Generate Features
   │
   ▼
Run Behavioral Analytics
   │
   ▼
Generate Findings
   │
   ▼
Expose Intelligence in UI

---

20. Configuration Safety

Runtime configuration is treated as part of the system architecture.

Configuration errors should remain visible.

For example:

Invalid configuration
        ↓
config_error
        ↓
Collection blocked

rather than:

Invalid configuration
        ↓
Silent fallback
        ↓
Unexpected region

This is particularly important for geographic Bounding Box configuration.

---

21. Security Boundaries

Credentials remain server-side.

The architecture does not expose the AISStream API key to the browser.

Secrets such as:

AISSTREAM_API_KEY
DATABASE_URL

are expected to be supplied through the deployment environment or Streamlit Secrets.

They must never be committed to source control.

---

22. Validation Architecture

MIE uses several layers of validation.

                Repository
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
      Tests       Compile     Diff Check
        │
        ▼
   Runtime Validation
        │
        ▼
   Browser / UI Checks
        │
        ▼
 Real AIS Verification

Automated validation covers core parsing, configuration, temporal semantics, trajectory logic, data quality, bounded storage, and related system behavior.

However:

«A successful application boot is not evidence of live AIS operation.»

Live operation requires a configured AISStream credential and a successful collection receiving real messages.

---

23. Failure Semantics

MIE intentionally distinguishes between absence, failure, and insufficient evidence.

Examples:

No AIS connection
      ≠
Zero vessels in the ocean

Insufficient tracks
      ≠
No anomaly detected

Historical database unavailable
      ≠
Live pipeline unavailable

Anomaly score
      ≠
Threat classification

These distinctions are fundamental to the interpretation of the system.

---

24. Current Limitations

The current architecture has several deliberate limitations.

AIS dependency

AIS-only analysis cannot automatically detect vessels that are not transmitting usable AIS information.

Session-relative modeling

Current behavioral models operate on the observed analytical session rather than a universal historical maritime baseline.

Limited historical intelligence

Long-term behavioral baselines require a sufficiently large and validated historical dataset.

No universal intent inference

Behavioral anomalies indicate patterns that may deserve investigation. They do not establish vessel intent or malicious activity.

---

25. Temporal Intelligence

Temporal intelligence is an evidence-gated parallel analytical path built from the same validated AIS tracks used by the rest of the system.

The temporal path is:

Real AIS tracks
      ↓
Validated temporal coverage
      ↓
Temporal diagnostics
      ↓
Adaptive scale selection
      ↓
Temporal sequence construction
      ↓
TCN Autoencoder
      ↓
Reconstruction error
      ↓
Session-relative deep anomaly ranking

The selector considers the candidate scales in descending order:

T=32
  ↓ if unsupported
T=16
  ↓ if unsupported
T=8
  ↓ if unsupported
NOT_READY

A scale is supported only when the minimum required number of tracks contains at least that many validated real AIS observations. The default minimum remains the existing deep-model requirement of 8 usable tracks.

This means a dense session may use T=32, while a sparse session such as the observed Houston Ship Channel session can use T=8. If fewer than 8 tracks support T=8, the temporal model remains NOT_READY.

The selector does not interpolate, stretch, duplicate, or synthesize observations to satisfy a requested sequence length.

Temporal diagnostics also expose:

- tracks meeting minimum point thresholds;
- median and maximum track duration;
- receive-time intervals and maximum gaps;
- sliding-window availability;
- non-overlapping window availability.

These diagnostics establish the evidence boundary before model training. They should be considered alongside model output rather than treated as a model-performance metric.

`deep_anomaly_score` remains a session-relative ranking and is not a calibrated probability or a universal maritime behavior classification.

---

26. Evolution Boundary

The current temporal architecture deliberately separates three questions:

1. Is there enough real temporal evidence to train?
2. Which supported temporal scale is appropriate for the current session?
3. Does the resulting temporal score generalize beyond the current session?

The first two are implemented. The third is not yet validated.

Future work should therefore prioritize controlled temporal validation, historical baselines, and cross-region evaluation before increasing model complexity.
