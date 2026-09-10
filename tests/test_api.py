"""Flask API 层测试。"""
import pytest

from backend.app import create_app


@pytest.fixture()
def client():
    app = create_app()
    app.testing = True
    return app.test_client()


def test_map_api(client):
    resp = client.get("/api/map?now=12:00")
    assert resp.status_code == 200
    data = resp.get_json()
    assert {f["id"] for f in data["floors"]} == {"B1", "B2", "B3"}
    assert len(data["nodes"]) >= 20
    assert len(data["edges"]) >= 30
    s5 = next(n for n in data["nodes"] if n["id"] == "s5")
    assert s5["open"] is False
    s1 = next(n for n in data["nodes"] if n["id"] == "s1")
    assert s1["open"] is True


def test_map_api_night_state(client):
    # 深夜 2 点: 普通店铺关闭, 海底捞/全家仍开
    data = client.get("/api/map?now=02:00").get_json()
    status = {n["id"]: n["open"] for n in data["nodes"]
              if n["type"] == "shop"}
    assert status["s1"] is False
    assert status["s10"] is True
    assert status["s15"] is True


def test_route_api_success(client):
    resp = client.post("/api/route", json={
        "start": "sub_a", "end": "s1", "now": "12:00"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["start"] == "sub_a"
    assert data["steps"]
    assert data["total_seconds"] > 0


def test_route_api_closed_destination(client):
    resp = client.post("/api/route", json={
        "start": "sub_a", "end": "s5", "now": "12:00"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "destination_closed"


def test_route_api_after_hours(client):
    resp = client.post("/api/route", json={
        "start": "sub_a", "end": "s1", "now": "06:00"})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "destination_closed"


def test_route_api_missing_params(client):
    resp = client.post("/api/route", json={"start": "sub_a"})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "unknown_node"


def test_route_api_invalid_time(client):
    resp = client.post("/api/route", json={
        "start": "sub_a", "end": "s1", "now": "abc"})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "invalid_time"


def test_index_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
