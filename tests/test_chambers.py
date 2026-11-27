import json
from pathlib import Path

import pytest
import requests

from tools.counsel import chambers


FIXTURE_DATA = {
    "chambers": [
        {
            "name": "Near Chambers",
            "email": "clerks@near.example",
            "branches": [{"name": "London", "lat": 51.50, "lon": -0.10}],
        },
        {
            "name": "Far Chambers",
            "email": "clerks@far.example",
            "branches": [{"name": "Leeds", "lat": 53.80, "lon": -1.55}],
        },
        {
            "name": "No Coordinates Chambers",
            "email": "clerks@nogeo.example",
            "branches": [{"name": "Unknown", "lat": None, "lon": None}],
        },
    ],
    "courts": [],
}


@pytest.fixture
def fixture_data_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_file = tmp_path / "chambers-data.json"
    data_file.write_text(json.dumps(FIXTURE_DATA), encoding="utf-8")
    monkeypatch.setattr(chambers, "DATA_FILE", data_file)
    return data_file


def test_find_nearest_chambers_sorts_by_distance_and_skips_ungeocoded(fixture_data_file):
    results = chambers.find_nearest_chambers(51.50, -0.10, count=5)

    names = [row["chambers"]["name"] for row in results]
    assert names == ["Near Chambers", "Far Chambers"]
    assert "No Coordinates Chambers" not in names
    assert results[0]["distance_miles"] < results[1]["distance_miles"]


def test_find_nearest_chambers_respects_count_limit(fixture_data_file):
    results = chambers.find_nearest_chambers(51.50, -0.10, count=1)

    assert len(results) == 1
    assert results[0]["chambers"]["name"] == "Near Chambers"


def test_geocode_postcode_success(monkeypatch: pytest.MonkeyPatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"result": {"latitude": 51.50101, "longitude": -0.141563}}

    monkeypatch.setattr(chambers.requests, "get", lambda *a, **k: FakeResponse())

    result = chambers.geocode_postcode("ZZ99 1ZZ")

    assert result["ok"] is True
    assert result["lat"] == pytest.approx(51.50101)
    assert result["lon"] == pytest.approx(-0.141563)


def test_geocode_postcode_invalid_postcode_returns_message_not_crash(monkeypatch: pytest.MonkeyPatch):
    class FakeResponse:
        status_code = 404

    monkeypatch.setattr(chambers.requests, "get", lambda *a, **k: FakeResponse())

    result = chambers.geocode_postcode("ZZ99 9ZZ")

    assert result["ok"] is False
    assert "not a recognised" in result["message"]


def test_geocode_postcode_network_failure_degrades_to_message_not_exception(monkeypatch: pytest.MonkeyPatch):
    def raise_connection_error(*args, **kwargs):
        raise requests.ConnectionError("simulated network failure")

    monkeypatch.setattr(chambers.requests, "get", raise_connection_error)

    result = chambers.geocode_postcode("ZZ99 1ZZ")

    assert result["ok"] is False
    assert "unavailable" in result["message"]


def test_geocode_postcode_empty_input_does_not_call_network(monkeypatch: pytest.MonkeyPatch):
    called = []
    monkeypatch.setattr(chambers.requests, "get", lambda *a, **k: called.append(1))

    result = chambers.geocode_postcode("   ")

    assert result["ok"] is False
    assert not called


def test_find_nearest_chambers_by_postcode_propagates_geocode_failure(monkeypatch: pytest.MonkeyPatch, fixture_data_file):
    monkeypatch.setattr(chambers, "geocode_postcode", lambda postcode: {"ok": False, "message": "bad postcode"})

    result = chambers.find_nearest_chambers_by_postcode("nonsense")

    assert result == {"ok": False, "message": "bad postcode"}


def test_find_nearest_chambers_by_postcode_success_path(monkeypatch: pytest.MonkeyPatch, fixture_data_file):
    monkeypatch.setattr(chambers, "geocode_postcode", lambda postcode: {"ok": True, "lat": 51.50, "lon": -0.10})

    result = chambers.find_nearest_chambers_by_postcode("ZZ99 1ZZ", count=1)

    assert result["ok"] is True
    assert result["postcode"] == "ZZ99 1ZZ"
    assert len(result["nearest_chambers"]) == 1
    assert result["nearest_chambers"][0]["chambers"]["name"] == "Near Chambers"



def test_find_chambers_by_name_matches_on_name(fixture_data_file):
    results = chambers.find_chambers_by_name("Near")

    assert len(results) == 1
    assert results[0] == {
        "name": "Near Chambers",
        "email": "clerks@near.example",
        "phone": "",
        "website": "",
        "aliases": [],
    }


def test_find_chambers_by_name_matches_on_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = {
        "chambers": [{"name": "Example Chambers|Family Law", "email": "clerks@example.test", "aliases": ["EC"]}],
        "courts": [],
    }
    data_file = tmp_path / "chambers-data.json"
    data_file.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(chambers, "DATA_FILE", data_file)

    results = chambers.find_chambers_by_name("ec")

    assert [r["name"] for r in results] == ["Example Chambers|Family Law"]


def test_find_chambers_by_name_no_match_returns_empty_list(fixture_data_file):
    assert chambers.find_chambers_by_name("Not A Real Chambers") == []


def test_find_chambers_by_name_empty_query_returns_empty_list_without_loading(monkeypatch: pytest.MonkeyPatch):
    def fail_load():
        raise AssertionError("must not load the data file for an empty query")

    monkeypatch.setattr(chambers, "_load", fail_load)

    assert chambers.find_chambers_by_name("   ") == []
