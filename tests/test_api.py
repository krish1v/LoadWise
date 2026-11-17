"""API + SQLite store: demo import, re-upload no-op, drill-down, override, exports, forecast."""

import json
import os

os.environ["LOADWISE_NO_DEFAULT_APP"] = "1"   # don't touch data/loadwise.db during tests

import pytest
from fastapi.testclient import TestClient

from conftest import REAL_WORKBOOK, build_workbook, session

import datetime as dt


@pytest.fixture
def client(tmp_path):
    from api.main import create_app
    return TestClient(create_app(str(tmp_path / "test.db"), autoload_demo=False))


def _upload(client, data, year=2025, name="team.xlsx"):
    return client.post("/api/imports", files={"file": (name, data)},
                       data={"season_start_year": str(year)} if year else {})


def test_empty_store_returns_actionable_404(client):
    r = client.get("/api/summary")
    assert r.status_code == 404 and "Upload" in r.json()["detail"]


def test_upload_requires_season_year(client):
    r = _upload(client, build_workbook([session()]), year=None)
    assert r.status_code == 422 and r.json()["code"] == "season_year_required"
    assert client.get("/api/status").json()["imports"] == []      # nothing stored


def test_bad_file_rejected_gracefully(client):
    r = _upload(client, b"not an excel file")
    assert r.status_code == 422 and "xlsx" in r.json()["detail"]


def test_reupload_is_noop_and_history_accumulates(client):
    a = build_workbook([session(date="11/09", day=1)])
    b = build_workbook([session(date="12/09", day=2)])
    assert _upload(client, a).json()["status"] == "imported"
    first = client.get("/api/summary").json()["summary"]
    assert _upload(client, a, name="again.xlsx").json()["status"] == "already_imported"
    assert client.get("/api/summary").json()["summary"] == first
    _upload(client, b)
    s = client.get("/api/summary").json()
    assert s["summary"]["daily_records"] == 2 and s["summary"]["imports"] == 2
    assert len(s["squad"]["athletes"]) == 1


def test_season_year_mismatch_rejected(client):
    _upload(client, build_workbook([session()]))
    r = _upload(client, build_workbook([session(date="12/09")]), year=2024)
    assert r.status_code == 422 and "2025" in r.json()["detail"]


def test_drilldown_override_and_exports(client):
    rows = [session(trimp=100, start=dt.time(9), end=dt.time(10, 30)),
            session(trimp=90, start=dt.time(9, 10), end=dt.time(10, 30))]
    _upload(client, build_workbook(rows))
    daily = client.get("/api/daily").json()
    assert daily[0]["trimp"]["value"] == 190
    aid, date = daily[0]["athlete_id"], daily[0]["date"]
    detail = client.get(f"/api/daily/{aid}/{date}").json()
    assert [s["provenance"]["excel_row"] for s in detail["sessions"]] == [2, 3]
    assert detail["sessions"][0]["raw"]["cells"]["TRIMP (Index)"] == 100

    queue = client.get("/api/review").json()
    assert {q["kind"] for q in queue} == {"possible_duplicate"}
    rid = detail["sessions"][1]["record_id"]
    assert client.post("/api/overrides", json={"record_id": rid, "action": "exclude",
                                               "reason": ""}).status_code == 422   # reason required
    r = client.post("/api/overrides", json={"record_id": rid, "action": "exclude",
                                            "reason": "recorded twice"}).json()
    assert r["daily"]["trimp"]["value"] == 100
    assert client.get("/api/daily").json()[0]["trimp"]["value"] == 100

    out = json.loads(client.get("/api/export.json").text)
    assert out["configuration"]["overrides"][rid]["reason"] == "recorded twice"
    csv = client.get("/api/export.csv").text
    assert "trimp_completeness" in csv.splitlines()[0]

    cal = client.get("/api/calendar?metric=trimp").json()
    assert cal["athletes"][0]["cells"][0]["value"] == 100
    assert client.get("/api/flags?rule=MANUAL_OVERRIDE").json()


def test_autoload_demo_on_empty_store(tmp_path):
    if not os.path.exists(REAL_WORKBOOK):
        pytest.skip("real workbook not present")
    from api.main import create_app
    c = TestClient(create_app(str(tmp_path / "auto.db"), autoload_demo=True))
    st = c.get("/api/status").json()
    assert len(st["imports"]) == 1 and st["season_start_year"] == 2025


def test_reset_clears_store(client):
    _upload(client, build_workbook([session()]))
    client.delete("/api/store")
    assert client.get("/api/status").json()["imports"] == []


@pytest.mark.skipif(not os.path.exists(REAL_WORKBOOK), reason="real workbook not present")
def test_demo_and_forecast(client):
    r = client.post("/api/imports/demo").json()
    assert r["summary"]["session_records"] == 1260
    squad = client.get("/api/summary").json()["squad"]
    assert len(squad["athletes"]) == 15 and squad["reference_date"] == "2026-01-09"
    pytest.importorskip("sklearn")
    aid = squad["athletes"][0]["athlete_id"]
    fc = client.get(f"/api/forecast/{aid}?minutes=90,60").json()
    assert len(fc["days"]) == 2 and fc["days"][0]["date"] > "2026-01-01"
    assert fc["days"][0]["predicted_trimp"] > 0 and fc["observed_history"]
    base = client.get(f"/api/forecast/{aid}/baseline.json?minutes=90").json()
    assert base["kind"] == "expected_baseline_workload"
