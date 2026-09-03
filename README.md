# Maritime Intelligence Engine (MIE)

## Real-Time Maritime Behavioral Intelligence

Maritime Intelligence Engine (MIE) is an end-to-end maritime intelligence platform designed to ingest **real AIS telemetry**, reconstruct vessel trajectories, analyze movement patterns, detect behavioral anomalies, and transform maritime telemetry into explainable operational intelligence.

> **Real AIS. Real trajectories. No synthetic vessels. No fabricated results.**

---

## What MIE does

```text
Real AIS
   ↓
Ingestion
   ↓
Validation
   ↓
Session Store
   ↓
Trajectory Reconstruction
   ↓
Feature Engineering
   ↓
Behavioral Analytics
   ↓
Temporal Intelligence
   ↓
Explainable Findings
   ↓
Operational Intelligence
```

The central question is not only **where a vessel is**, but also how it is moving, how its behavior compares with observed traffic, and which patterns deserve further investigation.

## Core capabilities

### Real-time AIS

- AISStream WebSocket integration
- Real vessel telemetry
- Server-side Bounding Box filtering
- Configurable collection windows
- Explicit connection and collection states
- Session-based collection
- Multi-region monitoring through a single operational workspace
- Two-region unified or split tactical visualization

### Multi-region tactical monitoring

MIE supports monitoring two maritime regions simultaneously while keeping their analytical state separated.

```text
                 AISStream
                    ↓
          Multi-region subscription
               ↙          ↘
          Region A      Region B
             ↓              ↓
       Regional state  Regional state
             ↘              ↙
              Operational UI
              /            \
           SPLIT          UNIFIED
```

**SPLIT** provides independent tactical maps and independent vessel selection for each region.

**UNIFIED** provides one enclosing tactical viewport across both regions without inventing a geographic midpoint. Regional intelligence remains distinct even when the map is unified.

Selecting a vessel in a regional or unified view persists the selection across Streamlit reruns and opens the corresponding Vessel Intelligence context.

### Vessel and trajectory intelligence

- MMSI-based vessel tracking
- Position history
- SOG / COG / heading
- Track duration and continuity
- Movement and trajectory features
- Vessel-level investigation
- Interactive geospatial visualization

### Behavioral analytics

- PCA dimensionality reduction
- KMeans behavioral grouping
- Isolation Forest anomaly detection
- Explainable behavioral rules
- Session-relative analytical signals

### Temporal intelligence

MIE measures the real temporal coverage available before applying deep temporal learning.

```text
Real AIS tracks
      ↓
Temporal diagnostics
      ↓
T=32 ── if enough real observations
      ↓ otherwise
T=16 ── if enough real observations
      ↓ otherwise
T=8  ── if enough real observations
      ↓ otherwise
NOT_READY
```

The current temporal production path uses a **GRU Temporal Autoencoder** with adaptive sequence length. Short tracks are never stretched, interpolated, or fabricated into longer temporal evidence.

### Temporal evidence observed in live AIS

A Houston Ship Channel session produced approximately 974 seconds of observed collection, 549 persisted real position reports, and 181 active vessels. The temporal diagnostics found:

- 69 tracks with ≥4 points;
- 11 tracks with ≥8 points;
- 0 tracks with ≥16 points;
- 0 tracks with ≥32 points;
- 17 sliding T=8 windows;
- 11 non-overlapping T=8 windows;
- median track duration of 7.0 minutes;
- maximum receive-time gap of 24.7 minutes.

Previous Danish Straits sessions produced materially denser temporal coverage, including 263 tracks with ≥4 points. This demonstrates that temporal model availability is **region- and session-dependent**.

The current development therefore treats temporal coverage as an explicit evidence boundary rather than assuming that T=32 is universally available.

### Explainable findings

Anomaly scores and behavioral rules are treated as signals for investigation, not proof of malicious intent, criminal activity, or hostile behavior.

### Historical persistence

PostgreSQL/PostGIS provides an optional historical persistence layer for real validated AIS observations. Persistence is decoupled from live ingestion and is idempotent.

### Data quality

The system validates conditions including:

- MMSI validity;
- geographic bounds;
- speed plausibility;
- temporal consistency;
- duplicate observations;
- geographic jumps;
- stale observations;
- insufficient analytical evidence.

When real AIS data is unavailable, MIE exposes an unavailable/insufficient-data state instead of generating fictional traffic.

---

## Architecture

```text
AISStream WebSocket
        ↓
Real AIS ingestion
        ↓
Validation & integrity
        ↓
AISObservation
        ↓
Session Store
        ↓
Trajectory Engine
        ↓
Feature Engineering
        ↓
 ┌───────────────────────────────┐
 │ Behavioral Analytics          │
 │ PCA / KMeans / IsolationForest│
 └───────────────┬───────────────┘
                 ↓
       Temporal Diagnostics
                 ↓
      GRU Temporal Autoencoder
                 ↓
      Intelligence / Findings
          ↙              ↘
     Streamlit       PostgreSQL/PostGIS
```

The architecture intentionally separates data acquisition, validation, domain representation, session state, trajectory processing, machine learning, intelligence, persistence, and visualization.

For the detailed architecture, see `docs/architecture.md`.

---

## Real Data Principle

MIE is built around real AIS observations.

```text
Real AIS
   ↓
Validated Observation
   ↓
Real Track
   ↓
Real Features
   ↓
Analytical Signal
```

If the required data is unavailable, the system does not substitute simulated vessels or fabricated trajectories.

This principle applies to temporal learning as well: a model cannot claim a long temporal sequence when the source observations do not support it.

---

## Operational semantics

MIE explicitly distinguishes infrastructure state, data availability, and analytical sufficiency.

```text
AIS disconnected
      ≠
No vessels exist

Insufficient observations
      ≠
Normal behavior

Anomaly score
      ≠
Threat classification

Session-relative score
      ≠
Universal behavior probability
```

`deep_anomaly_score` is currently a session-relative ranking, not a calibrated probability.

---

## Technology stack

| Layer | Technology |
|---|---|
| Language | Python |
| Interface | Streamlit |
| AIS Transport | WebSocket / AISStream |
| Data Processing | Pandas / NumPy |
| Machine Learning | Scikit-learn / PyTorch |
| Dimensionality Reduction | PCA |
| Clustering | KMeans |
| Anomaly Detection | Isolation Forest |
| Temporal Model | GRU Temporal Autoencoder |
| Visualization | Plotly / PyDeck |
| Database | PostgreSQL |
| Geospatial Database | PostGIS |
| Containers | Docker |
| Testing | Pytest |

---

## Validation

The repository contains automated tests for ingestion, configuration, trajectory processing, data quality, persistence, temporal semantics, temporal diagnostics, and analytical safeguards.

Run:

```bash
pytest -q
```

Temporal diagnostics specifically verify:

- minimum-point coverage;
- receive-time duration and gaps;
- sliding and non-overlapping windows;
- adaptive selection of T=8/T=16/T=32;
- rejection when temporal coverage is insufficient.

Live AIS validation is performed separately against the deployed Streamlit application using real AISStream observations.

See:

- `docs/VALIDATION.md`
- `docs/PROJECT_STATUS.md`
- `docs/AUDIT.md`
- `docs/architecture.md`
- `docs/STREAMLIT_DEPLOY.md`

---

## Current scope

### Implemented

- Real-time AIS ingestion
- AISStream WebSocket integration
- Multi-region monitoring with two simultaneous Bounding Boxes
- SPLIT and UNIFIED tactical map views
- Independent regional vessel selection
- Persistent UNIFIED vessel selection across Streamlit reruns
- Vessel Intelligence from regional and unified selection
- 30 maritime monitoring region presets
- Bounding Box validation
- Vessel tracking
- Session-based collection
- Trajectory reconstruction
- Behavioral feature engineering
- PCA / KMeans / Isolation Forest
- Explainable behavioral rules
- Vessel Intelligence
- Tactical geospatial visualization
- Data Quality monitoring
- Temporal integrity controls
- Temporal track diagnostics
- GRU Temporal Autoencoder
- Adaptive temporal scale selection (T=8/T=16/T=32)
- PostgreSQL/PostGIS historical persistence
- Idempotent historical observation persistence

### In development / research

- Historical behavioral baselines
- Long-term vessel profiles
- Quantitative temporal model validation
- Context-aware anomaly scoring
- Weather and ocean context
- Event intelligence
- Multimodal maritime intelligence

---

## Current research position

The immediate goal is not simply to make the temporal model more complex. The project is establishing an evidence-driven temporal foundation:

1. measure real track coverage;
2. select the longest supported temporal scale;
3. preserve source provenance;
4. validate temporal scores quantitatively;
5. build historical behavioral baselines;
6. add environmental context;
7. combine behavioral, trajectory, temporal, and environmental evidence;
8. use LLMs as an interpretation layer rather than as the raw anomaly detector.

### Current limitation

AIS coverage is not uniform. Short collection windows may provide many active vessels but relatively few repeated observations per vessel. Long temporal sequences therefore cannot be assumed to exist in every region.

The system should prefer `NOT_READY` or a shorter supported temporal scale over unsupported temporal evidence.

---

## Roadmap

```text
Real-Time AIS
      ↓
Multi-Region Operational Monitoring
      ↓
Temporal Coverage Diagnostics
      ↓
Adaptive Temporal Intelligence
      ↓
Historical Behavioral Baselines
      ↓
Weather / Ocean Context
      ↓
Context-Aware Behavioral Intelligence
      ↓
Advanced Geospatial Intelligence
      ↓
Multimodal Maritime Intelligence
      ├── AIS
      ├── Computer Vision
      ├── SAR
      ├── Weather / Ocean
      └── External Geospatial Data
```

Future data sources are architectural directions and are not represented as current capabilities unless implemented.

---

## Design philosophy

> **Observe → Validate → Analyze → Explain → Investigate**

The platform is designed to support human investigation rather than replace human judgment.

---

## Installation

```bash
git clone https://github.com/edu-moraess/maritime-intelligence-engine.git
cd maritime-intelligence-engine
python -m venv .venv
```

Linux / macOS:

```bash
source .venv/bin/activate
```

Windows:

```powershell
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure the required AISStream credentials through the deployment environment or Streamlit Secrets. Never commit API keys or database credentials.

Run:

```bash
streamlit run app.py
```

---

## Author

**Carlos Eduardo Moraes**  
Quantitative Developer · Data Science · Computer Engineering

---

## License

MIT License. See `LICENSE` for the complete license text.

---

**Maritime Intelligence Engine**  
*Real AIS → Trusted Data → Trajectories → Behavior → Intelligence*