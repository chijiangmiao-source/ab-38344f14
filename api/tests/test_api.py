"""HTTP-level tests for the FastAPI service (real ASGI transport via TestClient)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def payload_override(**kw):
    base = {
        "states": ["A", "B", "C"],
        "transitions": [
            {"id": "e1", "source": "A", "target": "B", "code": "x"},
            {"id": "e2", "source": "B", "target": "A", "code": "y"},
            {"id": "e3", "source": "B", "target": "C", "code": "z"},
        ],
        "start": "A",
        "end": "C",
        "observations": ["x", "y", "x", "z"],
    }
    base.update(kw)
    return base


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "interlock-solver"


def test_solve_cycle_completion():
    r = client.post("/api/solve", json=payload_override())
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [s["edge_id"] for s in body["canonical_sequence"]]
    # x=e1, y=e2, x=e1 consumes -> B ; insert nothing; z=e3 to C
    assert ids == ["e1", "e2", "e1", "e3"]
    assert body["inserted_count"] == 0
    roles = [s["role"] for s in body["canonical_sequence"]]
    assert roles == ["consumed"] * 4
    assert [s["observation_index"] for s in body["canonical_sequence"]] == [1, 2, 3, 4]
    assert len(body["boundary_states"]) == 5


def test_solve_with_insertions_and_boundary_set():
    payload = payload_override(
        states=["A", "B", "C", "D"],
        transitions=[
            {"id": "p", "source": "A", "target": "B", "code": "x"},
            {"id": "q", "source": "A", "target": "C", "code": "x"},
            {"id": "r", "source": "B", "target": "D", "code": "u"},
            {"id": "s", "source": "C", "target": "D", "code": "v"},
        ],
        end="D",
        observations=["x"],
    )
    r = client.post("/api/solve", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["inserted_count"] == 1
    assert [s["edge_id"] for s in body["canonical_sequence"]] == ["p", "r"]
    boundary1 = body["boundary_states"][1]
    assert boundary1["after_observation"] == 1
    assert sorted(boundary1["states"]) == ["B", "C"]


def test_unreachable_returns_409_with_location():
    payload = payload_override(observations=["x", "nope"])
    r = client.post("/api/solve", json=payload)
    assert r.status_code == 409
    body = r.json()["error"]
    assert body["code"] == "unreachable"
    assert body["observation_index"] == 2
    assert body["event_code"] == "nope"


def test_invalid_returns_422_and_keeps_input_responsibility_on_client():
    payload = payload_override(states=["A"])  # fewer than 2 states
    r = client.post("/api/solve", json=payload)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"

    payload = payload_override(
        transitions=[
            {"id": "e1", "source": "A", "target": "B", "code": "x"},
            {"id": "e1", "source": "B", "target": "A", "code": "y"},
        ]
    )
    r = client.post("/api/solve", json=payload)
    assert r.status_code == 422
    assert "duplicate transition id" in r.json()["error"]["message"]


def test_malformed_json_shape_422():
    r = client.post("/api/solve", json={"states": ["A", "B"]})
    assert r.status_code == 422
