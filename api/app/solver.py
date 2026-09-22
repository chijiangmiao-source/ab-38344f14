"""Minimum missing-transition completion for vacuum-coating interlock logs.

Model
-----
A directed multigraph of states.  Edges (transitions) carry a unique id and an
event code.  The log is a sequence of observed event codes ``o_1 .. o_m``.
Exactly one edge whose code equals ``o_i`` consumes observation ``i``; between
two consumed edges the machine may take any number of *inserted* (previously
unlogged) edges, including edges on cycles.  We must:

1. minimize the total number of inserted edges;
2. among all minimum completions, return the lexicographically smallest full
   sequence of edge ids (the canonical solution);
3. report, for every boundary ``b = 0..m``, the states that can occur at that
   boundary in *some* optimal completion.

Forward / backward dynamic programs
-----------------------------------
``F[b][v]`` = minimum inserted edges in a prefix consuming ``o_1..o_b`` and
standing in state ``v`` at boundary ``b``.

``G[b][u]`` = minimum inserted edges needed to (a) consume ``o_{b+1}..o_m``
starting at ``u`` on boundary ``b`` and then (b) reach the final state.

Within one segment all edges have unit cost, so the inner shortest paths are
Dijkstra runs with the DP values as multi-source seeds (O((V+E) log V) per
observation).

A state ``v`` is possible at boundary ``b`` iff ``F[b][v] + G[b][v] == OPT``.

Canonical lexicographic reconstruction
--------------------------------------
Every edge id gets a rank ``1..E`` (ids sorted lexicographically).  At a DP
node ``(b, x)`` the remaining suffix of an optimal completion has a fixed
length ``L = G[b][x] + (m-b)`` (one consumed edge per remaining observation
plus the inserted edges).  Every candidate first edge leads to a child key of
length ``L-1``, so lex order of length-``L`` keys is exactly the order of the
pairs ``(rank(first edge), dense rank of the child key among all keys of
length L-1)``.  Processing nodes grouped by increasing ``L`` therefore gives
tiny integer ranks and an O((m+1)E) reconstruction with no big integers.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Iterable

MAX_STATES = 80
MAX_TRANSITIONS = 300
MAX_OBSERVATIONS = 200
MIN_STATES = 2
MIN_TRANSITIONS = 1
MIN_OBS = 1

# Largest conceivable optimum: m segments of at most (V-1) inserted edges plus
# a final path of at most (V-1) edges.  Anything at/above INF is unreachable.
INF = 10**9


class ValidationError(ValueError):
    """Raised when the request payload describes an invalid problem."""


class UnreachableError(ValueError):
    """Raised when no completion can consume every observation in order."""

    def __init__(self, message: str, *, observation_index: int | None = None,
                 event_code: str | None = None) -> None:
        super().__init__(message)
        self.observation_index = observation_index  # 1-based; None => cannot end
        self.event_code = event_code


@dataclass(frozen=True)
class Edge:
    id: str
    source: str
    target: str
    code: str


def _is_token(value: object) -> bool:
    return isinstance(value, str) and len(value) > 0 and all(ord(c) < 128 for c in value)


def validate_and_build(
    states: Iterable[str],
    transitions: Iterable[dict],
    start: str,
    end: str,
    observations: Iterable[str],
) -> tuple[list[str], list[Edge], list[str]]:
    """Validate raw payload objects and return ``(states, edges, observations)``."""
    if not isinstance(states, list):
        raise ValidationError("states must be a list")
    if not (MIN_STATES <= len(states) <= MAX_STATES):
        raise ValidationError(
            f"number of states must be between {MIN_STATES} and {MAX_STATES}"
        )
    for s in states:
        if not _is_token(s):
            raise ValidationError(f"state names must be non-empty ASCII strings: {s!r}")
    if len(set(states)) != len(states):
        seen: set[str] = set()
        dupes: list[str] = []
        for s in states:
            if s in seen and s not in dupes:
                dupes.append(s)
            seen.add(s)
        raise ValidationError("duplicate state names: " + ", ".join(sorted(dupes)))

    if not isinstance(transitions, list):
        raise ValidationError("transitions must be a list")
    if not (MIN_TRANSITIONS <= len(transitions) <= MAX_TRANSITIONS):
        raise ValidationError(
            f"number of transitions must be between {MIN_TRANSITIONS} and {MAX_TRANSITIONS}"
        )
    edges: list[Edge] = []
    seen_ids: set[str] = set()
    state_set = set(states)
    for pos, t in enumerate(transitions):
        if not isinstance(t, dict):
            raise ValidationError(f"transitions[{pos}] must be an object")
        tid = t.get("id")
        src = t.get("source")
        dst = t.get("target")
        code = t.get("code")
        if not _is_token(tid):
            raise ValidationError(
                f"transitions[{pos}].id must be a non-empty ASCII string: {tid!r}"
            )
        if tid in seen_ids:
            raise ValidationError(f"duplicate transition id: {tid}")
        seen_ids.add(tid)
        if not _is_token(code):
            raise ValidationError(
                f"transition {tid}: event code must be a non-empty ASCII string: {code!r}"
            )
        if not isinstance(src, str) or src not in state_set:
            raise ValidationError(
                f"transition {tid}: source {src!r} is not a declared state"
            )
        if not isinstance(dst, str) or dst not in state_set:
            raise ValidationError(
                f"transition {tid}: target {dst!r} is not a declared state"
            )
        edges.append(Edge(tid, src, dst, code))

    if not isinstance(start, str) or start not in state_set:
        raise ValidationError(f"start state {start!r} is not a declared state")
    if not isinstance(end, str) or end not in state_set:
        raise ValidationError(f"end state {end!r} is not a declared state")

    if not isinstance(observations, list):
        raise ValidationError("observations must be a list")
    if not (MIN_OBS <= len(observations) <= MAX_OBSERVATIONS):
        raise ValidationError(
            f"number of observations must be between {MIN_OBS} and {MAX_OBSERVATIONS}"
        )
    for pos, o in enumerate(observations):
        if not _is_token(o):
            raise ValidationError(
                f"observations[{pos}] must be a non-empty ASCII string: {o!r}"
            )

    return list(states), edges, list(observations)


def _dijkstra(n: int, adj: list[list[int]], src_of: list[int], dst_of: list[int],
              seeds: dict[int, int], *, reverse: bool = False) -> list[int]:
    """Unit-edge shortest paths with per-source initial costs.

    ``reverse=True`` walks predecessor edges: from a node ``v`` an edge ``e``
    with ``dst_of[e] == v`` relaxes ``src_of[e]``.
    """
    dist = [INF] * n
    heap: list[tuple[int, int]] = []
    for node, cost in seeds.items():
        if cost < INF and cost < dist[node]:
            dist[node] = cost
    for node, cost in enumerate(dist):
        if cost < INF:
            heap.append((cost, node))
    heapq.heapify(heap)
    while heap:
        d, u = heapq.heappop(heap)
        if d != dist[u]:
            continue
        nd = d + 1
        if nd >= INF:
            continue
        for e in adj[u]:
            v = src_of[e] if reverse else dst_of[e]
            if nd < dist[v]:
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist


def solve(states: list[str], edges: list[Edge], obs: list[str],
          start: str, end: str) -> dict:
    """Solve one completion problem.

    Returns a dict with keys ``inserted_count``, ``canonical_sequence`` (list
    of edge records annotated ``consumed``/``inserted``) and
    ``boundary_states``.  Raises :class:`UnreachableError` when no completion
    exists.
    """
    n = len(states)
    m = len(obs)
    index = {s: i for i, s in enumerate(states)}
    s0, send = index[start], index[end]
    ecount = len(edges)

    src_of = [0] * ecount
    dst_of = [0] * ecount
    fwd: list[list[int]] = [[] for _ in range(n)]
    rev: list[list[int]] = [[] for _ in range(n)]
    by_code: dict[str, list[int]] = {}
    for ei, e in enumerate(edges):
        u, v = index[e.source], index[e.target]
        src_of[ei], dst_of[ei] = u, v
        fwd[u].append(ei)
        rev[v].append(ei)
        by_code.setdefault(e.code, []).append(ei)

    # ---- Forward DP -------------------------------------------------------
    F: list[list[int]] = [[INF] * n]
    F[0][s0] = 0
    for b in range(m):
        seeds = {v: F[b][v] for v in range(n) if F[b][v] < INF}
        reach = _dijkstra(n, fwd, src_of, dst_of, seeds)
        nxt = [INF] * n
        for ei in by_code.get(obs[b], ()):  # edges consuming observation b+1
            cand = reach[src_of[ei]]
            if cand < nxt[dst_of[ei]]:
                nxt[dst_of[ei]] = cand
        F.append(nxt)

    # ---- Backward DP ------------------------------------------------------
    G: list[list[int]] = [[INF] * n for _ in range(m + 1)]
    G[m] = _dijkstra(n, rev, src_of, dst_of, {send: 0}, reverse=True)
    for b in range(m - 1, -1, -1):
        seeds: dict[int, int] = {}
        for ei in by_code.get(obs[b], ()):
            tail = G[b + 1][dst_of[ei]]
            u = src_of[ei]
            if tail < seeds.get(u, INF):
                seeds[u] = tail
        G[b] = _dijkstra(n, rev, src_of, dst_of, seeds, reverse=True)

    opt = G[0][s0]
    if opt >= INF:
        # Locate the first observation that cannot be consumed, for the UI.
        fail_boundary = None
        for b in range(1, m + 1):
            if all(c >= INF for c in F[b]):
                fail_boundary = b
                break
        code = obs[fail_boundary - 1] if fail_boundary is not None else None
        if fail_boundary is None:
            # Every observation is consumable but the final state is not.
            raise UnreachableError(
                f"all {m} observations can be consumed but state {end!r} is "
                "not reachable from any possible end-of-log state",
                event_code=None,
            )
        if code not in by_code:
            reason = f"no transition carries event code {code!r}"
        else:
            reason = (
                f"after consuming observation {fail_boundary - 1} (if any), "
                f"no transition carrying {code!r} is reachable"
            )
        raise UnreachableError(
            f"observation {fail_boundary} (code {code!r}) cannot be consumed: {reason}",
            observation_index=fail_boundary,
            event_code=code,
        )

    # ---- Boundary possibility sets ---------------------------------------
    boundary_states: list[list[str]] = []
    for b in range(m + 1):
        possible = [
            states[v] for v in range(n)
            if F[b][v] < INF and G[b][v] < INF and F[b][v] + G[b][v] == opt
        ]
        boundary_states.append(possible)

    # ---- Canonical lexicographic reconstruction --------------------------
    # rank[ei] = dense rank of the edge id (1 = smallest).
    rank = [0] * ecount
    for r, ei in enumerate(sorted(range(ecount), key=lambda i: edges[i].id), start=1):
        rank[ei] = r

    # R[b][x] = dense rank (1-based, smaller = lexicographically smaller) of
    # the canonical suffix key at node (b, x) among keys of the SAME remaining
    # length L = G[b][x] + (m-b).  Ranks cover EVERY node with finite G, not
    # only boundary-possible ones: after an inserted edge the walk is at an
    # intermediate node of the current segment (F[b][x] may be infinite there).
    R: list[list[int]] = [[0] * n for _ in range(m + 1)]

    # Terminal node: boundary m at the final state has an empty suffix.
    R[m][send] = 1
    # Order every node by increasing remaining length L; children always have
    # length L-1, so their ranks are already known.
    by_length: dict[int, list[tuple[int, int]]] = {}
    for b in range(m + 1):
        for x in range(n):
            if G[b][x] >= INF:
                continue
            length = G[b][x] + (m - b)
            if length > 0:
                by_length.setdefault(length, []).append((b, x))

    def _pair_for(b: int, x: int, ei: int) -> tuple[int, int] | None:
        """Return ``(first-edge rank, child dense rank)`` or ``None``."""
        y = dst_of[ei]
        if b < m and edges[ei].code == obs[b] and G[b + 1][y] == G[b][x]:
            child = R[b + 1][y]
            if child:
                return (rank[ei], child)
        if G[b][y] == G[b][x] - 1 and R[b][y]:
            return (rank[ei], R[b][y])
        return None

    for length in sorted(by_length):
        pairs: list[tuple[tuple[int, int], int, int]] = []
        for b, x in by_length[length]:
            best_pair: tuple[int, int] | None = None
            for ei in fwd[x]:
                p = _pair_for(b, x, ei)
                if p is not None and (best_pair is None or p < best_pair):
                    best_pair = p
            if best_pair is not None:
                pairs.append((best_pair, b, x))
        # Dense-rank the best pairs: equal pair => equal rank (equal key).
        pairs.sort(key=lambda t: t[0])
        last_pair: tuple[int, int] | None = None
        cur_rank = 0
        for p, b, x in pairs:
            if p != last_pair:
                cur_rank += 1
                last_pair = p
            R[b][x] = cur_rank

    # Greedy walk following the globally best pair at every node.
    sequence: list[dict] = []
    boundary_path: list[str] = [start]
    b, x = 0, s0
    while b < m or x != send:
        best_pair: tuple[int, int] | None = None
        best_ei = -1
        best_consume = False
        for ei in fwd[x]:
            y = dst_of[ei]
            if b < m and edges[ei].code == obs[b] and G[b + 1][y] == G[b][x]:
                child = R[b + 1][y]
                if child:
                    p = (rank[ei], child)
                    if best_pair is None or p < best_pair:
                        best_pair, best_ei, best_consume = p, ei, True
            if G[b][y] == G[b][x] - 1 and R[b][y]:
                p = (rank[ei], R[b][y])
                if best_pair is None or p < best_pair:
                    best_pair, best_ei, best_consume = p, ei, False
        e = edges[best_ei]
        step = {
            "edge_id": e.id,
            "source": e.source,
            "target": e.target,
            "code": e.code,
            "observation_index": b + 1 if best_consume else None,
        }
        sequence.append({**step, "role": "consumed" if best_consume else "inserted"})
        if best_consume:
            b += 1
            boundary_path.append(e.target)
        x = dst_of[best_ei]

    consumed_ids = [step["edge_id"] for step in sequence if step["role"] == "consumed"]
    total_edges = len(sequence)

    return {
        "inserted_count": opt,
        "total_edge_count": total_edges,
        "canonical_sequence": sequence,
        "canonical_path_states": boundary_path,
        "consumed_edge_ids": consumed_ids,
        "boundary_states": [
            {"boundary": b,
             "after_observation": b if b > 0 else None,
             "states": boundary_states[b]}
            for b in range(m + 1)
        ],
    }
