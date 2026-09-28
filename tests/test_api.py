"""FastAPI 接口测试。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_plan_ok():
    resp = client.post("/api/plan", json={"ground": [100, 107, 114, 119, 124, 130]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["feasible"] is True
    assert data["plan"][0] == 100
    assert data["plan"][-1] == 130
    assert data["total_adjustment"] >= 0
    assert "segments" in data and len(data["segments"]) == 5


def test_invalid_count():
    resp = client.post("/api/plan", json={"ground": [1, 2]})
    assert resp.status_code == 422
    data = resp.json()
    assert data["feasible"] is False
    assert "3" in data["reason"]


def test_invalid_range():
    resp = client.post("/api/plan", json={"ground": [0, 999, 0]})
    assert resp.status_code == 422
    assert "超出范围" in resp.json()["reason"]


def test_reject_float_and_string():
    for bad in ([0, 1.5, 0], [0, "8", 0]):
        resp = client.post("/api/plan", json={"ground": bad})
        assert resp.status_code == 422
        assert "整数" in resp.json()["reason"]


def test_missing_field():
    resp = client.post("/api/plan", json={"points": [1, 2, 3]})
    assert resp.status_code == 400
    assert "ground" in resp.json()["reason"]


def test_body_not_json():
    resp = client.post("/api/plan", content="not-json", headers={"Content-Type": "text/plain"})
    assert resp.status_code == 400


def test_infeasible_is_200():
    # 合法输入但无解：200 + feasible=false
    resp = client.post(
        "/api/plan", json={"ground": [0, 8, 16, 24, 32, 40]}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["feasible"] is False
    assert "无解" in data["reason"]


def test_index_page():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "步道坡线规划台".encode() in resp.content
