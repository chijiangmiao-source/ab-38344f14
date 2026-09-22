"""求解器单元测试：环补全、字典序规范解、边界可能状态、不可达与非法输入。"""
from __future__ import annotations

import itertools
import random

import pytest

from app.solver import (
    Transition,
    UnreachableError,
    ValidationError,
    solve,
    validate_input,
)


def T(id, code, src, dst):
    return Transition(id=id, event_code=code, source=src, target=dst)


def brute_force(states, transitions, s0, sf, obs, max_insert):
    """枚举所有至多 max_insert 条插入的完整迁移序列（DFS），返回
    (最小插入数, 字典序最小标识序列, 各边界可能状态集合)。"""
    out = {}
    for t in transitions:
        out.setdefault(t.source, []).append(t)

    best = {"k": None, "seq": None, "boundaries": [set() for _ in range(len(obs) + 1)]}

    def dfs(cur, phase, inserted, seq, bounds):
        seqt = tuple(seq)
        if phase == len(obs) and cur == sf:
            if best["k"] is None or inserted < best["k"] or (
                inserted == best["k"] and seqt < best["seq"]
            ):
                best["k"] = inserted
                best["seq"] = seqt
            # 收集最优边界在更新后阶段处理；先记录所有可行终态路径
            best["_all_paths"].append((inserted, tuple(seq), tuple(bounds)))
        if inserted >= max_insert:
            return
        # 插入边
        for t in out.get(cur, []):
            dfs(t.target, phase, inserted + 1, seq + [t.id], bounds)
        # 消费边
        if phase < len(obs):
            for t in out.get(cur, []):
                if t.event_code == obs[phase]:
                    nb = list(bounds)
                    nb[phase + 1] = t.target
                    dfs(t.target, phase + 1, inserted, seq + [t.id], nb)

    best["_all_paths"] = []
    dfs(s0, 0, 0, [], [s0] + [None] * len(obs))
    paths = best.pop("_all_paths")
    if best["k"] is None:
        return None
    k = best["k"]
    boundaries = [set() for _ in range(len(obs) + 1)]
    for ins, _seq, bounds in paths:
        if ins == k:
            for i, b in enumerate(bounds):
                boundaries[i].add(b)
    return k, list(best["seq"]), [sorted(b) for b in boundaries]


# ---------------------------------------------------------------- 基本用例

def test_simple_direct_consumption():
    """观测边直达，零插入。"""
    r = solve(["A", "B"], [T("t1", "E1", "A", "B")], "A", "B", ["E1"])
    assert r.inserted_count == 0
    assert r.canonical_sequence == ["t1"]
    assert r.canonical_events == [1]
    assert r.boundary_states == [["A"], ["B"]]


def test_single_insertion_before_observation():
    r = solve(
        ["A", "B", "C"],
        [T("p", "PUMP_ON", "A", "B"), T("v", "V1_OPEN", "B", "C")],
        "A", "C", ["V1_OPEN"],
    )
    assert r.inserted_count == 1
    assert r.canonical_sequence == ["p", "v"]
    assert r.canonical_events == [None, 1]
    assert r.boundary_states[0] == ["A"]
    assert r.boundary_states[1] == ["C"]


# ---------------------------------------------------------------- 成环

def test_cycle_must_be_traversed_to_enable_event():
    """泵启动需绕行阀门环：A ->(环 t-loop) ... 事件边只在环后状态可用。"""
    trans = [
        T("a", "X", "A", "B"),
        T("loop", "L", "B", "A"),  # 成环
        T("ready", "EV", "B", "C"),
    ]
    r = solve(["A", "B", "C"], trans, "A", "C", ["EV"])
    assert r.inserted_count == 1          # a 是漏记插入，ready 消费观测
    assert r.canonical_sequence == ["a", "ready"]
    # 强制事件码为环边：必须绕环
    trans2 = [T("a", "X", "A", "B"), T("loop", "EV", "B", "A"), T("b", "Y", "A", "C")]
    r2 = solve(["A", "B", "C"], trans2, "A", "C", ["EV"])
    # 路径：a(插), loop(消费, 回到A), b(插) => 2 插入
    assert r2.inserted_count == 2
    assert r2.canonical_sequence == ["a", "loop", "b"]
    assert r2.canonical_events == [None, 1, None]


def test_repeated_cycles_with_multiple_observations():
    """同一自环事件码消费多次，每圈一次。"""
    trans = [T("tick", "CLK", "A", "A"), T("done", "END", "A", "B")]
    r = solve(["A", "B"], trans, "A", "B", ["CLK", "CLK", "END"])
    assert r.inserted_count == 0
    assert r.canonical_sequence == ["tick", "tick", "done"]
    assert r.canonical_events == [1, 2, 3]


# ---------------------------------------------------------------- 同码多边

def test_same_code_on_multiple_edges_boundary_sets():
    """同码两条边，两个消费位置产生边界分叉。"""
    trans = [
        T("e1", "EV", "A", "B"),
        T("e2", "EV", "A", "C"),
        T("g1", "G", "B", "Z"),
        T("g2", "G", "C", "Z"),
    ]
    r = solve(["A", "B", "C", "Z"], trans, "A", "Z", ["EV", "G"])
    assert r.inserted_count == 0
    assert r.boundary_states[1] == ["B", "C"]
    assert r.boundary_states[0] == ["A"]
    assert r.boundary_states[2] == ["Z"]
    # 字典序：e1 < e2，首跳选 e1
    assert r.canonical_sequence[0] == "e1"
    assert r.canonical_sequence == ["e1", "g1"]


def test_same_edge_consume_vs_insert_tie_decided_by_suffix():
    """同一条迁移 t 在同一节点既可消费观测、也可作漏记插入，两种最优走法
    插入数相同，规范解必须由后继序列（而非首标识）决定。

    观测 [E, X]，A -> F：
      t:E A->B；d:Z B->D；r:X D->F；l:E B->Y；x:X Y->F
    P1（t 消费）：t -> d(插) -> r 消费 X         = [t,d,r]，1 插入
    P2（t 插入）：t(插) -> l 消费 E -> x 消费 X  = [t,l,x]，1 插入
    两序列首标识相同（同为 t），比较第二项决定胜负。
    """
    states = ["A", "B", "D", "Y", "F"]
    trans = [
        T("t", "E", "A", "B"),
        T("d", "Z", "B", "D"),
        T("r", "X", "D", "F"),
        T("l", "E", "B", "Y"),
        T("x", "X", "Y", "F"),
    ]
    r = solve(states, trans, "A", "F", ["E", "X"])
    assert r.inserted_count == 1
    assert r.canonical_sequence == ["t", "d", "r"]  # d < l
    assert r.canonical_events == [1, None, 2]
    # 边界1（消费 E 之后）：P1 在 B、P2 在 Y，二者都在最优补全中
    assert r.boundary_states[1] == ["B", "Y"]
    assert r.boundary_states[2] == ["F"]

    # 交换两条分叉边的标识：插入分支第二项变小，规范解翻转
    trans2 = [
        T("t", "E", "A", "B"),
        T("z", "Z", "B", "D"),
        T("r", "X", "D", "F"),
        T("a", "E", "B", "Y"),
        T("x", "X", "Y", "F"),
    ]
    r2 = solve(states, trans2, "A", "F", ["E", "X"])
    assert r2.inserted_count == 1
    assert r2.canonical_sequence == ["t", "a", "x"]  # a < z
    assert r2.canonical_events == [None, 1, 2]
    assert r2.boundary_states[1] == ["B", "Y"]


# ---------------------------------------------------------------- 不可达

def test_unreachable_no_path():
    trans = [T("a", "E", "A", "B")]
    with pytest.raises(UnreachableError):
        solve(["A", "B", "C"], trans, "A", "C", ["E"])


def test_unreachable_unknown_event_code():
    with pytest.raises(UnreachableError):
        solve(["A", "B"], [T("a", "E", "A", "B")], "A", "B", ["OTHER"])


def test_unreachable_observation_order_blocks():
    # E 边 B->A 方向与初态相反，且无法到达 B
    trans = [T("back", "E", "B", "A"), T("x", "X", "A", "A")]
    with pytest.raises(UnreachableError):
        solve(["A", "B"], trans, "A", "A", ["E"])


# ---------------------------------------------------------------- 校验

def test_validation_duplicate_state():
    with pytest.raises(ValidationError) as e:
        validate_input(["A", "A"], [T("a", "E", "A", "A")], "A", "A", ["E"])
    assert e.value.field == "states"


def test_validation_duplicate_transition_id():
    with pytest.raises(ValidationError) as e:
        validate_input(
            ["A", "B"],
            [T("x", "E", "A", "B"), T("x", "E", "B", "A")],
            "A", "B", ["E"],
        )
    assert e.value.field == "transitions"
    assert e.value.index == 1


def test_validation_dangling_endpoint():
    with pytest.raises(ValidationError) as e:
        validate_input(["A", "B"], [T("a", "E", "A", "X")], "A", "B", ["E"])
    assert e.value.field == "transitions"
    assert e.value.index == 0


def test_validation_counts():
    with pytest.raises(ValidationError):
        validate_input(["A"], [T("a", "E", "A", "A")], "A", "A", ["E"])
    with pytest.raises(ValidationError):
        validate_input(["A", "B"], [], "A", "B", ["E"])
    with pytest.raises(ValidationError):
        validate_input(["A", "B"], [T("a", "E", "A", "B")], "A", "B", [])


def test_validation_non_ascii():
    with pytest.raises(ValidationError):
        validate_input(["A", "阀"], [T("a", "E", "A", "A")], "A", "A", ["E"])
    with pytest.raises(ValidationError):
        validate_input(["A", "B"], [T("a", "E 1", "A", "B")], "A", "B", ["E 1"])


# ---------------------------------------------------------------- 暴力对拍

def test_randomized_against_brute_force():
    """随机小图：与枚举对拍最优值、规范序列与全部边界集合。"""
    rng = random.Random(20260922)
    for trial in range(120):
        nstate = rng.randint(2, 4)
        states = [f"s{i}" for i in range(nstate)]
        nedge = rng.randint(1, 7)
        ids = [f"e{i}" for i in range(nedge)]
        codes_pool = ["A", "B"]
        trans = []
        used_pairs = set()
        for eid in ids:
            while True:
                src = rng.choice(states)
                dst = rng.choice(states)
                if (src, dst) not in used_pairs or rng.random() < 0.3:
                    break
            used_pairs.add((src, dst))
            trans.append(T(eid, rng.choice(codes_pool), src, dst))
        m = rng.randint(1, 3)
        obs = [rng.choice(codes_pool) for _ in range(m)]
        s0, sf = rng.choice(states), rng.choice(states)

        expected = brute_force(states, trans, s0, sf, obs, max_insert=5)
        if expected is None:
            with pytest.raises(UnreachableError):
                solve(states, trans, s0, sf, obs)
            continue
        r = solve(states, trans, s0, sf, obs)
        ek, eseq, ebounds = expected
        assert r.inserted_count == ek, (trial, trans, obs, s0, sf, r.inserted_count, ek)
        assert r.canonical_sequence == eseq, (trial, trans, obs, r.canonical_sequence, eseq)
        assert r.boundary_states == ebounds, (trial, trans, obs, r.boundary_states, ebounds)
        # 不变量：规范序列中恰有 m 条消费步，事件序号递增
        consumed = [e for e in r.canonical_events if e is not None]
        assert consumed == list(range(1, m + 1))
        # 每步事件码与观测一致、状态迁移真实存在
        tmap = {t.id: t for t in trans}
        cur = s0
        ci = 0
        for step_id, ev in zip(r.canonical_sequence, r.canonical_events):
            t = tmap[step_id]
            assert t.source == cur
            cur = t.target
            if ev is not None:
                ci += 1
                assert t.event_code == obs[ev - 1]
            else:
                ci_ = ci
        assert cur == sf
        assert r.canonical_events.count(None) == r.inserted_count


def test_switch_timing_boundary_fork():
    """插入切换边的时机任意时，边界集合精确反映分叉。

    t:E A->A（自环）；z:X A->B；b:E B->B；g:G B->B。
    观测 100 个 E + 50 个 G，A->B。z 恰插入一次，可在任意 E 之后切换：
    边界 1..100 均为 {A,B}，边界 101 起钉死在 B。
    """
    trans = [
        T("t", "E", "A", "A"),
        T("z", "X", "A", "B"),
        T("b", "E", "B", "B"),
        T("g", "G", "B", "B"),
    ]
    r = solve(["A", "B"], trans, "A", "B", ["E"] * 100 + ["G"] * 50)
    assert r.inserted_count == 1
    assert r.canonical_sequence == ["t"] * 100 + ["z"] + ["g"] * 50
    assert r.boundary_states[1] == ["A", "B"]
    assert r.boundary_states[100] == ["A", "B"]
    assert r.boundary_states[101] == ["B"]
    assert r.boundary_states[150] == ["B"]


def test_boundary_sets_cover_all_optimal_paths():
    """边界集合精确等于全部最优路径可达边界（构造分叉再汇合的图）。"""
    trans = [
        T("a1", "E", "S", "L"),
        T("a2", "E", "S", "R"),
        T("x1", "X", "L", "M"),
        T("x2", "X", "R", "M"),
        T("go", "F", "M", "Z"),
    ]
    r = solve(["S", "L", "R", "M", "Z"], trans, "S", "Z", ["E", "X", "F"])
    assert r.inserted_count == 0
    assert r.boundary_states[1] == ["L", "R"]
    assert r.boundary_states[2] == ["M"]
    assert r.boundary_states[3] == ["Z"]
