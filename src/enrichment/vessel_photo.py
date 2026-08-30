"""Wikidata + Wikimedia Commons vessel photo resolver.
MMSI → Wikidata P587 → unique Q-ID → P18 → Commons. No fallback.
"""
from __future__ import annotations
import logging, re
from dataclasses import dataclass
from typing import Any
import httpx
logger = logging.getLogger(__name__)
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "MaritimeIntelligenceEngine/1.0 (vessel-photo; educational)"
HTTP_TIMEOUT = 12.0
MAX_IMAGE_BYTES = 4_000_000
_MMSI_RE = re.compile(r"^\d{9}$")

@dataclass(frozen=True)
class VesselPhoto:
    image_bytes: bytes
    mime_type: str
    source_url: str
    commons_title: str
    license_name: str
    author: str
    qid: str
    verified: bool = True

def resolve_vessel_photo(mmsi: str, *, imo: str | None = None, client: httpx.Client | None = None) -> VesselPhoto | None:
    mmsi = str(mmsi or "").strip()
    if not _MMSI_RE.match(mmsi):
        return None
    owns = client is None
    if client is None:
        client = httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    try:
        qid = _lookup_qid_by_mmsi(client, mmsi)
        if not qid:
            return None
        if imo and not _qid_matches_imo(client, qid, str(imo).strip()):
            return None
        title = _fetch_p18_title(client, qid)
        if not title:
            return None
        return _download_commons_image(client, title, qid=qid)
    except Exception as exc:
        logger.info("Vessel photo resolve failed for %s: %s", mmsi, type(exc).__name__)
        return None
    finally:
        if owns:
            client.close()

def _lookup_qid_by_mmsi(client, mmsi):
    query = f'SELECT ?item WHERE {{ ?item wdt:P587 "{mmsi}" . }} LIMIT 5'
    resp = client.get(WIKIDATA_SPARQL, params={"format": "json", "query": query},
                      headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT})
    if resp.status_code != 200:
        return None
    qids = []
    for row in resp.json().get("results", {}).get("bindings", []):
        uri = row.get("item", {}).get("value", "")
        if "/entity/Q" in uri:
            qids.append(uri.rsplit("/", 1)[-1])
    return qids[0] if len(qids) == 1 else None

def _qid_matches_imo(client, qid, imo):
    if not imo:
        return True
    query = f"SELECT ?imo WHERE {{ wd:{qid} wdt:P458 ?imo . }} LIMIT 3"
    resp = client.get(WIKIDATA_SPARQL, params={"format": "json", "query": query},
                      headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT})
    if resp.status_code != 200:
        return False
    values = {str(b.get("imo", {}).get("value", "")).strip() for b in resp.json().get("results", {}).get("bindings", [])}
    return imo in values

def _fetch_p18_title(client, qid):
    resp = client.get(WIKIDATA_API, params={"action": "wbgetclaims", "entity": qid, "property": "P18", "format": "json"})
    if resp.status_code != 200:
        return None
    claims = resp.json().get("claims", {}).get("P18", [])
    if not claims:
        return None
    title = claims[0].get("mainsnak", {}).get("datavalue", {}).get("value")
    if not title or not isinstance(title, str):
        return None
    return title if title.startswith("File:") else f"File:{title}"

def _download_commons_image(client, file_title, *, qid):
    resp = client.get(COMMONS_API, params={"action": "query", "titles": file_title, "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata", "iiurlwidth": 800, "format": "json"})
    if resp.status_code != 200:
        return None
    pages = resp.json().get("query", {}).get("pages", {})
    if not pages:
        return None
    page = next(iter(pages.values()))
    if int(page.get("missing", 0) or 0) == 1 or "imageinfo" not in page:
        return None
    info = page["imageinfo"][0]
    mime = str(info.get("mime") or "")
    if not mime.startswith("image/"):
        return None
    url = info.get("thumburl") or info.get("url")
    if not url:
        return None
    meta = info.get("extmetadata") or {}
    def mv(k):
        n = meta.get(k) or {}
        return str(n.get("value") if isinstance(n, dict) else n or "").strip()
    license_name = mv("LicenseShortName") or mv("UsageTerms") or "Unknown"
    author = re.sub(r"<[^>]+>", "", mv("Artist") or mv("Attribution") or "Unknown").strip() or "Unknown"
    img = client.get(url)
    if img.status_code != 200 or not img.content or len(img.content) > MAX_IMAGE_BYTES:
        return None
    return VesselPhoto(image_bytes=img.content, mime_type=mime, source_url=str(info.get("descriptionurl") or url),
                       commons_title=file_title, license_name=license_name, author=author, qid=qid, verified=True)
