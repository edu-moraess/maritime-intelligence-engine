"""Tests for conservative, identity-matched Wikimedia vessel photos."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import httpx

from src.enrichment.vessel_photo import (
    VesselPhoto,
    _download_commons_image,
    _fetch_p18_title,
    _lookup_qid_by_mmsi,
    _qid_matches_name,
    resolve_vessel_photo,
)


def response(status=200, payload=None):
    item = MagicMock()
    item.status_code = status
    item.json.return_value = payload or {}
    return item


def test_invalid_or_unidentified_mmsi_returns_none():
    assert resolve_vessel_photo("123", expected_name="SHIP") is None
    assert resolve_vessel_photo("", expected_name="SHIP") is None
    assert resolve_vessel_photo("235102528", expected_name="UNKNOWN VESSEL") is None


def test_unique_qid_lookup():
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = response(payload={"results": {"bindings": [
        {"item": {"value": "http://www.wikidata.org/entity/Q123"}}
    ]}})
    assert _lookup_qid_by_mmsi(client, "235102528") == "Q123"


def test_ambiguous_mmsi_rejected():
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = response(payload={"results": {"bindings": [
        {"item": {"value": "http://www.wikidata.org/entity/Q1"}},
        {"item": {"value": "http://www.wikidata.org/entity/Q2"}},
    ]}})
    assert _lookup_qid_by_mmsi(client, "235102528") is None


def test_name_must_match_wikidata_label_or_alias():
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = response(payload={"entities": {"Q123": {
        "labels": {"en": {"value": "Höegh Sunrise"}},
        "aliases": {"en": [{"value": "Hoegh Sunrise"}]},
    }}})
    assert _qid_matches_name(client, "Q123", "HOEGH SUNRISE")
    assert not _qid_matches_name(client, "Q123", "PATRIA SEAWAYS")


def test_missing_p18():
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = response(payload={"claims": {}})
    assert _fetch_p18_title(client, "Q123") is None


def test_p18_title_prefixed():
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = response(payload={"claims": {"P18": [
        {"mainsnak": {"datavalue": {"value": "Example ship.jpg"}}}
    ]}})
    assert _fetch_p18_title(client, "Q123") == "File:Example ship.jpg"


def test_commons_image_requires_name_or_imo_in_file_metadata():
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = response(payload={"query": {"pages": {"1": {
        "title": "File:Generic tug.jpg",
        "imageinfo": [{
            "mime": "image/jpeg",
            "url": "https://example.test/ship.jpg",
            "thumburl": "https://example.test/ship_thumb.jpg",
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Generic_tug.jpg",
            "extmetadata": {
                "LicenseShortName": {"value": "CC BY-SA 4.0"},
                "Artist": {"value": "Photographer"},
                "ImageDescription": {"value": "A harbor tug boat"},
            },
        }],
    }}}})
    assert _download_commons_image(
        client, "File:Generic tug.jpg", qid="Q9",
        expected_name="HOEGH SUNRISE", imo="1234567"
    ) is None
    assert client.get.call_count == 1  # image bytes were never downloaded


def test_commons_download_success_when_exact_identity_is_in_description():
    client = MagicMock(spec=httpx.Client)
    meta = response(payload={"query": {"pages": {"1": {
        "title": "File:Vessel at sea.jpg",
        "imageinfo": [{
            "mime": "image/jpeg",
            "url": "https://example.test/ship.jpg",
            "thumburl": "https://example.test/ship_thumb.jpg",
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Ship.jpg",
            "extmetadata": {
                "LicenseShortName": {"value": "CC BY-SA 4.0"},
                "Artist": {"value": "Photographer"},
                "ImageDescription": {"value": "The HOEGH SUNRISE underway"},
            },
        }],
    }}}})
    img = MagicMock()
    img.status_code = 200
    img.content = b"\\xff\\xd8\\xfffakejpeg"
    client.get.side_effect = [meta, img]
    photo = _download_commons_image(
        client, "File:Vessel at sea.jpg", qid="Q9",
        expected_name="HOEGH SUNRISE"
    )
    assert isinstance(photo, VesselPhoto)
    assert photo.verified and photo.identity_verified
    assert photo.license_name == "CC BY-SA 4.0"


def test_http_failure_soft():
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = httpx.ConnectError("down")
    assert resolve_vessel_photo(
        "235102528", expected_name="SHIP", client=client
    ) is None


def test_no_fallback_provider_strings_in_module():
    source = Path("src/enrichment/vessel_photo.py").read_text().lower()
    for banned in ("marinetraffic", "shipspotting", "fleetmon", "vesselfinder"):
        assert banned not in source


def test_end_to_end_mocked_resolve_requires_all_identity_checks():
    client = MagicMock(spec=httpx.Client)
    sparql = response(payload={"results": {"bindings": [
        {"item": {"value": "http://www.wikidata.org/entity/Q42"}}
    ]}})
    name = response(payload={"entities": {"Q42": {
        "labels": {"en": {"value": "Example Ship"}},
        "aliases": {"en": []},
    }}})
    claims = response(payload={"claims": {"P18": [
        {"mainsnak": {"datavalue": {"value": "Ship.jpg"}}}
    ]}})
    commons = response(payload={"query": {"pages": {"1": {
        "title": "File:Example Ship.jpg",
        "imageinfo": [{
            "mime": "image/jpeg",
            "url": "https://example.test/a.jpg",
            "descriptionurl": "https://commons.example/File:Example_Ship.jpg",
            "extmetadata": {
                "LicenseShortName": {"value": "CC0"},
                "Artist": {"value": "A"},
                "ImageDescription": {"value": "Example Ship"},
            },
        }],
    }}}})
    img = MagicMock()
    img.status_code = 200
    img.content = b"abc123"
    client.get.side_effect = [sparql, name, claims, commons, img]
    photo = resolve_vessel_photo(
        "235102528", expected_name="Example Ship", client=client
    )
    assert photo is not None and photo.image_bytes == b"abc123"
    assert photo.identity_verified
