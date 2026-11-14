# MIE — Front-End Design Specification
## Maritime Intelligence Command & Control Interface

**Specification date:** 2026-11-14  
**Repository:** `edu-moraess/vyra-maritime-intell`  
**Target branch:** `fix/mie-p0-async-collection-safety`  
**Status:** Design specification — not an implementation or visual validation  
**Product direction:** Concept B — Geospatial Intelligence Workspace

---

## 1. Purpose and design intent

Evolve the existing MIE front end from a maritime monitoring dashboard into a disciplined **Maritime Intelligence Command & Control Interface**.

The design should communicate operational awareness, evidence traceability, system state and analytical context. It must not imitate a specific military product or use decorative militarization as a substitute for functionality.

The map remains the primary analytical surface. The five approved Concept B environments remain intact:

1. Operational Overview
2. Geospatial Intelligence
3. Vessel Intelligence
4. Behavioral & Temporal Intelligence
5. Data Quality & Observability

Collection & Session Management remains transversal.

### Non-goals and safety boundaries

This specification is presentation-only. It does not authorize changes to:
- AIS ingestion, provider subscriptions, collection lifecycle or worker behavior;
- engine, analytics, model inference, anomaly logic or temporal processing;
- session identity, regional isolation, persistence or database behavior;
- credentials, environment variables, Supabase configuration or deployment;
- data contracts or public interfaces.

No synthetic vessels, fabricated events, simulated connectivity, invented sensor states or decorative operational metrics may be introduced. Missing evidence must remain visibly unavailable.

---

## 2. Reference system

The following products and institutions inform design principles. They are references, not templates to copy.

| MIE area | Reference | Design principle to adapt |
|---|---|---|
| Command Header | Anduril Lattice | Compact operational context and system-level awareness |
| Geospatial Workspace | Palantir Foundry Map / Gotham | Layer management, object selection and map-centered investigation |
| Operational Event Center | NATO Situation Centre | Prioritized situational information and event dissemination |
| Intelligence Workspace | Thales TACTICOS | Function-oriented naval operations layout and consistent information hierarchy |
| System Observability | Anduril Lattice | Sensor/source availability and integrated operational state |
| Mobile Interface | ATAK-CIV / TAK | Map-first interaction, overlays and touch-accessible controls |

### Reference links

- Anduril — Lattice: https://www.anduril.com/lattice
- Palantir — Foundry documentation: https://www.palantir.com/docs/foundry/
- Palantir — Map documentation: https://www.palantir.com/docs/foundry/map/
- NATO — Situation Centre context: https://www.nato.int/
- Thales — Naval forces: https://www.thalesgroup.com/en/markets/defence-and-security/naval-forces
- TAK — public ecosystem: https://tak.gov/
- ATAK-CIV — Android application: https://play.google.com/store/apps/details?id=com.atakmap.app.civ

Availability and exact capabilities of vendor interfaces may vary by product edition and access. Public screenshots and product material should be treated as visual inspiration, not evidence of internal implementation details.

---

## 3. Global visual language

### 3.1 Design principles

- **Map first:** the geospatial surface is the main workspace, not a decorative background.
- **Evidence before interpretation:** observations, calculations, estimates and unavailable values must be distinguishable.
- **Operational hierarchy:** critical state is immediately visible; secondary detail is progressively disclosed.
- **Persistent context:** selected region, selected vessel, time scope and session context should remain understandable during navigation.
- **Low-noise density:** compact information, restrained borders and deliberate spacing.
- **Responsive by design:** mobile layout must preserve core tasks, not merely shrink desktop columns.

### 3.2 Proposed design tokens

| Token | Value | Intended use |
|---|---|---|
| Base | `#0A1118` | Application background |
| Surface | `#111E29` | Panels and workspace surfaces |
| Surface elevated | `#172733` | Nested cards and selected regions |
| Border | `#263A47` | Dividers and subtle outlines |
| Text primary | `#DCE5EA` | Main content |
| Text secondary | `#91A4B0` | Labels and metadata |
| Geospatial cyan | `#39A9C7` | Map selection and geospatial emphasis |
| Warning amber | `#D5A34A` | Attention / degraded state |
| Critical red | `#D45B5B` | Confirmed critical condition |
| Operational green | `#63A68A` | Confirmed healthy/online state |

Color is semantic. Green must not be used as a general decorative accent. Red is reserved for actual critical states. Never use color as the only carrier of status; pair it with text or an icon.

### 3.3 Typography and geometry

- Use a highly legible UI sans-serif for primary content.
- Use monospaced numerals for UTC timestamps, MMSI, coordinates, rates and telemetry.
- Prefer compact uppercase labels for section identifiers, not for long descriptions.
- Use consistent spacing increments and restrained corner radii.
- Avoid excessive glow, neon, gradients, animated scanlines, faux radar effects and ornamental military insignia.

---

## 4. Panel specifications

## 4.1 Command Header — reference: Anduril Lattice

**Purpose:** establish what system is being viewed and whether its operational state is known.

**Content hierarchy:**
1. MIE / ARQTECH LABS identity.
2. Active workspace and selected region context.
3. UTC clock.
4. AIS connection / session state.
5. Data freshness and system integrity indicators.

**Behavior:**
- Keep the header compact and persistent across workspaces.
- Distinguish NOT CONFIGURED, DISCONNECTED, CONNECTING, CONNECTED, DEGRADED and UNKNOWN only when supported by existing state contracts.
- Do not infer CONNECTED from the presence of cached vessels.
- Do not add a second source of truth for connection state.

**Acceptance criteria:**
- Operator can identify the application, active context and connection state at a glance.
- Header does not displace the map or create excessive vertical height on mobile.
- Displayed states come from existing runtime evidence.

## 4.2 Tactical Geospatial Workspace — reference: Palantir Map

**Purpose:** make map-based exploration and investigation the central activity.

**Existing capabilities to preserve:** SPLIT / UNIFIED modes, Region A/B selection, map controls, observed trails, heading vectors, freshness, anomaly overlays, traffic hexbin and vessel selection.

**Visual hierarchy:**
1. MAP CONTROLS rail.
2. Map surface(s).
3. Legend and scale/context.
4. Selected-vessel contextual information.
5. Supporting regional/environmental evidence.

**MAP CONTROLS rail:**
- Preserve the existing four-part desktop arrangement:
  **MAP CONTROLS | DATA | ANALYSIS | SYSTEM**.
- Keep the four controls aligned in the same workspace rail.
- Do not relocate DATA / ANALYSIS / SYSTEM below the map.
- Preserve current click/touch behavior and Streamlit state keys unless a separately reviewed implementation plan authorizes changes.

**Map requirements:**
- Use consistent vessel symbols and distinguish live from stale targets.
- Make trails, heading vectors, anomaly overlays and traffic layers visually distinguishable.
- Include a readable legend for active overlays.
- Make selected vessel and selected region states unambiguous.
- Keep environmental model context visually separate from AIS observations.
- Do not imply that the map is suitable for navigation.

**Acceptance criteria:**
- An operator can identify the active region, active layers and selected vessel.
- SPLIT mode keeps Region A and Region B analytically distinct.
- UNIFIED mode communicates that both regions are shown in one viewport.
- No overlay is shown as observed evidence if it is estimated or model-derived.

## 4.3 Operational Event Center — reference: NATO Situation Centre

**Purpose:** provide a traceable queue of events requiring attention.

**Recommended event row fields:**
- Priority: CRITICAL / HIGH / MEDIUM / INFORMATIONAL.
- Event timestamp (UTC).
- Event type.
- Region.
- Related MMSI, when applicable.
- Evidence/source reference.
- Review or acknowledgement state, only if that state exists.

**Behavior:**
- Sort by an explicit, documented rule (normally severity and recency).
- Selecting an event should navigate to its vessel/map context when the underlying references exist.
- Keep raw observation, derived finding and analyst interpretation distinct.
- Do not create threat labels or operational conclusions from anomaly scores alone.

**Acceptance criteria:**
- Every event can be traced to a source and time.
- Empty state says no events are available in the selected scope; it must not create sample events.
- Priority labels have documented semantics.

## 4.4 Intelligence Workspace — reference: Thales TACTICOS

**Purpose:** make the existing DATA, ANALYSIS and SYSTEM panels feel like coordinated parts of one operational workspace.

**Desktop rail:**
- Maintain the current shared rail beside MAP CONTROLS on Overview.
- Keep the same three panel identities on secondary pages, positioned according to the approved page layout.
- Use consistent expander headers, touch targets, spacing and typography.
- Do not introduce duplicate navigation state.

**DATA:**
- Message and record counts.
- Quality percentage and validation context.
- Freshness / stale counts where supported.
- Clear time scope and source.

**ANALYSIS:**
- Existing module navigation and subareas.
- Selected module and subarea should remain visually clear.
- Avoid adding navigation options that do not correspond to implemented pages.

**SYSTEM:**
- Connection state.
- Worker/reconnect telemetry.
- Queue depth and dropped messages.
- Temporal readiness.
- Historical persistence configuration/result.
- Operator timezone.

**Acceptance criteria:**
- Each panel has one clear responsibility.
- Values are sourced from existing engine snapshots and contracts.
- Panel interaction remains reliable during Streamlit reruns and fragment updates.
- No panel displays fabricated defaults as operational measurements.

## 4.5 System Observability — reference: Anduril Lattice

**Purpose:** explain whether the platform and its data paths are functioning.

**Recommended information groups:**
- Provider / AIS connection.
- Ingestion worker and reconnect telemetry.
- Queue depth and dropped messages.
- Data freshness and stale target counts.
- Validation and data quality.
- Temporal readiness and coverage.
- Historical persistence and last result.
- Component-level availability, where measurable.

**State vocabulary:**
- HEALTHY: positive evidence of normal operation.
- DEGRADED: operation continues with a known limitation.
- FAILED: a confirmed failure.
- NOT CONFIGURED: required configuration is absent.
- NOT READY: prerequisites for a capability are not met.
- UNKNOWN: evidence is insufficient to determine state.

**Acceptance criteria:**
- Every status has a source and a defined meaning.
- UNKNOWN is preferred to an unsupported healthy/unhealthy claim.
- Historical persistence state is not conflated with live ingestion state.

## 4.6 Mobile Command Interface — reference: ATAK-CIV

**Purpose:** preserve map-first situational awareness on narrow screens.

**Responsive behavior:**
- Keep the command header compact.
- Preserve access to MAP CONTROLS, DATA, ANALYSIS and SYSTEM.
- At narrow widths, stack or horizontally scroll the control rail without clipping or shrinking touch targets.
- Prefer one primary map at a time in narrow SPLIT layouts, with an explicit way to switch between Region A and Region B; retain a comparison path.
- Keep selected-vessel details accessible without permanently covering the map.
- Avoid fixed-position panels that obscure map controls or content.
- Respect mobile safe areas and Streamlit's native interaction model.

**Acceptance criteria:**
- No horizontal overflow at the target mobile viewport.
- All controls are reachable and have touch-safe targets.
- Returning to Overview restores the correct rail placement.
- Secondary pages retain their approved top-of-page control placement.
- No control becomes inert after navigation or fragment reruns.

---

## 5. Cross-panel interaction model

The following user journey should be coherent without changing engine semantics:

1. Operator opens Operational Overview and sees the current system state.
2. Operator selects a region and map layer.
3. Operator selects a vessel or an evidence-backed event.
4. MIE opens the corresponding Vessel Intelligence context.
5. Operator examines observed telemetry, movement and available historical context.
6. Operator opens Behavioral & Temporal Intelligence to inspect the relevant finding and its evidence.
7. Operator returns to the map without losing the investigation context.
8. Operator opens Data Quality & Observability to understand freshness, coverage or system limitations.

Navigation must preserve context only where the existing application state model supports it. Region A/B isolation and session boundaries must not be weakened.

---

## 6. Evidence and provenance presentation

Use explicit labels consistently:

- **OBSERVED:** directly present in source observations.
- **DERIVED:** computed deterministically from observations.
- **MODEL OUTPUT:** produced by a statistical or ML model.
- **ESTIMATED:** inferred or forecast by an external model/provider.
- **PERSISTED:** retrieved from historical storage.
- **UNAVAILABLE:** not present or not accessible.
- **UNKNOWN:** state cannot be established from current evidence.

Every time-sensitive value should expose its relevant timestamp or age. Every external/model-derived value should identify its source. Live session evidence must remain distinct from persisted historical evidence.

---

## 7. Implementation sequence

This document is a design baseline. Implementation should be split into small, independently reviewable front-end increments.

| Phase | Scope | Constraint |
|---|---|---|
| UI-01 | Design tokens and command header | Presentation only |
| UI-02 | Overview rail and geospatial visual hierarchy | Preserve existing rail position and map behavior |
| UI-03 | Event Center presentation | Use existing event/finding evidence only |
| UI-04 | DATA / ANALYSIS / SYSTEM consistency | Preserve callbacks, state keys and runtime contracts |
| UI-05 | Mobile responsiveness | Validate on actual Android viewport |
| UI-06 | Cross-page continuity and visual polish | No engine or session changes |

### Required workflow for each phase

1. Read-only audit of the relevant UI files and current branch.
2. Identify exact render functions, state keys, fragment boundaries and existing tests.
3. Propose a minimal patch limited to presentation.
4. Review the diff before applying it.
5. Run a single consolidated Colab validation cell where automated checks are applicable.
6. Perform visual validation on desktop and Android.
7. Record commit, evidence, test output and remaining limitations.

Do not add GitHub Actions/workflows for this work.

---

## 8. Visual validation checklist

- [ ] Header communicates actual state and active context.
- [ ] Overview rail order is MAP CONTROLS | DATA | ANALYSIS | SYSTEM.
- [ ] The four controls remain aligned in the same rail on desktop.
- [ ] Overview rail placement is correct after navigating away and back.
- [ ] Secondary-page rail placement remains correct.
- [ ] Map overlays have a readable legend and semantic distinction.
- [ ] Live, stale, persisted and model-derived evidence are distinguishable.
- [ ] Empty and unavailable states do not fabricate activity.
- [ ] Event rows expose source, timestamp and region.
- [ ] Vessel investigation retains supported context across navigation.
- [ ] Mobile controls are reachable and do not overlap the map.
- [ ] No engine, ingestion, session, persistence or database behavior changed.

---

## 9. Completion definition

The design system is considered implemented only after:
- the relevant UI changes are committed to the approved feature branch;
- automated validation has been run and its output recorded;
- desktop and Android visual checks have been completed;
- navigation and touch interactions have been exercised;
- no unauthorized engine/data behavior has changed;
- remaining limitations are explicitly documented.

## 10. Implementation log

### UI-01 — Design tokens and Command Header

**Code commit:** `f3dc002e9037b940689818144b228128c0754ae5`  
**File changed:** `src/ui/presentation.py`

Implemented:
- Applied the approved base, surface, border, text, geospatial, warning, critical and operational color tokens to the existing CSS variables.
- Reworked the shared header identity to show MIE / ARQTECH LABS and the active workspace name.
- Expanded the UTC timestamp to include the date.
- Added compact responsive wrapping rules for the command header.
- Preserved the existing ingestion status as the sole source for the displayed connection state.

Not changed:
- No engine, ingestion, collection, session, persistence, analytics, model or database code.
- No navigation keys, callbacks, fragment boundaries or workspace rail placement.

**Validation status:** GitHub source and commit diff were re-read and checked for the intended token/header changes. Automated tests, Python compilation, deployment and desktop/Android visual validation have not yet been run.

**Current status:** UI-01 source change committed; awaiting consolidated Colab validation and visual review before UI-02.


### UI-02 — Tactical map legend hierarchy

**Code changes:**
- Grouped the existing tactical map legend into TARGET STATUS and MOVEMENT.
- Added the already-supported STALE target state to the legend.
- Replaced the previous triangle glyphs with neutral status swatches; retained a ring for SELECTED and line treatments for observed tracks and heading/COG vectors.
- Added responsive styling using the existing MIE design tokens.
- Added a source-level unit test for legend coverage.

**Preserved:**
- No changes to vessel classification, AIS data, map layers, layer toggles, selection handling, map keys, session state, controls rail, engine or ingestion behavior.

**Validation status:** Source changes and test were committed; automated tests, Python compilation, deployment and desktop/Android visual validation remain pending.


### UI-02 follow-up — Hide native Streamlit chrome

- Hid the native Streamlit header, toolbar, decoration/status widgets, Main Menu and footer through presentation-layer CSS.
- Kept the MIE command header intact because it is rendered in the application body, independently of Streamlit's native header.
- Removed the top padding reserved for the native chrome.
- No application controls, navigation, session state, data, or runtime behavior changed.
- Visual confirmation in the deployed app remains pending.

### UI follow-up — Restore Streamlit sidebar access

**Code commit:** `5fe322c039d7a34eed51fcfa6a1f40a64af58ec0`  
**File changed:** `src/ui/presentation.py`

- Kept Streamlit's native header shell visible with a transparent background instead of hiding the entire header.
- Explicitly preserved the sidebar expansion control using the supported test-id selectors for current/older Streamlit variants.
- Continued hiding the nonessential toolbar, decoration/status widgets, Main Menu and footer.
- Left the Streamlit Cloud app-management control untouched; this application CSS does not target it.
- No engine, ingestion, session, navigation, data, persistence or database behavior changed.

**Validation status:** GitHub source update committed. Automated tests, Python compilation, deployment and visual confirmation on Android remain pending.

### UI follow-up — Use native Streamlit header and sidebar behavior

**Code commit:** `5eaadb2c35f4212f5cbff9e8ac5401e28b57c380`  
**File changed:** `src/ui/presentation.py`

- Removed the custom CSS overrides for the native Streamlit header and sidebar toggle.
- Streamlit now controls the header visibility, appearance and sidebar expansion control using its native behavior.
- Kept the existing rules for nonessential toolbar/decoration/status elements and footer; the Cloud app-management UI remains outside this app-level change.
- No engine, ingestion, collection, session, data, persistence or database behavior changed.

**Validation status:** Source update committed and pending visual confirmation in the deployed app, especially sidebar expansion on Android.

### UI follow-up — Restore visible native navigation controls

**Code commit:** `9ea9a06a1acc5a443e3b992ba9c0f5829a17b1f9`

The previous adjustment still hid Streamlit's toolbar and menu, which prevented the native header/navigation controls from appearing in the mobile screenshot. This follow-up removes those hiding rules and the forced zero top-padding override. Streamlit now controls its native header, toolbar and sidebar navigation. Only the decorative top stripe and footer remain hidden. The Cloud app-management control is not modified.

**Validation:** GitHub source verification pending below; visual confirmation in the deployed mobile app remains pending.

### UI follow-up — Prevent MIE identity clipping below native header

**Code commit:** `aa051f985937160e5d8d63563623bac920c26df3`

The mobile screenshot showed the first line of the MIE command identity clipped after restoring Streamlit's native header. Increased the top padding of the main Streamlit block container from `.75rem` to `1.5rem` so the application identity has breathing room below the native header. No header/sidebar controls or application behavior were changed.

**Validation:** GitHub source update committed; deployed visual confirmation remains pending.

### UI follow-up — Align ingestion status with page context

**Code commit:** `f2921f9c345da0bfa0faa79b523b79284d725429`

Adjusted the command-header layout so the MIE identity remains on its own first row, while the page context (for example, `OVERVIEW · MARITIME INTELLIGENCE`) and ingestion status/UTC clock share the following row. The status and clock remain visible; their spacing and clock font are compacted to suit the mobile viewport. No ingestion or status logic changed.

**Validation:** Source committed; deployed visual confirmation remains pending.

### UI follow-up — Prevent collection notices from preceding the command header

**Code commit:** `faa619f998a292da268eac21857f132e8aed23f1`

The mobile screenshot exposed a yellow/amber strip above the MIE identity. Source inspection identified the cause: finite-collection notices and collection diagnostics were rendered before `render_header()` inside the timed Overview and secondary-workspace fragments. Reordered presentation so the command header is rendered first and operational notices/diagnostics follow it. No notice, diagnostic, status source, collection behavior or engine logic was removed or changed.

**Validation:** GitHub source ordering verified; automated tests and deployed visual confirmation remain pending.

**Follow-up correction:** commit `6789b5df78c0c6df19a6700db36a61b985ce1c1c` keeps active-page resolution ahead of header rendering in the secondary-page fragment. This preserves the current page label while ensuring the header precedes collection notices. Source order was re-read from the branch after this correction.

### UI follow-up — Render live-monitoring feedback below the MIE header

**Code commit:** `c0e402530f70db0891aa35b27b5ac1b82a9e3451`

The mobile screenshot showed the green “Continuous AIS monitoring started” confirmation above the MIE command header. The message was consumed and rendered in `main()` before either timed workspace fragment rendered its header. The result is now consumed exactly once inside the active workspace fragment, immediately after `render_header()`. Both Overview and secondary workspaces follow the same order. The feedback remains visible; only its placement changed.

**Validation:** GitHub source verification completed; deployed visual confirmation remains pending. No ingestion, worker, session, engine, or persistence behavior changed.
