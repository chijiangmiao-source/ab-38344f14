"""漏记迁移（联锁日志补全）求解器。

问题建模
========
给定状态集合 S、带唯一标识与事件码的有向迁移集合 T、初态 s0、末态 sf，
以及按时间顺序记录的观测事件序列 o_1 .. o_m。实际发生的迁移序列中：

* 每条观测事件必须由**恰好一条**同事件码迁移按观测顺序消费；
* 未被观测到的迁移（日志漏记）可以任意插入，代价为插入条数；
* 迁移允许成环，同一事件码可出现在多条边上。

要求：最小化插入迁移条数；在所有最优补全中按"完整迁移标识序列"取字典序
最小者（规范解）；并给出每个观测边界（迁移序列中消费某条观测的边之后，
等价地也是消费下一条观测的边之前）在全部最优补全中可能出现的状态集合。

展开图
======
构造分层有向图，节点为 ``(相位 i, 状态 s)``，相位 i 表示已消费前 i 条观测
（0 <= i <= m）。两类边：

* 插入边：任意迁移 t: u -> v，``(i,u) -> (i,v)``，代价 1；
* 消费边：满足 code(t) == o_{i+1} 的迁移 t: u -> v，
  ``(i,u) -> (i+1,v)``，代价 0。

消费边只能从相位 i 到 i+1，故路径上消费边严格按序、恰有 m 条；插入边
不改变相位且允许环。目标为 ``(0,s0) -> (m,sf)`` 的最小代价路径。

由于权值仅为 0/1，使用 Dial 算法（桶 Dijkstra）。相位内迁移边恒为权 1、
跨相位消费边恒为权 0，实际结构是"相位内单位代价可达闭包 + 零代价跨层"，
Dial 实现简单且与更专门的写法同阶。

前向距离 f[i][s]：从 (0,s0) 到 (i,s) 的最小插入数；
后向距离 h[i][s]：从 (i,s) 到 (m,sf) 的最小插入数。
总最优代价 K = h[0][s0] = f[m][sf]。

边界可能状态
============
相位 i 的状态 s 出现在某条最优路径上，当且仅当
``f[i][s] + h[i][s] == K``（最短路径的局部最优性，0/1 整数权下充要）。

规范解（字典序最小最优标识序列）
================================
定义 G(i,s) 为从 (i,s) 到 (m,sf) 的最短路径中字典序最小的标识序列。
常规"逐跳选最小标识"贪心在一种情况下失效：同码迁移 t 在同一节点既可作为
插入边（目标 (i,v)）又可作为消费边（目标 (i+1,v)），二者首标识相同但
后继不同，必须比较后继序列。

利用势函数 P(i,s) = h[i][s]*(m+1) + (m-i)：最优插入边使 h 减 1（P 减
m+1），最优消费边使 i 增 1（P 减 1），故最优边的目标势严格减小，依赖
无环。按 P 从小到大处理节点，取
``key(node) = min 可行边 (t.id, rank(目标节点))``，
再对全部 key 全局排序赋予密集秩；rank 次序即 G 序列字典序（空序列
rank 最小）。最后从 (0,s0) 沿选定边走即得规范解。
"""
from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import sys
from typing import Dict, List, Optional, Sequence, Tuple

# 规范解重放链最长 K + m ≤ (m+1)(n-1) + m（约 1.6 万），放宽默认递归深度。
sys.setrecursionlimit(100000)

INF = float("inf")


class ValidationError(Exception):
    """输入非法错误，message 面向用户、field 用于页面定位。"""

    def __init__(self, message: str, field: Optional[str] = None, index: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.field = field
        self.index = index


class UnreachableError(Exception):
    """输入合法但不存在可到达终态的补全。"""


@dataclass(frozen=True)
class Transition:
    id: str
    event_code: str
    source: str
    target: str


@dataclass
class SolveResult:
    feasible: bool
    inserted_count: int
    canonical_sequence: List[str] = field(default_factory=list)
    canonical_events: List[Optional[int]] = field(default_factory=list)
    """canonical_events[k] 为第 k 步消费的观测序号（1 基），插入步为 None。"""
    boundary_states: List[List[str]] = field(default_factory=list)
    """boundary_states[i]：第 i 个观测边界（i=0 为初态边界，i=m 为终态边界）
    在全部最优补全中的可能状态集合，按状态名升序。"""


def _is_ascii_token(value: str) -> bool:
    return len(value) > 0 and all(32 < ord(c) < 127 for c in value)


def validate_input(
    raw_states: Sequence[str],
    raw_transitions: Sequence[Transition],
    initial_state: str,
    final_state: str,
    observations: Sequence[str],
    *,
    min_states: int = 2,
    max_states: int = 80,
    min_transitions: int = 1,
    max_transitions: int = 300,
    min_observations: int = 1,
    max_observations: int = 200,
) -> Tuple[List[str], List[Transition]]:
    """校验输入，返回 (排序后的状态列表, 迁移列表)。非法时抛 ValidationError。"""
    from .models import MAX_TOKEN_LEN

    if not isinstance(raw_states, list) or len(raw_states) == 0:
        raise ValidationError("状态集合不能为空，至少需要 2 个状态。", "states")
    if not (min_states <= len(raw_states) <= max_states):
        raise ValidationError(
            f"状态数量须在 {min_states}–{max_states} 之间，当前为 {len(raw_states)}。",
            "states",
        )
    for idx, s in enumerate(raw_states):
        if not isinstance(s, str) or not _is_ascii_token(s):
            raise ValidationError(
                "状态须为非空 ASCII 可见字符（不含空格）。", "states", idx
            )
        if len(s) > MAX_TOKEN_LEN:
            raise ValidationError(
                f"状态长度不能超过 {MAX_TOKEN_LEN} 个字符。", "states", idx
            )
    if len(set(raw_states)) != len(raw_states):
        dup = next(s for s in raw_states if raw_states.count(s) > 1)
        raise ValidationError(f"状态重复：{dup!r}，状态必须唯一。", "states")

    if not (min_transitions <= len(raw_transitions) <= max_transitions):
        raise ValidationError(
            f"迁移数量须在 {min_transitions}–{max_transitions} 之间，当前为 {len(raw_transitions)}。",
            "transitions",
        )
    state_set = set(raw_states)
    seen_ids: set[str] = set()
    for idx, t in enumerate(raw_transitions):
        if not t.id or not _is_ascii_token(t.id):
            raise ValidationError(
                "迁移标识须为非空 ASCII 可见字符（不含空格）。", "transitions", idx
            )
        if len(t.id) > MAX_TOKEN_LEN:
            raise ValidationError(
                f"迁移标识长度不能超过 {MAX_TOKEN_LEN} 个字符。", "transitions", idx
            )
        if t.id in seen_ids:
            raise ValidationError(f"迁移标识重复：{t.id!r}。", "transitions", idx)
        seen_ids.add(t.id)
        if not t.event_code or not _is_ascii_token(t.event_code):
            raise ValidationError(
                "事件码须为非空 ASCII 可见字符（不含空格）。", "transitions", idx
            )
        if len(t.event_code) > MAX_TOKEN_LEN:
            raise ValidationError(
                f"事件码长度不能超过 {MAX_TOKEN_LEN} 个字符。", "transitions", idx
            )
        if t.source not in state_set:
            raise ValidationError(
                f"迁移 {t.id!r} 的源状态 {t.source!r} 不在状态集合中。",
                "transitions",
                idx,
            )
        if t.target not in state_set:
            raise ValidationError(
                f"迁移 {t.id!r} 的目标状态 {t.target!r} 不在状态集合中。",
                "transitions",
                idx,
            )

    if initial_state not in state_set:
        raise ValidationError("初态必须是状态集合中的状态。", "initial_state")
    if final_state not in state_set:
        raise ValidationError("末态必须是状态集合中的状态。", "final_state")

    if not (min_observations <= len(observations) <= max_observations):
        raise ValidationError(
            f"观测事件数量须在 {min_observations}–{max_observations} 之间，当前为 {len(observations)}。",
            "observations",
        )
    for idx, code in enumerate(observations):
        if not code or not _is_ascii_token(code):
            raise ValidationError(
                "观测事件码须为非空 ASCII 可见字符（不含空格）。", "observations", idx
            )
        if len(code) > MAX_TOKEN_LEN:
            raise ValidationError(
                f"事件码长度不能超过 {MAX_TOKEN_LEN} 个字符。", "observations", idx
            )

    return sorted(raw_states), list(raw_transitions)


def solve(
    states: Sequence[str],
    transitions: Sequence[Transition],
    initial_state: str,
    final_state: str,
    observations: Sequence[str],
) -> SolveResult:
    """求最小漏记补全、规范解与各观测边界的可能状态集合。"""
    n = len(states)
    m = len(observations)
    index = {s: i for i, s in enumerate(states)}

    # 邻接（插入边，按相位复用）：out[u] = [(v, t_index), ...]
    out: List[List[Tuple[int, int]]] = [[] for _ in range(n)]
    rev: List[List[Tuple[int, int]]] = [[] for _ in range(n)]
    # 各事件码的迁移下标列表
    by_code: Dict[str, List[int]] = {}
    for ti, t in enumerate(transitions):
        u, v = index[t.source], index[t.target]
        out[u].append((v, ti))
        rev[v].append((u, ti))
        by_code.setdefault(t.event_code, []).append(ti)

    # 快速不可达判定：某条观测事件码根本没有迁移能消费。
    for code in observations:
        if code not in by_code:
            raise UnreachableError(f"事件码 {code!r} 没有任何同码迁移，无法消费该观测。")

    def dijkstra_forward() -> List[List[int]]:
        """f[i][s]：(0,s0) 到 (i,s) 的最小代价（插入条数）。"""
        f = [[INF] * n for _ in range(m + 1)]
        start = index[initial_state]
        f[0][start] = 0
        pq: List[Tuple[int, int, int]] = [(0, 0, start)]
        while pq:
            d, i, u = heapq.heappop(pq)
            if d != f[i][u]:
                continue
            nd = d + 1
            for v, _ti in out[u]:  # 插入边，权 1
                if f[i][v] > nd:
                    f[i][v] = nd
                    heapq.heappush(pq, (nd, i, v))
            if i < m:
                for ti in by_code.get(observations[i], ()):  # 消费边，权 0
                    t = transitions[ti]
                    if index[t.source] != u:
                        continue
                    v = index[t.target]
                    if f[i + 1][v] > d:
                        f[i + 1][v] = d
                        heapq.heappush(pq, (d, i + 1, v))
        return f

    def dijkstra_backward() -> List[List[int]]:
        """h[i][s]：(i,s) 到 (m,sf) 的最小代价。在反向展开图上做 Dijkstra。"""
        h = [[INF] * n for _ in range(m + 1)]
        goal = index[final_state]
        h[m][goal] = 0
        pq: List[Tuple[int, int, int]] = [(0, m, goal)]
        while pq:
            d, i, v = heapq.heappop(pq)
            if d != h[i][v]:
                continue
            nd = d + 1
            for u, _ti in rev[v]:  # 反向插入边，权 1
                if h[i][u] > nd:
                    h[i][u] = nd
                    heapq.heappush(pq, (nd, i, u))
            if i > 0:
                for ti in by_code.get(observations[i - 1], ()):  # 反向消费边，权 0
                    t = transitions[ti]
                    if index[t.target] != v:
                        continue
                    u = index[t.source]
                    if h[i - 1][u] > d:
                        h[i - 1][u] = d
                        heapq.heappush(pq, (d, i - 1, u))
        return h

    f = dijkstra_forward()
    h = dijkstra_backward()

    k = h[0][index[initial_state]]
    if k == INF:
        raise UnreachableError("不存在能从初态消费全部观测并到达末态的补全。")

    # 各观测边界的可能状态。
    # 边界 0 为初态（固定）；边界 i（i>=1）为第 i 条消费边的着陆点 v，
    # 充要条件：存在码 o_i 的消费边 u->v 使 f[i-1][u] + h[i][v] == K
    # （f 路径在相位 i-1 内允许插入移动到起跳点 u，消费后由 h 接续）。
    boundary_states: List[List[str]] = [[initial_state]]
    for i in range(1, m + 1):
        members_set: set[int] = set()
        for ti in by_code.get(observations[i - 1], ()):
            t = transitions[ti]
            u = index[t.source]
            v = index[t.target]
            if f[i - 1][u] != INF and h[i][v] != INF and f[i - 1][u] + h[i][v] == k:
                members_set.add(v)
        boundary_states.append([states[s] for s in sorted(members_set, key=lambda x: states[x])])

    # ---- 字典序最小规范解：递归记忆化比较 ----
    # best(i,s) = 可行最优边中使 (t.id ++ best(目标)) 字典序最小者；
    # 可行边目标势严格更小，故比较沿势函数严格下降、必然终止。
    goal_idx = index[final_state]
    goal_node = (m, goal_idx)
    compare_memo: Dict[Tuple[Tuple[int, int], Tuple[int, int]], int] = {}
    choice_memo: Dict[Tuple[int, int], Tuple[str, Tuple[int, int]]] = {}

    def feasible_options(i: int, u: int):
        """节点 (i,u) 上属于某条最优路径的出边：(迁移标识, 目标节点)。"""
        opts = []
        for v, ti in out[u]:  # 插入边可行 ⇔ 1 + h[目标] == h[当前]
            if h[i][v] != INF and 1 + h[i][v] == h[i][u]:
                opts.append((transitions[ti].id, (i, v)))
        if i < m:  # 消费边可行 ⇔ h[i+1][目标] == h[i][当前]
            for ti in by_code.get(observations[i], ()):
                t = transitions[ti]
                if index[t.source] != u:
                    continue
                v = index[t.target]
                if h[i + 1][v] != INF and h[i + 1][v] == h[i][u]:
                    opts.append((t.id, (i + 1, v)))
        return opts

    def compare_seq(a: Tuple[int, int], b: Tuple[int, int]) -> int:
        """best 序列字典序比较：-1 / 0 / 1。空序列（终态节点）最小。"""
        if a == b:
            return 0
        key = (a, b)
        if key in compare_memo:
            return compare_memo[key]
        if a == goal_node:
            result = -1
        elif b == goal_node:
            result = 1
        else:
            (ida, ta), (idb, tb) = best_choice(a), best_choice(b)
            if ida < idb:
                result = -1
            elif ida > idb:
                result = 1
            else:
                result = compare_seq(ta, tb)
        compare_memo[key] = result
        return result

    def best_choice(node: Tuple[int, int]) -> Tuple[str, Tuple[int, int]]:
        if node in choice_memo:
            return choice_memo[node]
        best_opt: Optional[Tuple[str, Tuple[int, int]]] = None
        for opt in feasible_options(node[0], node[1]):
            if best_opt is None:
                best_opt = opt
            else:
                tid, tgt = opt
                bid, btgt = best_opt
                if tid < bid or (tid == bid and compare_seq(tgt, btgt) < 0):
                    best_opt = opt
        if best_opt is None:  # 防御性：h 有限则必有可行边
            raise UnreachableError("规范解构造中断（内部错误：未找到可行边）。")
        choice_memo[node] = best_opt
        return best_opt

    # 从初态沿 best_choice 重放。
    seq: List[str] = []
    events: List[Optional[int]] = []
    node = (0, index[initial_state])
    while node != goal_node:
        tid, tgt = best_choice(node)
        seq.append(tid)
        events.append(tgt[0] if tgt[0] > node[0] else None)  # 相位增加 => 消费步
        node = tgt

    return SolveResult(
        feasible=True,
        inserted_count=k,
        canonical_sequence=seq,
        canonical_events=events,
        boundary_states=boundary_states,
    )
