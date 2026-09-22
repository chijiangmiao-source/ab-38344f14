"""Real HTTP smoke tests executed inside the verify one-shot container.

Replays four scenarios against the live services:
  A. a completion that goes around a cycle and inserts a missing edge;
  B. equal-optimum completions sharing one event code -> boundary state set;
  C. an unreachable request (409) with precise observation localization;
  D. an invalid request (422).

The same scenarios are sent BOTH to the API container directly and through the
web container's nginx reverse proxy, proving end-to-end HTTP integration.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API_BASE = os.environ.get("API_BASE", "http://api:8000").rstrip("/")
WEB_BASE = os.environ.get("WEB_BASE", "http://web").rstrip("/")


def call(base: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        base + "/api/solve",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  PASS " if cond else "  FAIL ") + msg)
    if not cond:
        FAILURES.append(msg)


def scenario_cycle() -> dict:
    return {
        "states": ["A", "B"],
        "transitions": [
            {"id": "e_x", "source": "A", "target": "B", "code": "x"},
            {"id": "e_y", "source": "B", "target": "A", "code": "y"},
            {"id": "e_back", "source": "B", "target": "A", "code": "z"},
        ],
        "start": "A",
        "end": "A",
        "observations": ["x", "y", "x"],
    }


def scenario_tie() -> dict:
    return {
        "states": ["A", "B", "C", "D"],
        "transitions": [
            {"id": "p", "source": "A", "target": "B", "code": "x"},
            {"id": "q", "source": "A", "target": "C", "code": "x"},
            {"id": "r", "source": "B", "target": "D", "code": "u"},
            {"id": "s", "source": "C", "target": "D", "code": "v"},
        ],
        "start": "A",
        "end": "D",
        "observations": ["x"],
    }


def scenario_unreachable() -> dict:
    p = scenario_cycle()
    p["observations"] = ["x", "nope"]
    return p


def scenario_invalid() -> dict:
    p = scenario_cycle()
    p["states"] = ["A"]  # fewer than 2
    return p


def run_against(base: str, label: str) -> None:
    print(f"\n-- {label} ({base}) --")

    status, body = call(base, scenario_cycle())
    check(status == 200, f"[cycle] HTTP 200 (got {status})")
    ids = [s["edge_id"] for s in body.get("canonical_sequence", [])]
    check(ids == ["e_x", "e_y", "e_x", "e_back"], f"[cycle] canonical ids {ids}")
    check(body.get("inserted_count") == 1, f"[cycle] inserted=1 (got {body.get('inserted_count')})")
    roles = [s["role"] for s in body.get("canonical_sequence", [])]
    check(roles == ["consumed", "consumed", "consumed", "inserted"],
          f"[cycle] roles {roles}")

    status, body = call(base, scenario_tie())
    check(status == 200, f"[tie] HTTP 200 (got {status})")
    ids = [s["edge_id"] for s in body.get("canonical_sequence", [])]
    check(ids == ["p", "r"], f"[tie] lex-min ids {ids}")
    boundary1 = body.get("boundary_states", [{}, {}])[1].get("states", [])
    check(sorted(boundary1) == ["B", "C"], f"[tie] boundary-1 possible set {boundary1}")

    status, body = call(base, scenario_unreachable())
    check(status == 409, f"[unreachable] HTTP 409 (got {status})")
    err = body.get("error", {})
    check(err.get("code") == "unreachable", f"[unreachable] code {err.get('code')}")
    check(err.get("observation_index") == 2,
          f"[unreachable] localized at observation 2 (got {err.get('observation_index')})")
    check(err.get("event_code") == "nope", f"[unreachable] event code {err.get('event_code')}")

    status, body = call(base, scenario_invalid())
    check(status == 422, f"[invalid] HTTP 422 (got {status})")
    check(body.get("error", {}).get("code") == "invalid_request",
          f"[invalid] error code {body.get('error', {}).get('code')}")


def main() -> int:
    run_against(API_BASE, "API container direct")
    run_against(WEB_BASE, "Through web nginx proxy")
    if FAILURES:
        print(f"\n{len(FAILURES)} smoke check(s) FAILED")
        return 1
    print("\nAll smoke checks passed on both routes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
