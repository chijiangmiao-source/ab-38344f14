"""请求 / 响应数据模型与输入规模约束。"""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

# 输入规模约束（题目给定）
MIN_STATES = 2
MAX_STATES = 80
MIN_TRANSITIONS = 1
MAX_TRANSITIONS = 300
MIN_OBSERVATIONS = 1
MAX_OBSERVATIONS = 200
MAX_TOKEN_LEN = 64


class TransitionIn(BaseModel):
    id: str = Field(..., description="迁移唯一标识")
    event_code: str = Field(..., description="事件码")
    source: str = Field(..., description="源状态")
    target: str = Field(..., description="目标状态")


class SolveRequest(BaseModel):
    states: List[str]
    transitions: List[TransitionIn]
    initial_state: str
    final_state: str
    observations: List[str]
