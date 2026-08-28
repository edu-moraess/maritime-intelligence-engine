Validation Record

Validation date: 2026-08-27
Repository: "edu-moraess/maritime-intelligence-engine"
Branch: "main"

This document records the validation evidence available for the Maritime Intelligence Engine (MIE).

The validation distinguishes between automated tests, local runtime checks, visual/state checks, repository integrity, and remaining real-world validation requirements.

---

1. Validation Summary

Check| Result
"pytest -q"| ✅ Passed — 34 tests
"python3 -m compileall -q app.py src tests"| ✅ Passed
"git diff --check"| ✅ Passed
Streamlit health endpoint| ✅ Returned "ok" on local port 8501
Streamlit clean boot| ✅ Passed after full process restart
Streamlit navigation rerun| ✅ Overview → Vessels rendered without runtime or DOM exception
Bounding Box UI reversal| ✅ Correctly rejected
Valid region edit| ✅ Region update confirmed
GitHub publication| ✅ Completed on "main"

---

2. Automated Test Validation

The automated test suite validates core MIE behavior across configuration, AIS ingestion, trajectory processing, data quality, session storage, and analytical safeguards.

The current test suite includes coverage for:

- strict Bounding Box limits;
- partial runtime configuration;
- invalid runtime configuration;
- exact AISStream subscription fields;
- documented "PositionReport" parsing;
- invalid JSON rejection;
- invalid UTF-8 handling;
- non-position message rejection;
- AIS second-of-minute timestamp handling;
- real-record state transitions;
- no-message unavailability;
- trajectory mathematics;
- insufficient trajectory tracks;
- data-quality validation;
- duplicate counting;
- bounded message storage;
- bounded vessel storage;
- missing credentials;
- unsupported providers;
- session configuration errors;
- explicit no-pretrained-checkpoint provenance.

The current result was:

pytest -q
34 passed

The test suite does not provide a synthetic vessel-traffic dataset to the application.

---

3. Static and Repository Checks

Python Compilation

The application and test source tree were checked using:

python3 -m compileall -q app.py src tests

Result:

Passed

This confirms that the checked Python files compile successfully.

Git Diff Integrity

The repository was checked using:

git diff --check

Result:

Passed

No whitespace errors were reported by this check.

---

4. Streamlit Runtime Validation

The local Streamlit application was started and validated after a full process restart.

The health endpoint returned:

ok

The unified MIE shell loaded successfully.

Navigation was tested through:

Overview → Vessels

No runtime exception or previously reported DOM reconciliation failure was observed during this validation.

---

5. Expected Safe State Without AIS Credentials

The local Streamlit shell was intentionally opened without an AISStream credential.

The observed operational state was:

DISCONNECTED
AISSTREAM API KEY NOT CONFIGURED

The interface correctly showed:

Observed vessels: 0

and displayed the corresponding empty/insufficient-real-data states.

This behavior is considered correct.

Important interpretation

The disconnected state is not evidence that no vessels exist.

It means that the application does not currently have an authenticated AISStream connection capable of receiving live observations.

Likewise:

No AIS data
    ≠
No vessels exist

and:

Insufficient observations
    ≠
No anomaly exists

---

6. Bounding Box Validation

The Monitoring region controls were tested with invalid and valid geographic configurations.

Invalid configuration

Reversed latitude limits were rejected with:

min_lat must be strictly less than max_lat.

Valid configuration

A valid region update produced:

Region updated. Collect again to open a new subscription.

The application recreates the session engine before the next subscription, preventing observations from different regions from being mixed.

Validated default region

The corrected default region was observed as:

Parameter| Value
Min latitude| "25.603"
Min longitude| "-80.208"
Max latitude| "25.835"
Max longitude| "-79.879"

---

7. UI and DOM Integrity

The previous cross-element raw HTML panel wrappers were removed to eliminate the DOM-reconciliation risk associated with the reported "removeChild" failure.

After the hotfix:

- the local application booted successfully;
- the MIE shell rendered;
- navigation between tested pages worked;
- no "removeChild" exception was observed during the validation run.

This validation supports the conclusion that the reported UI failure was addressed in the tested local state.

---

8. Data Integrity

The repository configuration excludes sensitive and local artifacts including:

- ".env";
- Streamlit secrets;
- local databases;
- caches;
- compiled Python artifacts;
- temporary files.

No synthetic AIS provider is implemented.

No browser-side AISStream connection is implemented.

The application therefore maintains a clear separation between:

Real AIS ingestion
        ↓
Application processing
        ↓
Analytical state

and does not substitute fabricated traffic when real AIS data is unavailable.

---

9. Temporal Integrity

AIS "Timestamp" is retained according to its available second-of-minute semantics.

Receipt time is used for:

- freshness;
- ordering;
- runtime/session analysis.

The system does not fabricate an absolute observation timestamp or network latency when those values cannot be established from the available AIS information.

---

10. Synthetic Data Policy

The application does not implement a synthetic vessel provider as a fallback for unavailable AIS data.

Therefore:

AIS unavailable
      ↓
Show unavailable / insufficient-data state

rather than:

AIS unavailable
      ↓
Generate fictional vessels

This is an intentional integrity constraint.

---

11. Historical Data Integrity

Session data must not be relabeled as historical AIS merely because it remains available inside the application.

The deployed application must distinguish between:

- live/session observations;
- historical persisted observations;
- unavailable data.

The UI must never present session observations as:

HISTORICAL AIS

unless they originate from the historical persistence layer.

---

12. Analytical Interpretation

Behavioral analytics and anomaly detection are analytical mechanisms.

An anomaly score must not automatically be interpreted as:

- malicious intent;
- criminal activity;
- hostile behavior;
- confirmed threat.

The appropriate interpretation is:

Observed behavior
       ↓
Analytical signal
       ↓
Human investigation

The MIE system is designed to support investigation rather than automatically determine intent.

---

13. Real AIS Validation Still Required

The validation recorded in this document does not constitute proof of successful live AIS operation.

A complete online validation requires:

1. AISStream credentials configured by the user;
2. "AISSTREAM_API_KEY" configured in Streamlit Secrets;
3. the four "AIS_AREA_*" values configured;
4. a deployed Streamlit application;
5. a successful collection window;
6. receipt of real AIS observations;
7. confirmation that real vessels appear in the operational workspace.

The live verification procedure is documented in:

""STREAMLIT_DEPLOY.md"" (STREAMLIT_DEPLOY.md)

---

14. Remaining User Action

The hotfix commit:

235727355b6ffef821e31dda7e5543139e8cc584

is present on:

origin/main

The remaining deployment-side validation requires the user to:

- create or refresh the Streamlit Community Cloud application;
- configure "AISSTREAM_API_KEY";
- configure the four "AIS_AREA_*" values under Streamlit Secrets;
- start a live collection window;
- verify real AIS observations.

The deployment step is intentionally outside this validation record.

---

15. Validation Status

Validated

- Automated test suite
- Python compilation
- Git diff integrity
- Streamlit boot
- Streamlit health endpoint
- Streamlit navigation
- Bounding Box validation
- Region update behavior
- UI DOM stability in the tested local state
- Repository integrity controls
- No synthetic AIS fallback
- Temporal semantics
- Session-state behavior

Pending

- Live AISStream authentication
- Real-time AIS collection after deployment
- End-to-end production validation with real observations
- Long-running operational stability under continuous AIS ingestion

---

Conclusion

The MIE codebase has passed the documented automated and local runtime validation checks for the tested state.

The remaining validation boundary is explicitly identified: real-time AIS operation after deployment with valid AISStream credentials.

Until that step is performed, the system should be described as:

«Technically validated locally, with live AIS deployment validation pending.»

This distinction is intentional and preserves the integrity of the project's claims.