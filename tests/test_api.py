"""FastAPI 接口测试。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_plan_ok():
    resp = client.post(
        "/api/plan",
        json={"ground": [100, 107, 114, 119, 124, 130], "width": 2.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["feasible"] is True
    assert data["plan"][0] == 100
    assert data["plan"][-1] == 130
    assert data["total_adjustment"] >= 0
    assert "segments" in data and len(data["segments"]) == 5
    ew = data["earthwork"]
    assert ew is not None
    assert ew["width"] == 2.0
    assert ew["unit"] == "m3"
    assert ew["total_cut"] >= 0 and ew["total_fill"] >= 0
    assert len(ew["segments"]) == 5
    assert len(ew["cumulative_net"]) == 5
    assert len(ew["flows"]) == 5
    assert ew["flows"][0]["distance"] == 0.5
    assert all(f["distance"] == 1.0 for f in ew["flows"][1:])


def test_invalid_count():
    resp = client.post("/api/plan", json={"ground": [1, 2], "width": 2.0})
    assert resp.status_code == 422
    data = resp.json()
    assert data["feasible"] is False
    assert "3" in data["reason"]


def test_invalid_range():
    resp = client.post("/api/plan", json={"ground": [0, 999, 0], "width": 2.0})
    assert resp.status_code == 422
    assert "超出范围" in resp.json()["reason"]


def test_reject_float_and_string():
    for bad in ([0, 1.5, 0], [0, "8", 0]):
        resp = client.post("/api/plan", json={"ground": bad, "width": 2.0})
        assert resp.status_code == 422
        assert "整数" in resp.json()["reason"]


def test_missing_field():
    resp = client.post("/api/plan", json={"points": [1, 2, 3], "width": 2.0})
    assert resp.status_code == 400
    assert "ground" in resp.json()["reason"]


def test_missing_width():
    resp = client.post("/api/plan", json={"ground": [100, 107, 114]})
    assert resp.status_code == 400
    assert "width" in resp.json()["reason"]


def test_width_null():
    resp = client.post(
        "/api/plan", json={"ground": [100, 107, 114], "width": None}
    )
    assert resp.status_code == 400
    assert "width" in resp.json()["reason"]


def test_width_out_of_range():
    for bad in (0.4, 10.1, 0, -1):
        resp = client.post(
            "/api/plan",
            json={"ground": [100, 107, 114, 119, 124, 130], "width": bad},
        )
        assert resp.status_code == 422, bad
        assert "净宽" in resp.json()["reason"]


def test_width_too_many_decimals():
    resp = client.post(
        "/api/plan",
        json={"ground": [100, 107, 114, 119, 124, 130], "width": 2.345},
    )
    assert resp.status_code == 422
    assert "小数" in resp.json()["reason"]


def test_width_wrong_type():
    for bad in ("2.0", True, [2.0]):
        resp = client.post(
            "/api/plan",
            json={"ground": [100, 107, 114, 119, 124, 130], "width": bad},
        )
        assert resp.status_code == 422, bad


def test_width_boundaries_ok():
    for w in (0.5, 10.0, 1.25, 3.0, 0.51):
        resp = client.post(
            "/api/plan",
            json={"ground": [100, 107, 114, 119, 124, 130], "width": w},
        )
        assert resp.status_code == 200, w
        assert resp.json()["feasible"] is True


def test_body_not_json():
    resp = client.post("/api/plan", content="not-json", headers={"Content-Type": "text/plain"})
    assert resp.status_code == 400


def test_infeasible_is_200():
    # 合法输入但无解：200 + feasible=false，且不附 earthwork
    resp = client.post(
        "/api/plan", json={"ground": [0, 8, 16, 24, 32, 40], "width": 2.0}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["feasible"] is False
    assert "无解" in data["reason"]
    assert "earthwork" not in data


def test_invalid_width_with_infeasible_ground():
    # 无解场地 + 非法净宽：净宽非法应明确报错（422），不返回无解
    resp = client.post(
        "/api/plan", json={"ground": [0, 8, 16, 24, 32, 40], "width": 99}
    )
    assert resp.status_code == 422
    assert "净宽" in resp.json()["reason"]


def test_index_page():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "步道坡线规划台".encode() in resp.content
    assert "土方调配".encode() in resp.content
