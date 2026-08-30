"""Tests for Wikimedia-only vessel photo enrichment (mocked HTTP)."""
from __future__ import annotations
from unittest.mock import MagicMock
import httpx
from src.enrichment.vessel_photo import VesselPhoto, resolve_vessel_photo, _lookup_qid_by_mmsi, _fetch_p18_title, _download_commons_image
def test_invalid_mmsi_returns_none():
    assert resolve_vessel_photo("123") is None
    assert resolve_vessel_photo("") is None
def test_unique_qid_lookup():
    client=MagicMock(spec=httpx.Client); resp=MagicMock(); resp.status_code=200
    resp.json.return_value={"results":{"bindings":[{"item":{"value":"http://www.wikidata.org/entity/Q123"}}]}}
    client.get.return_value=resp
    assert _lookup_qid_by_mmsi(client,"235102528")=="Q123"
def test_ambiguous_mmsi_rejected():
    client=MagicMock(spec=httpx.Client); resp=MagicMock(); resp.status_code=200
    resp.json.return_value={"results":{"bindings":[{"item":{"value":"http://www.wikidata.org/entity/Q1"}},{"item":{"value":"http://www.wikidata.org/entity/Q2"}}]}}
    client.get.return_value=resp
    assert _lookup_qid_by_mmsi(client,"235102528") is None
def test_missing_p18():
    client=MagicMock(spec=httpx.Client); resp=MagicMock(); resp.status_code=200; resp.json.return_value={"claims":{}}
    client.get.return_value=resp
    assert _fetch_p18_title(client,"Q123") is None
def test_p18_title_prefixed():
    client=MagicMock(spec=httpx.Client); resp=MagicMock(); resp.status_code=200
    resp.json.return_value={"claims":{"P18":[{"mainsnak":{"datavalue":{"value":"Example ship.jpg"}}}]}}
    client.get.return_value=resp
    assert _fetch_p18_title(client,"Q123")=="File:Example ship.jpg"
def test_commons_download_success():
    client=MagicMock(spec=httpx.Client)
    meta=MagicMock(); meta.status_code=200
    meta.json.return_value={"query":{"pages":{"1":{"imageinfo":[{"mime":"image/jpeg","url":"https://example.test/ship.jpg","thumburl":"https://example.test/ship_thumb.jpg","descriptionurl":"https://commons.wikimedia.org/wiki/File:Ship.jpg","extmetadata":{"LicenseShortName":{"value":"CC BY-SA 4.0"},"Artist":{"value":"Photographer"}}}]}}}}
    img=MagicMock(); img.status_code=200; img.content=b"\xff\xd8\xfffakejpeg"
    client.get.side_effect=[meta,img]
    photo=_download_commons_image(client,"File:Ship.jpg",qid="Q9")
    assert isinstance(photo,VesselPhoto) and photo.verified and photo.license_name=="CC BY-SA 4.0"
def test_http_failure_soft():
    client=MagicMock(spec=httpx.Client); client.get.side_effect=httpx.ConnectError("down")
    assert resolve_vessel_photo("235102528", client=client) is None
def test_no_fallback_provider_strings_in_module():
    from pathlib import Path
    src=Path("src/enrichment/vessel_photo.py").read_text().lower()
    for banned in ("marinetraffic","shipspotting","fleetmon","vesselfinder"):
        assert banned not in src
def test_end_to_end_mocked_resolve():
    client=MagicMock(spec=httpx.Client)
    sparql=MagicMock(); sparql.status_code=200
    sparql.json.return_value={"results":{"bindings":[{"item":{"value":"http://www.wikidata.org/entity/Q42"}}]}}
    claims=MagicMock(); claims.status_code=200
    claims.json.return_value={"claims":{"P18":[{"mainsnak":{"datavalue":{"value":"Ship.jpg"}}}]}}
    commons=MagicMock(); commons.status_code=200
    commons.json.return_value={"query":{"pages":{"1":{"imageinfo":[{"mime":"image/jpeg","url":"https://example.test/a.jpg","descriptionurl":"https://commons.example/File:Ship.jpg","extmetadata":{"LicenseShortName":{"value":"CC0"},"Artist":{"value":"A"}}}]}}}}
    img=MagicMock(); img.status_code=200; img.content=b"abc123"
    client.get.side_effect=[sparql,claims,commons,img]
    photo=resolve_vessel_photo("235102528", client=client)
    assert photo is not None and photo.image_bytes==b"abc123"
