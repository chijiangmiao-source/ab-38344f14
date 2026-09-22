"""API 层测试：健康检查、求解、不可达、非法输入定位。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def T(i, c, s, t):
    return {"id": i, "event_code": c, "source": s, "target": t}


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_limits():
    r = client.get("/api/limits")
    body = r.json()
    assert body["max_states"] == 80
    assert body["max_transitions"] == 300
    assert body["max_observations"] == 200


def test_solve_ok():
    r = client.post(
        "/api/solve",
        json={
            "states": ["A", "B", "C"],
            "transitions": [
                T("p", "PUMP", "A", "B"),
                T("v", "VALVE", "B", "C"),
            ],
            "initial_state": "A",
            "final_state": "C",
            "observations": ["VALVE"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["feasible"] is True
    assert body["inserted_count"] == 1
    assert body["canonical_sequence"] == ["p", "v"]
    assert body["canonical_events"] == [None, 1]
    assert body["boundary_states"] == [["A"], ["C"]]


def test_solve_cycle():
    r = client.post(
        "/api/solve",
        json={
            "states": ["A", "B", "C"],
            "transitions": [
                T("a", "X", "A", "B"),
                T("loop", "EV", "B", "A"),
                T("b", "Y", "A", "C"),
            ],
            "initial_state": "A",
            "final_state": "C",
            "observations": ["EV"],
        },
    )
    body = r.json()
    assert body["feasible"] is True
    assert body["inserted_count"] == 2
    assert body["canonical_sequence"] == ["a", "loop", "b"]


def test_unreachable_is_200_feasible_false():
    r = client.post(
        "/api/solve",
        json={
            "states": ["A", "B"],
            "transitions": [T("back", "E", "B", "A")],
            "initial_state": "A",
            "final_state": "A",
            "observations": ["E"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["feasible"] is False
    assert "reason" in body


def test_validation_error_points_to_field_and_index():
    r = client.post(
        "/api/solve",
        json={
            "states": ["A", "B"],
            "transitions": [
                T("x", "E", "A", "B"),
                T("x", "E", "B", "A"),
            ],
            "initial_state": "A",
            "final_state": "B",
            "observations": ["E"],
        },
    )
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["field"] == "transitions"
    assert err["index"] == 1
    assert "x" in err["message"]


def test_malformed_json_is_400():
    r = client.post(
        "/api/solve",
        content=b"{bad json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400


def test_missing_field_is_400():
    r = client.post("/api/solve", json={"states": ["A", "B"]})
    assert r.status_code == 400
