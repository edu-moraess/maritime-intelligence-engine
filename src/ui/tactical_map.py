"""Tactical maritime map helpers (presentation only)."""
from __future__ import annotations
from datetime import datetime, timezone
from math import cos, radians, sin
from typing import Any, Iterable

STATUS_FILL = {"NORMAL":[53,194,201,220],"ATTENTION":[233,184,87,230],"ANOMALY":[239,107,115,235],"CRITICAL":[220,50,60,245],"SELECTED":[255,255,255,250],"STALE":[121,147,155,180]}
STATUS_HALO = {"NORMAL":[53,194,201,50],"ATTENTION":[233,184,87,65],"ANOMALY":[239,107,115,85],"CRITICAL":[220,50,60,105],"SELECTED":[255,255,255,95],"STALE":[121,147,155,40]}
STATUS_RING = {"NORMAL":[53,194,201,0],"ATTENTION":[233,184,87,160],"ANOMALY":[239,107,115,200],"CRITICAL":[220,50,60,230],"SELECTED":[255,255,255,240],"STALE":[121,147,155,80]}
_SHIP_LOCAL = ((0.0,1.6),(0.55,-0.3),(0.45,-1.1),(-0.45,-1.1),(-0.55,-0.3))
VECTOR_BASE_DEG, VECTOR_MAX_DEG, VECTOR_SOG_REF, SHIP_SCALE_DEG = 0.010, 0.040, 15.0, 0.018
TACTICAL_MAP_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
TACTICAL_TOOLTIP_HTML = ("<div style='font-family:IBM Plex Mono,monospace;font-size:11px;line-height:1.45'>"
    "<div style='color:#35c2c9;font-weight:600'>{tooltip_name}</div>"
    "<div>MMSI {tooltip_mmsi}</div><div>SOG {tooltip_sog}</div>"
    "<div>COG {tooltip_cog}</div><div>HDG {tooltip_hdg}</div>"
    "<div>STATUS {tooltip_status}</div></div>")
TACTICAL_TOOLTIP_STYLE = {"backgroundColor":"rgba(7,17,22,0.94)","color":"#d9e6e9","border":"1px solid #1b3640","padding":"8px 10px"}

def resolve_vessel_course(heading_degrees, cog_degrees):
    for value in (heading_degrees, cog_degrees):
        if value is None: continue
        try: angle = float(value)
        except (TypeError, ValueError): continue
        if 0.0 <= angle < 360.0: return angle
    return None

def resolve_course_degrees(row):
    return resolve_vessel_course(row.get("heading_degrees"), row.get("cog_degrees"))

def classify_vessel_status(row, *, selected_mmsi, anomaly_mmsis, critical_mmsis):
    mmsi = str(row.get("mmsi") or "")
    if selected_mmsi and mmsi == selected_mmsi: return "SELECTED"
    if mmsi in critical_mmsis: return "CRITICAL"
    if mmsi in anomaly_mmsis: return "ANOMALY"
    if row.get("stale"): return "ATTENTION"
    try:
        messages = row.get("message_count")
        if messages is not None and int(messages) < 2: return "ATTENTION"
    except (TypeError, ValueError): pass
    return "NORMAL"

def anomaly_mmsi_sets(findings):
    anomaly, critical = set(), set()
    for finding in findings or []:
        mmsi = str(getattr(finding, "mmsi", "") or "")
        if not mmsi: continue
        anomaly.add(mmsi)
        try: score = float(getattr(finding, "score", 0.0) or 0.0)
        except (TypeError, ValueError): score = 0.0
        if score >= 0.85 or "critical" in str(getattr(finding, "category", "") or "").lower():
            critical.add(mmsi)
    return anomaly, critical

def ship_polygon(lat, lon, course_deg, *, scale_deg=SHIP_SCALE_DEG):
    angle = radians(float(course_deg) if course_deg is not None else 0.0)
    c, s = cos(angle), sin(angle)
    lon_scale = max(0.1, cos(radians(lat)))
    ring = []
    for x, y in _SHIP_LOCAL:
        east = (x * c + y * s) * scale_deg
        north = (-x * s + y * c) * scale_deg
        ring.append([max(-180.0, min(180.0, lon + east / lon_scale)), max(-90.0, min(90.0, lat + north))])
    ring.append(ring[0])
    return ring

def movement_vector_endpoint(lat, lon, course_deg, sog_knots):
    try: sog, course = float(sog_knots), float(course_deg)
    except (TypeError, ValueError): return None
    if sog <= 0.05 or not (0.0 <= course < 360.0): return None
    scale = min(1.0, max(0.15, sog / VECTOR_SOG_REF))
    dist = min(VECTOR_MAX_DEG, VECTOR_BASE_DEG + scale * (VECTOR_MAX_DEG - VECTOR_BASE_DEG))
    angle = radians(course)
    lon_scale = max(0.1, cos(radians(lat)))
    return (max(-90.0, min(90.0, lat + dist * cos(angle))), max(-180.0, min(180.0, lon + dist * sin(angle) / lon_scale)))

def enrich_tactical_rows(rows, *, selected_mmsi, anomaly_mmsis, critical_mmsis):
    enriched = []
    for raw in rows:
        row = dict(raw)
        status = classify_vessel_status(row, selected_mmsi=selected_mmsi, anomaly_mmsis=anomaly_mmsis, critical_mmsis=critical_mmsis)
        row["tactical_status"] = status
        row["fill_color"] = list(STATUS_FILL.get(status, STATUS_FILL["NORMAL"]))
        row["halo_color"] = list(STATUS_HALO.get(status, STATUS_HALO["NORMAL"]))
        row["ring_color"] = list(STATUS_RING.get(status, STATUS_RING["NORMAL"]))
        lat, lon = float(row["latitude"]), float(row["longitude"])
        course = resolve_course_degrees(row)
        row["course_degrees"] = course
        scale = SHIP_SCALE_DEG * (1.35 if status=="SELECTED" else 1.2 if status=="CRITICAL" else 1.1 if status=="ANOMALY" else 1.0)
        row["polygon"] = ship_polygon(lat, lon, course, scale_deg=scale)
        row["halo_radius"] = 650 if status=="SELECTED" else 420
        row["core_radius"] = 160 if status=="SELECTED" else 120
        try: sog_f = float(row["sog_knots"]) if row.get("sog_knots") is not None else None
        except (TypeError, ValueError): sog_f = None
        try: hdg_f = float(row["heading_degrees"]) if row.get("heading_degrees") is not None and 0 <= float(row["heading_degrees"]) < 360 else None
        except (TypeError, ValueError): hdg_f = None
        row["tooltip_name"] = str(row.get("name") or "UNKNOWN VESSEL")
        row["tooltip_mmsi"] = str(row.get("mmsi") or "UNKNOWN")
        row["tooltip_sog"] = f"{sog_f:.1f} kn" if sog_f is not None else "—"
        row["tooltip_cog"] = f"{course:.1f}°" if course is not None else "—"
        row["tooltip_hdg"] = f"{hdg_f:.0f}°" if hdg_f is not None else "—"
        row["tooltip_status"] = status
        tip = movement_vector_endpoint(lat, lon, course, sog_f) if course is not None and sog_f is not None else None
        if tip is not None:
            row["vector_end_lat"], row["vector_end_lon"] = tip
            row["has_vector"] = True
        else:
            row["vector_end_lat"], row["vector_end_lon"], row["has_vector"] = lat, lon, False
        enriched.append(row)
    return enriched

def build_track_segments(observations, *, selected):
    if not observations or len(observations) < 2: return []
    def _ts(obs):
        ts = getattr(obs, "received_at", None)
        if isinstance(ts, datetime):
            return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        return datetime.min.replace(tzinfo=timezone.utc)
    ordered = sorted(observations, key=_ts)
    times = [_ts(o) for o in ordered]
    span = max(1.0, (times[-1] - times[0]).total_seconds())
    segments = []
    for i in range(1, len(ordered)):
        a, b = ordered[i-1], ordered[i]
        age = (times[i] - times[0]).total_seconds() / span
        alpha = int(55 + age * (200 if selected else 130))
        color = [255,255,255,alpha] if selected else [53,194,201,max(35,alpha-45)]
        width = 2.8 if selected else 1.4
        segments.append({"path":[[float(a.longitude),float(a.latitude)],[float(b.longitude),float(b.latitude)]],"color":color,"width":width})
    return segments

def density_points_from_observations(observations, *, max_points=2500):
    points = []
    for obs in list(observations)[:max_points]:
        try: points.append({"longitude": float(obs.longitude), "latitude": float(obs.latitude)})
        except (TypeError, ValueError, AttributeError): continue
    return points

def legend_markdown():
    return ("<div style='display:flex;flex-wrap:wrap;gap:.85rem;align-items:center;font-family:IBM Plex Mono,monospace;font-size:0.66rem;color:#79939b;letter-spacing:.05em;margin:.3rem 0 .15rem'>"
            "<span style='color:#d9e6e9'>VESSEL STATUS</span>"
            "<span><span style='color:#35c2c9'>▲</span> NORMAL</span>"
            "<span><span style='color:#e9b857'>▲</span> ATTENTION</span>"
            "<span><span style='color:#ef6b73'>▲</span> ANOMALY</span>"
            "<span><span style='color:#dc323c'>▲</span> CRITICAL</span>"
            "<span><span style='color:#ffffff'>◎</span> SELECTED</span>"
            "<span style='color:#d9e6e9'>━━ TRACK</span>"
            "<span style='color:#e9b857'>→ VECTOR</span></div>")

def operational_strip(*, live_state, targets, tracks, anomalies, region):
    state_color = "#35c2c9" if "LIVE" in live_state.upper() else "#ef6b73"
    return (f"<div style='display:flex;flex-wrap:wrap;gap:1.1rem;align-items:center;font-family:IBM Plex Mono,monospace;font-size:0.68rem;letter-spacing:.07em;margin:0 0 .4rem;color:#79939b'>"
            f"<span style='color:{state_color};font-weight:600'>{live_state}</span>"
            f"<span>TARGETS {targets}</span><span>TRACKS {tracks}</span>"
            f"<span>ANOMALIES {anomalies}</span><span>REGION {region}</span></div>")
