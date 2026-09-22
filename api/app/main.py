"""FastAPI application exposing the minimum-completion solver."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .solver import (
    MAX_OBSERVATIONS,
    MAX_STATES,
    MAX_TRANSITIONS,
    UnreachableError,
    ValidationError,
    solve,
    validate_and_build,
)

SERVICE_VERSION = "1.0.0"


class TransitionIn(BaseModel):
    id: str = Field(..., description="unique transition id")
    source: str
    target: str
    code: str = Field(..., description="event code consumed by this transition")


class SolveRequest(BaseModel):
    states: list[str]
    transitions: list[TransitionIn]
    start: str
    end: str
    observations: list[str]


class SolveResponse(BaseModel):
    inserted_count: int
    total_edge_count: int
    canonical_sequence: list[dict[str, Any]]
    canonical_path_states: list[str]
    consumed_edge_ids: list[str]
    boundary_states: list[dict[str, Any]]
    limits: dict[str, int]


def _error(code: str, message: str, status: int, **extra: Any) -> JSONResponse:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    payload["error"].update(extra)
    return JSONResponse(status_code=status, content=payload)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Vacuum Coating Interlock Log Completion API",
        version=SERVICE_VERSION,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "interlock-solver", "version": SERVICE_VERSION}

    @app.post("/api/solve", response_model=SolveResponse)
    def solve_endpoint(req: SolveRequest) -> Any:
        try:
            states, edges, observations = validate_and_build(
                req.states,
                [t.model_dump() for t in req.transitions],
                req.start,
                req.end,
                req.observations,
            )
            result = solve(states, edges, observations, req.start, req.end)
        except ValidationError as exc:
            return _error("invalid_request", str(exc), 422)
        except UnreachableError as exc:
            return _error(
                "unreachable",
                str(exc),
                409,
                observation_index=exc.observation_index,
                event_code=exc.event_code,
            )
        result["limits"] = {
            "max_states": MAX_STATES,
            "max_transitions": MAX_TRANSITIONS,
            "max_observations": MAX_OBSERVATIONS,
        }
        return result

    @app.exception_handler(RequestValidationError)
    async def request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        detail = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in detail.get("loc", []) if p != "body")
        msg = f"{loc + ': ' if loc else ''}{detail.get('msg', 'request validation failed')}"
        return _error("invalid_request", msg, 422)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        return _error("internal_error", f"unexpected error: {exc}", 500)

    return app


app = create_app()


def main() -> None:  # pragma: no cover - runtime entry point
    import uvicorn

    port = int(os.environ.get("API_PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)


if __name__ == "__main__":  # pragma: no cover
    main()
