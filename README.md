Maritime Intelligence Engine (MIE)

Real-time Maritime Behavioral Intelligence

Maritime Intelligence Engine (MIE) is an end-to-end maritime intelligence platform designed to ingest real AIS data in real time, reconstruct vessel trajectories, analyze movement patterns, detect behavioral anomalies, and present explainable operational intelligence through an interactive geospatial workspace.

«Real AIS. Real trajectories. No synthetic vessels. No fabricated results.»

---

Overview

AIS provides continuous information about vessel movement, but raw position reports alone do not provide meaningful operational context.

MIE transforms raw AIS telemetry into a structured intelligence pipeline:

Real AIS
   ↓
WebSocket Ingestion
   ↓
Validation & Data Quality
   ↓
Session Store
   ↓
Trajectory Reconstruction
   ↓
Feature Engineering
   ↓
PCA / Clustering
   ↓
Isolation Forest
   +
Explainable Rules
   ↓
Behavioral Intelligence
   ↓
Operational Visualization

The objective is not simply to answer:

«Where are the vessels?»

but to move toward:

«How are they moving, how does their behavior compare with other observed vessels, and which patterns deserve investigation?»

---

Core Capabilities

📡 Real-time AIS Ingestion

- AISStream WebSocket integration
- Server-side subscription
- Geographic Bounding Box filtering
- Configurable collection windows
- Real vessel telemetry
- Explicit connection and data states

🚢 Vessel Tracking

- MMSI-based vessel tracking
- Individual vessel trajectories
- Position history
- Speed and course information
- Heading visualization
- Vessel-level investigation

🧭 Trajectory Intelligence

Trajectory data is transformed into behavioral features including:

- Position
- Speed over ground
- Course over ground
- Heading
- Distance traveled
- Time delta
- Computed speed
- Heading changes
- Track duration

These features provide the foundation for behavioral analysis.

🤖 Behavioral Anomaly Detection

MIE combines unsupervised machine learning with deterministic rules:

Trajectory Features
        ↓
Standardization
        ↓
PCA
        ↓
KMeans
        +
Isolation Forest
        ↓
Behavioral Findings

The system is designed to identify behavioral anomalies, not to automatically classify vessels as threats.

🔎 Explainable Findings

Machine-learning scores are complemented by interpretable rules such as:

- unusual speed;
- prolonged stops;
- signal gaps;
- significant heading changes;
- unusual movement patterns.

The goal is to provide an analyst with context, rather than an unexplained model score.

🗺️ Geospatial Intelligence

The operational workspace provides:

- live vessel positions;
- vessel trajectories;
- geographic filtering;
- Bounding Box control;
- vessel selection;
- behavioral overlays;
- heading visualization;
- interactive maps.

📊 Data Quality Monitoring

Data quality is treated as part of the intelligence pipeline.

The system monitors conditions such as:

- invalid MMSI;
- invalid coordinates;
- impossible speeds;
- impossible geographic jumps;
- duplicate observations;
- missing data;
- signal gaps;
- stale observations.

When real data is unavailable, MIE does not fabricate results.

---

Architecture

                         ┌─────────────────────┐
                         │      AISStream      │
                         │     Real AIS Data   │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │      Ingestion      │
                         │ WebSocket + BBox    │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │     Validation      │
                         │  Quality / Integrity│
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │    Session Store    │
                         │ Tracks / Observations│
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │  Trajectory Engine  │
                         │ Features / Tracks   │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │    ML Pipeline      │
                         │ PCA / KMeans / IF    │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Intelligence Layer  │
                         │ Rules + Findings    │
                         └──────────┬──────────┘
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                ┌─────────────────┐   ┌─────────────────┐
                │ Operational UI  │   │ Historical Store│
                │ Streamlit / Map │   │ PostgreSQL/PostGIS│
                └─────────────────┘   └─────────────────┘

---

System Design Principles

Real Data First

MIE is designed around real AIS observations.

The platform does not generate synthetic vessels or artificial trajectories to make the dashboard appear populated.

No Real AIS
     ↓
No Artificial Vessels
     ↓
No Fabricated Intelligence

---

Explicit System States

The platform distinguishes between states such as:

- LIVE
- DISCONNECTED
- STALE
- WAITING FOR DATA
- INSUFFICIENT DATA
- HISTORICAL DATABASE UNAVAILABLE

This prevents infrastructure failures or missing observations from being mistaken for analytical results.

---

Live vs Historical Data

Live operational data and historical persistence are intentionally separated.

                 Real AIS
                    │
                    ▼
              Session Store
                 /       \
                /         \
               ▼           ▼
          Live Analysis   PostgreSQL
                             │
                             ▼
                           PostGIS

Historical persistence is optional. The live pipeline can continue operating when the historical database is unavailable.

---

Behavioral Intelligence

MIE currently focuses on session-relative behavioral analysis.

The machine-learning pipeline learns the structure of the real trajectories available in the current analytical session.

This means the current system should be understood as:

«Real-time exploratory behavioral intelligence»

rather than a universal pre-trained maritime behavior model.

This distinction is intentional and keeps the interpretation of the results technically honest.

---

Vessel Intelligence

The vessel-level workspace brings together:

Vessel Identity
      +
Telemetry
      +
Trajectory
      +
Behavior
      +
Anomaly Findings

This allows an operator to move from a global maritime picture to the detailed investigation of an individual MMSI.

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

Project Structure

src/
├── ingestion/
│   ├── aisstream.py
│   ├── models.py
│   └── ...
│
├── processing/
│   ├── trajectories.py
│   ├── features.py
│   └── ...
│
├── ml/
│   ├── pca.py
│   ├── clustering.py
│   ├── isolation_forest.py
│   └── ...
│
├── intelligence/
│   ├── rules.py
│   ├── findings.py
│   └── ...
│
├── storage/
│   ├── session.py
│   ├── postgres.py
│   └── ...
│
└── ui/
    ├── pages/
    └── components/

---

Running Locally

1. Clone

git clone https://github.com/edu-moraess/maritime-intelligence-engine.git
cd maritime-intelligence-engine

2. Create environment

python -m venv .venv
source .venv/bin/activate

Windows:

.venv\Scripts\activate

3. Install dependencies

pip install -r requirements.txt

4. Configure secrets

Provide the required AISStream credentials through the application's supported secrets/environment configuration.

Do not commit credentials to the repository.

5. Run

streamlit run app.py

---

Historical Persistence

Historical persistence can be enabled with PostgreSQL/PostGIS.

The architecture supports:

- session storage;
- observation persistence;
- geospatial data;
- historical vessel observations;
- database health diagnostics.

The historical layer is intentionally decoupled from live ingestion.

---

Testing

The project includes automated tests covering core components such as:

- AIS parsing;
- validation;
- session behavior;
- trajectory processing;
- feature generation;
- anomaly logic;
- storage behavior;
- system diagnostics.

Run:

pytest -q

---

Current Scope

Available

- Real-time AIS ingestion
- Real vessel tracking
- Bounding Box filtering
- Session-based analysis
- Trajectory reconstruction
- Behavioral feature engineering
- PCA
- KMeans
- Isolation Forest
- Explainable behavioral rules
- Vessel Intelligence
- Data Quality monitoring
- Interactive geospatial visualization
- Optional PostgreSQL/PostGIS persistence

In Development

- AIS "ShipStaticData" enrichment
- Vessel metadata enrichment
- Improved vessel identity intelligence
- Historical behavioral analysis

Roadmap

Real-time AIS
      ↓
AIS Static Data
      ↓
Historical Behavioral Baselines
      ↓
Advanced Geospatial Intelligence
      ↓
Multimodal Maritime Intelligence
      ↓
AIS + Visual Intelligence + External Sensors

---

Design Philosophy

MIE is built around a simple principle:

«Turn real maritime telemetry into trustworthy, explainable intelligence.»

The system deliberately separates:

Observation
    ↓
Validation
    ↓
Representation
    ↓
Analysis
    ↓
Finding
    ↓
Human Investigation

A behavioral anomaly is therefore treated as a signal for investigation, not as proof of malicious intent.

---

What MIE Is — and Is Not

MIE is:

- a real-time AIS intelligence platform;
- a trajectory analysis system;
- a behavioral anomaly detection engine;
- a geospatial operational workspace;
- an experimental foundation for maritime intelligence.

MIE is not:

- a physical radar;
- a sonar system;
- a universal threat detector;
- a military targeting system;
- a pre-trained universal maritime behavior model;
- a guarantee of vessel intent.

AIS also has an important limitation:

«A vessel that is not transmitting usable AIS data cannot automatically be detected by an AIS-only system.»

This is one reason the long-term architecture is designed to evolve toward multi-source maritime intelligence.

---

Future Vision

The long-term direction is to evolve from AIS-only behavioral intelligence toward multimodal maritime perception.

                     MARITIME ENVIRONMENT
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
           AIS              VIDEO              SAR
            │                 │                 │
            ▼                 ▼                 ▼
       Vessel Data        Computer Vision    Remote Sensing
            │                 │                 │
            └─────────────────┼─────────────────┘
                              ▼
                        Sensor Fusion
                              │
                              ▼
                     Behavioral Analysis
                              │
                              ▼
                    Maritime Intelligence
                              │
                              ▼
                       Human Analyst

The goal is not to replace human analysis.

The goal is to give the analyst:

«better data, better context, better signals, and better explanations.»

---

Why This Project?

MIE combines several areas of modern engineering in one operational system:

- Data Engineering
- Real-time Streaming
- Geospatial Computing
- Machine Learning
- Unsupervised Learning
- Anomaly Detection
- Data Quality Engineering
- Backend Architecture
- Database Engineering
- Visualization
- Operational UI

Instead of treating these as isolated experiments, MIE connects them into a single end-to-end pipeline.

---

License

See the repository license for usage and distribution terms.

---

Maritime Intelligence Engine

Real AIS → Trusted Data → Trajectories → Behavior → Intelligence

Built as an engineering and research platform for real-time maritime behavioral intelligence.