# Maritime Intelligence Engine (MIE)

## Real-Time Maritime Behavioral Intelligence

Maritime Intelligence Engine (MIE) is an end-to-end system for ingesting **real AIS telemetry**, reconstructing vessel trajectories, analyzing navigation behavior, detecting anomalies, and enriching observations with environmental marine context.

> **Real AIS. Real trajectories. No synthetic vessels. No fabricated observations.**

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
Environmental Context
   ↓
Explainable Findings
   ↓
Operational Intelligence
```

The central question is not only **where a vessel is**, but how it is moving, how its behavior compares with observed traffic, and which events deserve further investigation.

---

## Core capabilities

### Real-time AIS

- AISStream WebSocket integration
- Real vessel telemetry
- Server-side Bounding Box filtering
- Configurable collection windows
- Explicit connection and collection states
- Session-based collection
- Multi-region monitoring through a single operational workspace
- Real AIS only: unavailable or insufficient data is surfaced explicitly

### Multi-region tactical monitoring

MIE supports two maritime regions simultaneously while keeping their analytical state separated.

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

**SPLIT** provides independent tactical maps and vessel selection for each region.

**UNIFIED** provides one enclosing tactical viewport across both regions without inventing a geographic midpoint. Regional intelligence remains distinct even when the map is unified.

Vessel selection persists across Streamlit reruns and opens the corresponding Vessel Intelligence context.

### Vessel and trajectory intelligence

- MMSI-based vessel tracking
- Position history
- SOG / COG / heading
- Track duration and continuity
- Movement and trajectory features
- Vessel-level investigation
- Real AIS track visualization
- Start/latest track endpoints
- Behavioral findings anchored to observed AIS events

### Behavioral analytics

- PCA dimensionality reduction
- KMeans behavioral grouping
- Isolation Forest anomaly detection
- Explainable behavioral rules
- Session-relative analytical signals
- Discrete anomaly findings tied to real observations

The behavioral reference space is analytical context, not a statistical confidence boundary. Isolation Forest scores are session-relative signals and are not probabilities.

### Temporal intelligence

MIE uses temporal sequence modeling only when the available AIS evidence supports it.

```text
Real validated AIS tracks
          ↓
Temporal diagnostics
          ↓
T=32 → T=16 → T=8 → NOT_READY
          ↓
TCN Temporal Autoencoder
          ↓
Reconstruction / temporal anomaly signal
```

The current production temporal architecture is a **TCN Autoencoder implemented in PyTorch**. The model uses causal/dilated temporal residual blocks and replaces the previous GRU production path. The legacy GRU implementation remains available for checkpoint/backward compatibility.

The adaptive selector chooses the longest supported sequence length from validated real observations. Short tracks are never stretched, interpolated, or fabricated into longer temporal evidence.

### Environmental marine context

MIE integrates real marine model data through the **Open-Meteo Marine API**.

The environmental channel currently retrieves:

- wave height;
- wave direction;
- wave period;
- wind-wave height;
- swell height and direction;
- ocean-current velocity;
- ocean-current direction;
- sea-surface temperature.

Environmental observations are normalized by region and timestamp and remain independent from AIS ingestion.

This context allows an operator to compare a change in vessel speed or route with the marine conditions observed during the same period. It provides additional evidence for investigation; it does **not** automatically establish that environmental conditions caused an anomaly.

### Explainable findings

Anomaly findings are analytical signals for investigation, not proof of malicious intent, criminal activity, or hostile behavior.

The system preserves the distinction between:

```text
AIS observation
      ≠
Analytical finding
      ≠
Threat classification
```

### Historical persistence

PostgreSQL/PostGIS provides an optional historical persistence layer for validated AIS observations.

- Historical persistence is decoupled from live ingestion.
- Writes are designed to be idempotent.
- Historical state is not used to fabricate current vessel positions.

### Data quality and evidence boundaries

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

## Analytical visualization

The operational interface separates **context, evidence, and state** rather than treating every chart as a generic dashboard.

Current analytical views include:

- real AIS trajectory with explicit start/latest endpoints;
- SOG and COG time series;
- behavioral findings anchored to observed events;
- anomaly score event markers;
- PCA behavioral reference space;
- AIS message throughput;
- speed-over-ground distribution;
- behavioral findings by category;
- regional operational state;
- environmental marine conditions.

The visualization layer does not alter AIS ingestion, anomaly semantics, persistence, or map geometry.

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
             ┌────────────────────┴────────────────────┐
             ↓                                         ↓
     Behavioral Analytics                    Environmental Context
   PCA / KMeans / IsolationForest             Open-Meteo Marine
             ↓                                         ↓
             └────────────────────┬────────────────────┘
                                  ↓
                        Temporal Diagnostics
                                  ↓
                         TCN Autoencoder
                                  ↓
                         Intelligence Engine
                                  ↓
                    Explainable Findings / UI
                         ↙               ↘
                    Streamlit       PostgreSQL/PostGIS
```

The architecture separates data acquisition, validation, domain representation, session state, trajectory processing, machine learning, environmental context, intelligence, persistence, and visualization.

For the detailed system topology, see `docs/architecture.md`.

---

## Real Data Principle

MIE is built around observations that were actually received from external data providers.

```text
Real AIS
   ↓
Validated Observation
   ↓
Real Track
   ↓
Real Features
   ↓
Behavioral / Temporal Signal
   ↓
Explainable Finding
```

If required evidence is unavailable, the system does not substitute simulated vessels or fabricated trajectories.

The same principle applies to temporal learning: a model cannot claim a sequence length that the source observations do not support.

---

## Operational semantics

MIE explicitly distinguishes infrastructure state, data availability, analytical sufficiency, and anomaly signals.

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
Universal probability

Environmental context
      ≠
Causal explanation
```

This distinction is fundamental to the system's analytical integrity.

---

## Technology stack

| Layer | Technology |
|---|---|
| Language | Python |
| Interface | Streamlit |
| AIS Transport | WebSocket / AISStream |
| Data Processing | Pandas / NumPy |
| Machine Learning | Scikit-learn / PyTorch |
| Behavioral Analysis | PCA / KMeans / Isolation Forest |
| Temporal Model | TCN Temporal Autoencoder |
| Marine Context | Open-Meteo Marine |
| Visualization | Plotly / PyDeck |
| Database | PostgreSQL |
| Geospatial Database | PostGIS |
| Containers | Docker |
| Testing | Pytest |

---

## Validation

The repository contains automated tests covering ingestion, configuration, trajectory processing, data quality, persistence, temporal semantics, temporal diagnostics, and analytical safeguards.

Run:

```bash
pytest -q
```

Temporal validation covers:

- minimum-point coverage;
- receive-time duration and gaps;
- sliding and non-overlapping windows;
- adaptive T=8/T=16/T=32 selection;
- rejection when temporal coverage is insufficient;
- TCN temporal model behavior when PyTorch is available.

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
- Maritime monitoring region presets
- Bounding Box validation
- Vessel tracking
- Session-based collection
- Trajectory reconstruction
- Behavioral feature engineering
- PCA / KMeans / Isolation Forest
- Explainable behavioral rules
- Behavioral findings linked to real AIS observations
- Analytical Plotly chart system
- Tactical geospatial visualization
- Data Quality monitoring
- Temporal integrity controls
- Temporal track diagnostics
- TCN Temporal Autoencoder
- Adaptive temporal scale selection
- PostgreSQL/PostGIS historical persistence
- Idempotent historical observation persistence
- Open-Meteo Marine environmental context
- Regional environmental context state

### In development / research

- Historical behavioral baselines
- Long-term vessel profiles
- Quantitative temporal model validation
- Context-aware anomaly scoring
- Environmental/behavioral evidence fusion
- Event intelligence
- Multimodal maritime intelligence

---

## Current research position

The project follows an evidence-first approach:

1. acquire real observations;
2. validate source integrity;
3. measure available temporal coverage;
4. select a supported temporal scale;
5. preserve observation provenance;
6. detect behavioral and temporal deviations;
7. contextualize findings with marine conditions;
8. validate analytical signals quantitatively;
9. build historical behavioral baselines;
10. combine independent evidence channels without conflating their semantics.

The objective is not to manufacture certainty. When the evidence is insufficient, the system should expose that limitation explicitly.

### Current limitations

AIS coverage is not uniform. Short collection windows may provide many active vessels but relatively few repeated observations per vessel. Long temporal sequences therefore cannot be assumed to exist in every region.

Marine environmental data is contextual model output and should be interpreted alongside its temporal and spatial resolution. It is not treated as automatic causal evidence for vessel behavior.

The system should prefer `NOT_READY` or a shorter supported temporal scale over unsupported temporal evidence.

---

## Roadmap

```text
Real-Time AIS
      ↓
Multi-Region Operational Monitoring
      ↓
Behavioral Intelligence
      ↓
Temporal Intelligence
      ↓
Environmental Marine Context
      ↓
Historical Behavioral Baselines
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

> **Observe → Validate → Analyze → Contextualize → Explain → Investigate**

MIE is designed to support human investigation rather than replace human judgment.

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
.venv\\Scripts\\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure AISStream credentials through the deployment environment or Streamlit Secrets. Never commit API keys or database credentials.

Run:

```bash
streamlit run app.py
```

---

## Author

**Carlos Eduardo Moraes**  
Computer Engineering · Data Science · Maritime Intelligence

---

## License

MIT License. See `LICENSE` for the complete license text.

---

**Maritime Intelligence Engine**  
*Real AIS → Trusted Data → Behavior → Temporal Intelligence → Environmental Context → Explainable Intelligence*
