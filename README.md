Maritime Intelligence Engine (MIE)

Real-Time Maritime Behavioral Intelligence

"MIE Architecture" (docs/architecture-diagram.png)

Maritime Intelligence Engine (MIE) is an end-to-end maritime intelligence platform designed to ingest real AIS telemetry, reconstruct vessel trajectories, analyze movement patterns, detect behavioral anomalies, and transform maritime telemetry into explainable operational intelligence.

«Real AIS. Real trajectories. No synthetic vessels. No fabricated results.»

---

Overview

AIS provides information about where vessels are and how they are moving.

MIE is designed to go further by transforming vessel telemetry into behavioral context and analytical signals.

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
Explainable Findings
   ↓
Operational Intelligence

The central question is not only:

«Where is the vessel?»

but also:

«How is it moving, how does its behavior compare with the observed traffic, and which patterns deserve further investigation?»

---

Core Capabilities

📡 Real-Time AIS Ingestion

- AISStream WebSocket integration
- Real vessel telemetry
- Server-side Bounding Box filtering
- Configurable collection windows
- Explicit connection and collection states
- Session-based collection

🚢 Vessel Tracking

- MMSI-based vessel tracking
- Position history
- Speed over ground
- Course over ground
- Heading
- Vessel-level investigation
- Trajectory reconstruction

🧭 Trajectory Intelligence

MIE transforms sequential AIS observations into vessel movement histories and analytical features.

Examples include:

- displacement
- elapsed time
- computed speed
- heading changes
- course changes
- track duration
- movement continuity
- signal gaps

🤖 Behavioral Analytics

The current analytical pipeline uses unsupervised methods to explore behavioral structure in observed maritime traffic.

Trajectory Features
        ↓
Standardization
        ↓
PCA
   ┌────┴────┐
   ▼         ▼
KMeans   Isolation Forest
   │         │
   └────┬────┘
        ▼
Behavioral Signals

Current analytical components include:

- PCA for dimensionality reduction
- KMeans for behavioral grouping
- Isolation Forest for anomaly detection

🔎 Explainable Findings

Machine-learning outputs are complemented by interpretable behavioral rules.

Potential signals include:

- unusual speed
- prolonged stops
- signal gaps
- significant heading changes
- unusual trajectory characteristics

An anomaly is treated as a signal for investigation, not as proof of malicious intent.

🗺️ Geospatial Intelligence

The operational workspace provides:

- live vessel positions
- trajectory visualization
- geographic filtering
- Bounding Box control
- vessel selection
- behavioral visualization
- heading visualization
- operational status

📊 Data Quality

Data quality is part of the intelligence pipeline.

The system validates conditions including:

- MMSI validity
- geographic bounds
- speed plausibility
- temporal consistency
- duplicate observations
- geographic jumps
- stale observations
- insufficient analytical data

When real AIS data is unavailable, MIE does not fabricate vessels or trajectories.

---

Architecture

MIE follows a layered architecture.

"MIE Architecture" (docs/architecture-diagram.png)

For the complete technical design, see ""docs/architecture.md"" (docs/architecture.md).

                         AISStream
                            │
                            ▼
                     AIS Ingestion
                            │
                            ▼
                  Validation & Integrity
                            │
                            ▼
                     AISObservation
                            │
                            ▼
                      Session Store
                            │
                            ▼
                    Trajectory Engine
                            │
                            ▼
                   Feature Engineering
                            │
                            ▼
                  Behavioral Analytics
                            │
                            ▼
                   Intelligence Layer
                       /          \
                      ▼            ▼
                Streamlit      PostgreSQL
                   / Maps         │
                                 ▼
                              PostGIS

The architecture intentionally separates:

- data acquisition
- validation
- domain representation
- session state
- trajectory processing
- machine learning
- intelligence
- persistence
- visualization

---

Real Data Principle

MIE is designed around real AIS observations.

The system does not generate synthetic vessels or artificial trajectories to make the operational interface appear populated.

Real AIS
   ↓
Validated Observation
   ↓
Real Track
   ↓
Real Features
   ↓
Analytical Signal

If the required data is unavailable, the system exposes that limitation instead.

This principle is fundamental to the project.

---

Operational State

MIE explicitly distinguishes between data availability, infrastructure state, and analytical sufficiency.

AIS disconnected
      ≠
No vessels exist

Historical database unavailable
      ≠
Live AIS unavailable

Insufficient observations
      ≠
No anomaly exists

Anomaly score
      ≠
Threat classification

This prevents infrastructure or data limitations from being misinterpreted as intelligence findings.

---

Temporal Integrity

MIE uses UTC as its canonical temporal reference.

The architecture distinguishes between:

- Receive Time
- AIS Timestamp
- Trusted Absolute Observation Time

The system does not fabricate absolute observation timestamps or network latency when the available AIS data does not support those conclusions.

---

Vessel Intelligence

The Vessel Intelligence layer combines:

Vessel Identity
       +
Telemetry
       +
Trajectory
       +
Behavioral Features
       +
Analytical Findings

This allows the operator to move from the global maritime operating picture toward an individual vessel investigation.

---

Historical Persistence

PostgreSQL/PostGIS provides an optional historical persistence layer.

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

Historical persistence is intentionally decoupled from live ingestion so that a historical database failure does not need to terminate live AIS analysis.

Historical storage provides the foundation for future capabilities such as:

- long-term vessel history
- behavioral baselines
- route analysis
- recurring behavior detection
- historical anomaly comparison

---

Technology Stack

Layer| Technology
Language| Python
Interface| Streamlit
AIS Transport| WebSocket / AISStream
Data Processing| Pandas / NumPy
Machine Learning| Scikit-learn
Dimensionality Reduction| PCA
Clustering| KMeans
Anomaly Detection| Isolation Forest
Visualization| Plotly / PyDeck
Database| PostgreSQL
Geospatial Database| PostGIS
Containers| Docker
Testing| Pytest

---

Installation

Clone

git clone https://github.com/edu-moraess/maritime-intelligence-engine.git
cd maritime-intelligence-engine

Create virtual environment

python -m venv .venv

Linux / macOS:

source .venv/bin/activate

Windows:

.venv\Scripts\activate

Install dependencies

pip install -r requirements.txt

Configure AIS credentials

Configure the required AISStream credentials using the supported environment or Streamlit Secrets configuration.

Never commit API keys or database credentials to the repository.

Run

streamlit run app.py

---

Validation

MIE includes automated and runtime validation covering core system behavior.

Examples include:

- AIS parsing
- configuration validation
- geographic bounds
- temporal semantics
- trajectory logic
- data-quality checks
- bounded session storage
- system diagnostics
- application compilation

Run:

pytest -q

For detailed validation evidence, see ""docs/VALIDATION.md"" (docs/VALIDATION.md).

For technical audit information, see ""docs/AUDIT.md"" (docs/AUDIT.md).

For deployment instructions, see ""docs/STREAMLIT_DEPLOY.md"" (docs/STREAMLIT_DEPLOY.md).

---

Current Scope

Implemented

- Real-time AIS ingestion
- AISStream WebSocket integration
- Bounding Box filtering
- Vessel tracking
- Session-based collection
- Trajectory reconstruction
- Behavioral feature engineering
- PCA
- KMeans
- Isolation Forest
- Explainable behavioral rules
- Vessel Intelligence
- Data Quality monitoring
- Temporal integrity controls
- Interactive geospatial visualization
- Optional PostgreSQL/PostGIS persistence

In Development

- AIS "ShipStaticData" enrichment
- Vessel metadata enrichment
- Expanded vessel identity intelligence
- Historical behavioral baselines
- Long-term behavioral analysis

---

Limitations

AIS Dependency

An AIS-only system cannot automatically detect vessels that are not transmitting usable AIS information.

Session-Relative Analysis

Current behavioral models operate relative to the observed analytical session.

They should not be interpreted as a universal maritime behavior classifier.

No Intent Inference

Behavioral anomalies are analytical signals.

They do not establish:

- malicious intent
- criminal activity
- hostile behavior
- vessel identity beyond available AIS information

No Synthetic Fallback

When real AIS data is unavailable, MIE does not replace it with simulated vessel traffic.

---

Roadmap

Real-Time AIS
      │
      ▼
Ship Static Data
      │
      ▼
Historical Behavioral Baselines
      │
      ▼
Context-Aware Behavioral Intelligence
      │
      ▼
Advanced Geospatial Intelligence
      │
      ▼
Multimodal Maritime Intelligence
      │
      ├── AIS
      ├── Computer Vision
      ├── SAR
      ├── Weather
      └── External Geospatial Data

The long-term direction is to evolve from AIS-focused behavioral analysis toward a multimodal maritime intelligence architecture.

Future data sources shown above are architectural directions and are not represented as current capabilities unless implemented.

---

Why MIE?

MIE is not simply an AIS map.

It combines several engineering disciplines into a single end-to-end system:

- Real-Time Data Engineering
- WebSocket Streaming
- Geospatial Computing
- Trajectory Reconstruction
- Feature Engineering
- Unsupervised Machine Learning
- Anomaly Detection
- Data Quality Engineering
- Database Engineering
- Operational Visualization
- System Diagnostics
- Explainable Intelligence

The objective is to transform:

Raw Maritime Telemetry
          ↓
Structured Movement Data
          ↓
Behavioral Representation
          ↓
Analytical Signals
          ↓
Operational Intelligence

---

Design Philosophy

«Observe → Validate → Analyze → Explain → Investigate»

The platform is designed to help an analyst understand maritime movement, not to replace human judgment.

---

Documentation

Document| Description
""docs/architecture.md"" (docs/architecture.md)| Complete technical architecture
""docs/AUDIT.md"" (docs/AUDIT.md)| Technical audit and engineering decisions
""docs/VALIDATION.md"" (docs/VALIDATION.md)| Automated and runtime validation
""docs/STREAMLIT_DEPLOY.md"" (docs/STREAMLIT_DEPLOY.md)| Streamlit deployment documentation

---

License

This project is licensed under the MIT License.

See ""LICENSE"" (LICENSE) for the complete license text.

---

Author

Carlos Eduardo Moraes

Quantitative Developer · Data Science · Computer Engineering

---

Maritime Intelligence Engine

Real AIS → Trusted Data → Trajectories → Behavior → Intelligence

Built as an engineering and research platform for real-time maritime behavioral intelligence.
