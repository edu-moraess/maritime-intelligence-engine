Maritime Intelligence Engine (MIE)

Real-Time Maritime Behavioral Intelligence

Maritime Intelligence Engine (MIE) is an end-to-end maritime intelligence platform designed to ingest real AIS data in real time, reconstruct vessel trajectories, analyze movement patterns, detect behavioral anomalies, and transform maritime telemetry into explainable operational intelligence.

«Real AIS. Real trajectories. No synthetic vessels. No fabricated results.»

---

Overview

Raw AIS data tells us where vessels are and how they are moving.
MIE is designed to go one step further: transforming vessel telemetry into behavioral context.

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

The central question is not only:

«Where is the vessel?»

but also:

«How is it moving, how does its behavior compare with other observed vessels, and which patterns deserve further investigation?»

---

Core Capabilities

📡 Real-Time AIS Ingestion

- AISStream WebSocket integration
- Real vessel telemetry
- Server-side Bounding Box filtering
- Configurable collection windows
- Explicit connection and data states
- Session-based collection

🚢 Vessel Tracking

- MMSI-based tracking
- Individual vessel trajectories
- Position history
- Speed over ground
- Course over ground
- Heading
- Vessel-level investigation

🧭 Trajectory Intelligence

MIE converts raw position reports into behavioral features such as:

- position;
- speed;
- course;
- heading;
- distance traveled;
- time delta;
- computed speed;
- heading changes;
- track duration;
- signal gaps.

These features form the foundation of the behavioral intelligence layer.

🤖 Behavioral Anomaly Detection

MIE combines unsupervised machine learning with interpretable rules.

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

The objective is to identify unusual behavioral patterns, not automatically classify vessels as threats.

🔎 Explainable Findings

Machine-learning outputs are complemented by deterministic rules covering patterns such as:

- unusual speed;
- prolonged stops;
- signal gaps;
- significant heading changes;
- unusual movement behavior.

The system is designed to provide analytical signals with context, rather than unexplained anomaly scores.

🗺️ Geospatial Intelligence

The operational workspace provides:

- live vessel positions;
- trajectory visualization;
- geographic filtering;
- Bounding Box control;
- vessel selection;
- behavioral overlays;
- heading visualization;
- interactive maps.

📊 Data Quality

Data quality is treated as part of the intelligence pipeline.

The system monitors conditions including:

- invalid MMSI;
- invalid coordinates;
- impossible speeds;
- impossible geographic jumps;
- duplicate observations;
- missing data;
- signal gaps;
- stale observations.

When real AIS data is unavailable, MIE does not fabricate vessels or trajectories.

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
                ┌─────────────────┐   ┌──────────────────┐
                │ Operational UI  │   │ Historical Store │
                │ Streamlit / Map │   │ PostgreSQL/PostGIS│
                └─────────────────┘   └──────────────────┘

---

System Design Principles

Real Data First

MIE is built around real AIS observations.

The platform does not generate synthetic vessels or artificial trajectories to make the operational interface appear populated.

No Real AIS
     ↓
No Artificial Vessels
     ↓
No Fabricated Intelligence

This principle is fundamental to the project.

---

Explicit System States

The platform distinguishes between operational states such as:

- "LIVE"
- "DISCONNECTED"
- "STALE"
- "WAITING FOR DATA"
- "INSUFFICIENT DATA"
- "HISTORICAL DATABASE UNAVAILABLE"

This prevents infrastructure failures or missing observations from being mistaken for analytical results.

---

Live and Historical Data

Live operational analysis and historical persistence are intentionally separated.

                    Real AIS
                       │
                       ▼
                 Session Store
                  /         \
                 /           \
                ▼             ▼
        Live Analysis     PostgreSQL
                              │
                              ▼
                           PostGIS

The historical layer is optional and decoupled from the live ingestion pipeline.

---

Vessel Intelligence

The vessel-level workspace combines:

Vessel Identity
      +
Telemetry
      +
Trajectory
      +
Behavior
      +
Anomaly Findings

This allows an operator to move from a global maritime picture to the detailed analysis of an individual MMSI.

---

Behavioral Intelligence

The current MIE architecture focuses on session-relative behavioral analysis.

The machine-learning pipeline learns the structure of the real trajectories available during the analytical session.

Therefore, the current system should be understood as:

«Real-time exploratory behavioral intelligence»

rather than a universal pre-trained maritime behavior model.

This distinction is intentional and keeps analytical interpretation technically honest.

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

Configure the required AISStream credentials using the application's supported secrets/environment configuration.

Never commit API keys or credentials to the repository.

Run

streamlit run app.py

---

Historical Persistence

PostgreSQL/PostGIS can be used for historical maritime data persistence.

The architecture supports:

- session storage;
- observation persistence;
- geospatial data;
- historical vessel observations;
- database health diagnostics.

Historical persistence remains decoupled from the real-time collection pipeline.

---

Testing

The project includes automated tests covering core components including:

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

---

Roadmap

                 ┌─────────────────────┐
                 │    Real-Time AIS    │
                 └──────────┬──────────┘
                            ↓
                 ┌─────────────────────┐
                 │   AIS Static Data   │
                 └──────────┬──────────┘
                            ↓
                 ┌─────────────────────┐
                 │ Historical Behavior │
                 │     Baselines       │
                 └──────────┬──────────┘
                            ↓
                 ┌─────────────────────┐
                 │ Advanced Geospatial │
                 │    Intelligence     │
                 └──────────┬──────────┘
                            ↓
                 ┌─────────────────────┐
                 │ Multimodal Maritime │
                 │    Intelligence     │
                 └──────────┬──────────┘
                            ↓
                 ┌─────────────────────┐
                 │ AIS + Visual + SAR  │
                 │   + External Data   │
                 └─────────────────────┘

---

Future Vision

The long-term direction is to evolve from AIS-focused behavioral intelligence toward multimodal maritime perception and intelligence.

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

The goal is to provide:

«Better data. Better context. Better signals. Better explanations.»

---

What MIE Is — and Is Not

MIE is

- a real-time AIS intelligence platform;
- a vessel trajectory analysis system;
- a behavioral anomaly detection engine;
- a geospatial operational workspace;
- an experimental foundation for maritime intelligence.

MIE is not

- a physical radar;
- a sonar system;
- a universal threat detector;
- a pre-trained universal maritime behavior model;
- a guarantee of vessel intent.

AIS also has an important limitation:

«An AIS-only system cannot automatically detect a vessel that is not transmitting usable AIS data.»

This limitation is one of the reasons the long-term architecture is designed to evolve toward multiple data sources.

---

Design Philosophy

MIE deliberately separates:

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

An anomaly is therefore treated as a signal for investigation, not proof of malicious intent.

This distinction is central to responsible maritime intelligence.

---

Why This Project?

MIE combines multiple areas of modern engineering into one end-to-end system:

- Data Engineering
- Real-Time Streaming
- Geospatial Computing
- Machine Learning
- Unsupervised Learning
- Anomaly Detection
- Data Quality Engineering
- Backend Architecture
- Database Engineering
- Visualization
- Operational UI

Rather than treating these as isolated experiments, MIE connects them into a single operational pipeline.

---

License

This project is licensed under the MIT License.

See the ""LICENSE"" (LICENSE) file for the complete license text.

---

Author

Carlos Eduardo Moraes

Quantitative Developer · Data Science · Computer Engineering

---

Maritime Intelligence Engine

Real AIS → Trusted Data → Trajectories → Behavior → Intelligence

Built as an engineering and research platform for real-time maritime behavioral intelligence.