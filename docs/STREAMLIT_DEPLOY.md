Streamlit Community Cloud Deployment

This document describes the deployment and production-validation procedure for the Maritime Intelligence Engine (MIE).

The application is designed to start safely without AIS credentials. In that state, the interface must explicitly report that real AIS data is unavailable.

A deployment is not considered operational merely because the Streamlit application opens successfully.

The MIE is considered operational only after the deployed application receives and processes real AISStream messages.

---

1. Deployment Architecture

The production flow is:

GitHub Repository
       ↓
Streamlit Community Cloud
       ↓
MIE Streamlit Application
       ↓
AISStream WebSocket
       ↓
Real AIS Messages
       ↓
Validation
       ↓
Trajectory Reconstruction
       ↓
Behavioral Analytics
       ↓
Operational Intelligence

Historical persistence is an independent optional path:

Real AIS
   ↓
Session Store
   ├──→ Live Analysis
   │
   └──→ Optional PostgreSQL/PostGIS

A failure of the historical database must not terminate live AIS analysis.

---

2. Create the Streamlit Application

Open the official Streamlit Community Cloud platform:

"Streamlit Community Cloud" (https://reference-url-citation.invalid/0)

Select Create app and configure:

Setting| Value
Repository| "edu-moraess/maritime-intelligence-engine"
Branch| "main"
Main file| "app.py"

The repository visibility should follow the owner's intended GitHub and Streamlit account configuration.

---

3. Configure Streamlit Secrets

Open:

App settings → Secrets

Add the production configuration.

Example:

AISSTREAM_API_KEY = "<real-AISStream-key>"
AIS_AREA_MIN_LAT = "25.603"
AIS_AREA_MIN_LON = "-80.208"
AIS_AREA_MAX_LAT = "25.835"
AIS_AREA_MAX_LON = "-79.879"
AIS_COLLECTION_SECONDS = "60"
AIS_MAX_MESSAGES = "3000"
AIS_MAX_VESSELS = "1000"
AIS_STALE_AFTER_SECONDS = "180"
AIS_PROVIDER = "aisstream"

# Optional external PostgreSQL/PostGIS.
# Omit for LIVE-ONLY operation.
# DATABASE_URL = "<external-postgresql-url>"

# Historical persistence is explicitly opt-in.
HISTORICAL_PERSISTENCE_ENABLED = "false"

Security requirements

The AISStream API key:

- must come from the user's AISStream account;
- must never be committed to GitHub;
- must never be embedded in source code;
- must never be displayed in the application;
- must never appear in logs or diagnostic output.

The application reads the secret server-side through Streamlit Secrets.

The MIE does not establish an AISStream connection directly from the browser.

---

4. AIS Configuration

The Bounding Box values define the geographic monitoring region.

The semantic ordering is:

MIN_LAT < MAX_LAT
MIN_LON < MAX_LON

The application validates these values before collection.

Invalid geographic configuration must prevent collection rather than silently reverting to defaults.

A valid region change requires a new collection/subscription.

The application should communicate:

Region updated.
Collect again to open a new subscription.

---

5. Historical Persistence

Historical persistence is optional.

LIVE-ONLY

If "DATABASE_URL" is not configured:

HISTORICAL DATABASE NOT CONFIGURED

The application remains capable of live AIS analysis.

Persistence disabled

If "DATABASE_URL" exists but:

HISTORICAL_PERSISTENCE_ENABLED = "false"

the expected state is:

HISTORICAL PERSISTENCE OFF

No historical inserts should be performed.

Persistence enabled

Historical persistence requires both:

DATABASE_URL
+
HISTORICAL_PERSISTENCE_ENABLED = true

When enabled, the application uses the versioned migration system and persists only valid observations.

Historical persistence must never replace the live session state.

Database unavailable

If the configured historical database cannot be reached:

HISTORICAL DATABASE UNAVAILABLE

The live AIS session must remain operational whenever the AIS connection itself is healthy.

PostgreSQL/PostGIS must be hosted externally when deploying on Streamlit Community Cloud.

---

6. Post-Deployment Verification

After deployment, open the published application and perform the checks in order.

Verification| Expected evidence
Boot| MIE shell opens without fatal error
Credential| Sidebar reports configured status without exposing the secret
Connection| "Collect real AIS" transitions through "CONNECTING"
Live state| "LIVE AIS" appears only after real messages are received
Messages| Message counter becomes positive and increases
Last received| "LAST RECEIVED" shows a recent value
Map| Real observed vessels appear
Vessel data| MMSI and telemetry correspond to received AIS observations
Pages| Operational pages load without runtime errors
Data integrity| No fabricated traffic appears
Historical state| Correct persistence status is displayed
Security| Credentials are absent from UI, logs, responses, and source

---

7. Operational Pages

The deployed application should be checked across the available operational workspace, including:

- Overview;
- Vessels;
- Vessel Intelligence;
- Trajectory Analysis;
- Behavior;
- Anomalies;
- Traffic;
- Data Quality;
- System.

A page that requires analytical data may legitimately display an insufficient-data state.

For example:

Insufficient real observations

is valid behavior.

The application must not generate synthetic observations merely to populate an analytical page.

---

8. Live AIS Verification

The live verification procedure is:

Open deployed application
        ↓
Verify AIS credential status
        ↓
Select monitoring region
        ↓
Click Collect real AIS
        ↓
CONNECTING
        ↓
AISStream subscription
        ↓
Real PositionReport messages
        ↓
LIVE AIS
        ↓
Messages > 0
        ↓
Real vessels displayed

The following evidence should be observed:

Connection

CONNECTING

followed by a successful live state.

Live state

LIVE AIS

must only be displayed after real AIS messages have been received.

Message counter

The message count must become positive and increase during the collection window.

Vessel observations

The map and vessel views must contain observations corresponding to the received AIS messages.

Recency

"LAST RECEIVED" must indicate recent receipt activity.

---

9. Production Success Criteria

Do not declare the deployment "LIVE" merely because the Streamlit page opens.

The minimum live-AIS success criteria are:

LIVE AIS
+
MESSAGES > 0
+
recent LAST RECEIVED
+
real vessels observed

The displayed vessel information must originate from the live AIS messages received by the Streamlit process.

A successful application boot alone is insufficient evidence.

---

10. Failure States

The application must expose infrastructure and data limitations explicitly.

AIS unavailable

Expected:

DISCONNECTED

or:

REAL AIS DATA UNAVAILABLE

The application must not generate replacement vessel traffic.

Historical database unavailable

Expected:

HISTORICAL DATABASE UNAVAILABLE

Live AIS analysis should remain available if the AIS connection is healthy.

Historical persistence disabled

Expected:

HISTORICAL PERSISTENCE OFF

No historical writes should occur.

Historical database not configured

Expected:

HISTORICAL DATABASE NOT CONFIGURED

The application remains LIVE-ONLY.

---

11. Data Integrity Requirements

The deployed application must preserve the MIE data-integrity principles.

It must not fabricate:

- vessels;
- positions;
- trajectories;
- AIS observations;
- historical records;
- timestamps;
- network latency;
- behavioral findings;
- embeddings.

When real AIS data is unavailable, the system must expose that limitation.

No AIS
   ↓
No fabricated traffic

---

12. Temporal Integrity

The MIE uses UTC as its canonical analytical and storage reference.

AIS "PositionReport.Timestamp" represents the AIS second within the UTC minute and must not be interpreted as a Unix timestamp.

The application uses receive time for freshness and ordering.

Network latency must remain:

UNAVAILABLE

unless a trusted measurement source is available.

The deployment environment must not alter these temporal semantics.

---

13. Historical vs Live Data

The application must maintain a strict distinction between live session observations and historical observations.

Live/session data must not be labeled:

HISTORICAL AIS

unless it originates from the historical persistence layer.

The system should distinguish explicitly between:

LIVE AIS

and:

HISTORICAL DATABASE AVAILABLE

or the corresponding unavailable/off states.

Live availability must never be inferred from historical database state.

---

14. Security Checklist

Before considering the deployment complete, verify:

- [ ] AISStream API key is stored only in Streamlit Secrets.
- [ ] Database credentials are stored only in secrets/environment configuration.
- [ ] No credentials exist in Git history.
- [ ] No credentials appear in application logs.
- [ ] No credentials appear in the UI.
- [ ] No credentials are embedded in source code.
- [ ] "DATABASE_URL" is not exposed to the client.
- [ ] Historical persistence is explicitly enabled only when intended.
- [ ] No synthetic AIS provider is enabled.
- [ ] No fabricated vessels appear when AIS is unavailable.

---

15. Troubleshooting

Application does not boot

Check:

1. Streamlit main file is "app.py";
2. branch is "main";
3. dependencies are installed from "requirements.txt";
4. "packages.txt" contains only required OS packages;
5. the application logs for Python import errors.

---

AIS remains disconnected

Check:

1. "AISSTREAM_API_KEY" exists in Streamlit Secrets;
2. the secret name is exactly correct;
3. the API key is valid;
4. the Bounding Box is valid;
5. the selected provider is "aisstream";
6. a new collection was started after changing the region.

Do not interpret an unavailable AIS connection as evidence that no vessels exist in the region.

---

No vessels appear

Check:

1. the AIS connection reached "LIVE AIS";
2. the message counter is positive;
3. the monitoring region contains active AIS traffic;
4. the collection window is sufficiently long;
5. the received messages contain valid position reports.

Do not add simulated vessels to make the map appear populated.

---

Historical persistence does not work

Check:

1. "DATABASE_URL";
2. PostgreSQL/PostGIS availability;
3. migrations;
4. "HISTORICAL_PERSISTENCE_ENABLED";
5. database connectivity.

A historical persistence failure must not be treated as a live AIS failure.

---

16. Final Production Validation Record

After completing the deployment, record:

Deployment URL:
Deployment date:
Git commit:
AIS provider:
Monitoring region:
Collection duration:
Messages received:
Distinct vessels:
Last received:
Live state:
Historical database state:
Validation result:

This creates a reproducible record of the production verification.

---

17. Important Limitation

AISStream provides live AIS access through its WebSocket service and subscription model. It should not be treated as a durable historical replay source.

Therefore, live validation must be performed while the application is actively connected and receiving messages.

Historical analysis requires an independently persisted dataset.

See the official AISStream developer documentation:

"AISStream Developer Documentation" (https://reference-url-citation.invalid/1)

---

18. Deployment Status Definition

The MIE uses the following deployment interpretation:

DEPLOYED
   ↓
Application successfully starts

does not automatically mean:

LIVE

The operational definition is:

DEPLOYED
   +
AIS AUTHENTICATED
   +
REAL AIS MESSAGES RECEIVED
   +
REAL VESSELS OBSERVED
   =
LIVE AIS

Historical persistence is evaluated independently.

---

Conclusion

A successful Streamlit deployment establishes that the application can run in the target environment.

A successful LIVE AIS validation requires additional evidence from real AISStream observations.

The MIE therefore maintains a strict distinction between:

- application availability;
- AIS connectivity;
- real-data availability;
- analytical sufficiency;
- historical persistence.

This distinction is intentional and forms part of the project's engineering and data-integrity policy.