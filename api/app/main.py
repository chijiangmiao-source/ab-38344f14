"""FastAPI 入口：漏记迁移补全服务。"""
from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .solver import (
    Transition,
    UnreachableError,
    ValidationError as SolverValidationError,
    solve,
    validate_input,
)

app = FastAPI(title="真空镀膜联锁日志漏记迁移补全", version="1.0.0")

# 同源部署（nginx 反代 /api）默认无需 CORS；允许通过环境变量放开跨域。
_allow_origin = os.getenv("CORS_ALLOW_ORIGIN", "").strip()
if _allow_origin:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in _allow_origin.split(",") if o.strip()],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )


@app.get("/healthz")
def healthz() -> Dict[str, str]:
    return {"status": "ok", "service": "api"}


@app.get("/api/limits")
def limits() -> Dict[str, int]:
    return {
        "min_states": models.MIN_STATES,
        "max_states": models.MAX_STATES,
        "min_transitions": models.MIN_TRANSITIONS,
        "max_transitions": models.MAX_TRANSITIONS,
        "min_observations": models.MIN_OBSERVATIONS,
        "max_observations": models.MAX_OBSERVATIONS,
        "max_token_len": models.MAX_TOKEN_LEN,
    }


def _error(message: str, status: int, field: str | None = None, index: int | None = None):
    detail: Dict[str, Any] = {"message": message}
    if field is not None:
        detail["field"] = field
    if index is not None:
        detail["index"] = index
    return JSONResponse(status_code=status, content={"ok": False, "error": detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errs = exc.errors()
    first = errs[0] if errs else {}
    loc = [str(x) for x in first.get("loc", []) if x != "body"]
    message = "请求体格式不合法：" + (
        ".".join(loc) + " " + first.get("msg", "") if loc else first.get("msg", "格式错误")
    )
    field = None
    index = None
    if loc:
        if loc[0] in {"states", "transitions", "observations"}:
            field = loc[0]
            for part in loc[1:]:
                if part.isdigit():
                    index = int(part)
                    break
    return _error(message, 400, field, index)


@app.post("/api/solve")
def api_solve(req: models.SolveRequest):
    try:
        states_ordered, transitions_ordered = validate_input(
            req.states,
            [
                Transition(
                    id=t.id,
                    event_code=t.event_code,
                    source=t.source,
                    target=t.target,
                )
                for t in req.transitions
            ],
            req.initial_state,
            req.final_state,
            req.observations,
        )
    except SolverValidationError as exc:
        return _error(exc.message, 400, exc.field, exc.index)

    try:
        result = solve(
            states_ordered,
            transitions_ordered,
            req.initial_state,
            req.final_state,
            req.observations,
        )
    except UnreachableError as exc:
        return {"ok": True, "feasible": False, "reason": str(exc)}

    return {
        "ok": True,
        "feasible": True,
        "inserted_count": result.inserted_count,
        "canonical_sequence": result.canonical_sequence,
        "canonical_events": result.canonical_events,
        "boundary_states": result.boundary_states,
        "states": states_ordered,
        "transitions": [
            {"id": t.id, "event_code": t.event_code, "source": t.source, "target": t.target}
            for t in transitions_ordered
        ],
    }
