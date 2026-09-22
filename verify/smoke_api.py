#!/usr/bin/env python3
"""对运行中的 API 做真实 HTTP 冒烟：重放含环补全、同优边界集合、不可达与非法请求。

仅使用标准库；任意断言失败以非零退出码结束。
用法: python smoke_api.py [base_url]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Optional, Tuple

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

failures: list[str] = []
checks = 0


def check(name: str, cond: bool, detail: Any = "") -> None:
    global checks
    checks += 1
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        failures.append(name)


def call(method: str, path: str, body: Any = None, raw: Optional[bytes] = None) -> Tuple[int, Any]:
    if raw is not None:
        data = raw
    elif body is not None:
        data = json.dumps(body).encode()
    else:
        data = None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = resp.read()
            return resp.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload)
        except Exception:
            return exc.code, payload


def T(i, c, s, t):
    return {"id": i, "event_code": c, "source": s, "target": t}


# ------------------------------------------------------------ 健康检查与元数据
print("[health] /healthz 与 /api/limits")
status, data = call("GET", "/healthz")
check("healthz 200", status == 200, data)
check("healthz body", isinstance(data, dict) and data.get("status") == "ok", data)

status, data = call("GET", "/api/limits")
check("limits 200", status == 200, data)
check("limits max_states=80", data and data.get("max_states") == 80, data)
check("limits max_transitions=300", data and data.get("max_transitions") == 300, data)
check("limits max_observations=200", data and data.get("max_observations") == 200, data)

# ------------------------------------------------------------ 场景 1：含环补全
print("[scenario] 含环补全：观测边方向要求先绕行")
payload = {
    "states": ["A", "B", "C"],
    "transitions": [
        T("a", "X", "A", "B"),
        T("loop", "EV", "B", "A"),  # B -> A 成环
        T("b", "Y", "A", "C"),
    ],
    "initial_state": "A",
    "final_state": "C",
    "observations": ["EV"],
}
status, data = call("POST", "/api/solve", payload)
check("cycle status 200", status == 200, data)
check("cycle feasible", data and data.get("feasible") is True, data)
check("cycle inserted_count == 2", data and data.get("inserted_count") == 2, data)
check(
    "cycle canonical [a, loop, b]",
    data and data.get("canonical_sequence") == ["a", "loop", "b"],
    data and data.get("canonical_sequence"),
)
check(
    "cycle consume markers [null,1,null]",
    data and data.get("canonical_events") == [None, 1, None],
    data and data.get("canonical_events"),
)

# 自环被同一条观测边消费多次
payload2 = {
    "states": ["A", "B"],
    "transitions": [
        T("tick", "CLK", "A", "A"),
        T("done", "END", "A", "B"),
    ],
    "initial_state": "A",
    "final_state": "B",
    "observations": ["CLK", "CLK", "END"],
}
status, data = call("POST", "/api/solve", payload2)
check("selfloop feasible", data and data.get("feasible") is True, data)
check("selfloop zero insert", data and data.get("inserted_count") == 0, data)
check(
    "selfloop sequence",
    data and data.get("canonical_sequence") == ["tick", "tick", "done"],
    data and data.get("canonical_sequence"),
)

# -------------------------------------------------- 场景 2：同优边界可能状态集合
print("[scenario] 同码多边分叉：边界集合覆盖全部最优补全")
payload3 = {
    "states": ["A", "B", "C", "Z"],
    "transitions": [
        T("e1", "EV", "A", "B"),
        T("e2", "EV", "A", "C"),
        T("g1", "G", "B", "Z"),
        T("g2", "G", "C", "Z"),
    ],
    "initial_state": "A",
    "final_state": "Z",
    "observations": ["EV", "G"],
}
status, data = call("POST", "/api/solve", payload3)
check("branch feasible", data and data.get("feasible") is True, data)
check("branch zero insert", data and data.get("inserted_count") == 0, data)
check(
    "boundary#1 == {B,C}",
    data and data.get("boundary_states", [None, None])[1] == ["B", "C"],
    data and data.get("boundary_states"),
)
check(
    "canonical picks e1 (lexicographic)",
    data and data.get("canonical_sequence") == ["e1", "g1"],
    data and data.get("canonical_sequence"),
)

# 同边消费/插入二重性打平：首标识相同，由后继定序
payload4 = {
    "states": ["A", "B", "D", "Y", "F"],
    "transitions": [
        T("t", "E", "A", "B"),
        T("d", "Z", "B", "D"),
        T("r", "X", "D", "F"),
        T("l", "E", "B", "Y"),
        T("x", "X", "Y", "F"),
    ],
    "initial_state": "A",
    "final_state": "F",
    "observations": ["E", "X"],
}
status, data = call("POST", "/api/solve", payload4)
check("dual-use feasible", data and data.get("feasible") is True, data)
check("dual-use K == 1", data and data.get("inserted_count") == 1, data)
check(
    "dual-use canonical [t,d,r] (suffix decides)",
    data and data.get("canonical_sequence") == ["t", "d", "r"],
    data and data.get("canonical_sequence"),
)
check(
    "dual-use boundary#1 == {B,Y}",
    data and data.get("boundary_states", [None, None])[1] == ["B", "Y"],
    data and data.get("boundary_states"),
)

# ------------------------------------------------------------ 场景 3：不可达
print("[scenario] 不可达请求")
payload5 = {
    "states": ["A", "B"],
    "transitions": [T("back", "E", "B", "A"), T("x", "X", "A", "A")],
    "initial_state": "A",
    "final_state": "A",
    "observations": ["E"],
}
status, data = call("POST", "/api/solve", payload5)
check("unreachable http 200", status == 200, data)
check("unreachable feasible=false", data and data.get("feasible") is False, data)
check("unreachable reason present", bool(data and data.get("reason")), data)

# 观测码无任何同码迁移
payload6 = {
    "states": ["A", "B"],
    "transitions": [T("a", "E", "A", "B")],
    "initial_state": "A",
    "final_state": "B",
    "observations": ["NOPE"],
}
status, data = call("POST", "/api/solve", payload6)
check("unknown code feasible=false", data and data.get("feasible") is False, data)

# ------------------------------------------------------------ 场景 4：非法输入（内容不丢，由客户端保留；此处校验错误结构）
print("[scenario] 非法输入精确定位")
bad_dup_state = {
    "states": ["A", "A"],
    "transitions": [T("a", "E", "A", "A")],
    "initial_state": "A",
    "final_state": "A",
    "observations": ["E"],
}
status, data = call("POST", "/api/solve", bad_dup_state)
check("dup state 400", status == 400, data)
check("dup state field", data and data.get("error", {}).get("field") == "states", data)

bad_dup_id = {
    "states": ["A", "B"],
    "transitions": [T("x", "E", "A", "B"), T("x", "E", "B", "A")],
    "initial_state": "A",
    "final_state": "B",
    "observations": ["E"],
}
status, data = call("POST", "/api/solve", bad_dup_id)
check("dup id 400", status == 400, data)
err = (data or {}).get("error") or {}
check("dup id field+index", err.get("field") == "transitions" and err.get("index") == 1, err)

bad_dangling = {
    "states": ["A", "B"],
    "transitions": [T("a", "E", "A", "X")],
    "initial_state": "A",
    "final_state": "B",
    "observations": ["E"],
}
status, data = call("POST", "/api/solve", bad_dangling)
check("dangling endpoint 400", status == 400, data)
err = (data or {}).get("error") or {}
check("dangling field+index", err.get("field") == "transitions" and err.get("index") == 0, err)

# 缺字段 / 非法 JSON：返回 4xx 而不是 5xx
status, data = call("POST", "/api/solve", {"states": ["A", "B"]})
check("missing fields 400", status == 400, (status, data))

status, data = call("POST", "/api/solve", raw=b"{not valid json")
check("malformed json 400", status == 400, (status, data))

# ------------------------------------------------------------ 规模上限压力
print("[scale] 80 状态 / 300 迁移 / 200 观测")
rng_state = 1234567


def rnd():
    # 简单确定性 LCG
    global rng_state
    rng_state = (1103515245 * rng_state + 12345) & 0x7FFFFFFF
    return rng_state


big_states = [f"S{i:02d}" for i in range(80)]
codes = ["EV", "VAC", "PUMP"]
big_trans = []
pairs = set()
for k in range(300):
    while True:
        u, v = big_states[rnd() % 80], big_states[rnd() % 80]
        if (u, v) not in pairs:
            pairs.add((u, v))
            break
    big_trans.append(T(f"T{k:03d}", codes[rnd() % 3], u, v))
big_obs = [codes[rnd() % 3] for _ in range(200)]
big_payload = {
    "states": big_states,
    "transitions": big_trans,
    "initial_state": big_states[0],
    "final_state": big_states[-1],
    "observations": big_obs,
}
t0 = time.time()
status, data = call("POST", "/api/solve", big_payload)
elapsed = time.time() - t0
check("max-scale http 200", status == 200, data)
check("max-scale response sane", data and ("inserted_count" in data or data.get("feasible") is False), data)
check(f"max-scale fast (<5s, {elapsed:.2f}s)", elapsed < 5.0, elapsed)

# ------------------------------------------------------------ 汇总
print(f"\n{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILED SCENARIOS:", ", ".join(failures))
    sys.exit(1)
print("API SMOKE OK")
