"""Unit tests + randomized differential tests against an exhaustive solver."""

from __future__ import annotations

import heapq
import random

import pytest

from app.solver import (
    Edge,
    UnreachableError,
    ValidationError,
    solve,
    validate_and_build,
)


# ---------------------------------------------------------------------------
# Exhaustive reference implementation for tiny instances
# ---------------------------------------------------------------------------

def brute_force(states, edges, obs, start, end):
    """Enumerate every optimal completion by DFS.

    Returns ``(opt_insertions, lex_min_id_tuple, boundary_sets)`` where
    ``boundary_sets[b]`` contains every state reachable at boundary ``b`` in
    some minimum completion.  Returns ``None`` when no completion exists.
    """
    idx = {s: i for i, s in enumerate(states)}
    out = [[] for _ in states]
    for ei, e in enumerate(edges):
        out[idx[e.source]].append(ei)

    target = (idx[end], len(obs))
    start_node = (idx[start], 0)

    def dijkstra(reverse: bool):
        # 0/1 costs: consuming an observation costs 0, an insertion costs 1.
        dist = {target if reverse else start_node: 0}
        pq = [(0, target if reverse else start_node)]
        while pq:
            d, node = heapq.heappop(pq)
            if d != dist.get(node):
                continue
            u, k = node
            if not reverse:
                moves = []
                for ei in out[u]:
                    v = idx[edges[ei].target]
                    moves.append(((v, k), 1, ei, False))
                    if k < len(obs) and edges[ei].code == obs[k]:
                        moves.append(((v, k + 1), 0, ei, True))
            else:
                moves = []
                for ei, e in enumerate(edges):
                    if idx[e.target] != u:
                        continue
                    pv = idx[e.source]
                    moves.append(((pv, k), 1, ei, False))
                    if k > 0 and e.code == obs[k - 1]:
                        moves.append(((pv, k - 1), 0, ei, True))
            for nxt, cost, _ei, _consume in moves:
                if d + cost < dist.get(nxt, 1 << 30):
                    dist[nxt] = d + cost
                    heapq.heappush(pq, (d + cost, nxt))
        return dist

    fwd_dist = dijkstra(reverse=False)
    if target not in fwd_dist:
        return None
    opt = fwd_dist[target]
    rev_dist = dijkstra(reverse=True)
    total_len = opt + len(obs)

    best_seq = None
    boundary_sets = [set() for _ in range(len(obs) + 1)]
    boundary_sets[0].add(start)

    def dfs(u, k, used, inserted, seq, bstates):
        nonlocal best_seq
        # Bound by forward optimum and reverse optimum (prunes non-optimal DAG).
        if fwd_dist.get((u, k), 1 << 30) != inserted:
            return
        if inserted + rev_dist.get((u, k), 1 << 30) != opt:
            return
        if used == total_len:
            if (u, k) == target:
                ids = tuple(edges[ei].id for ei in seq)
                if best_seq is None or ids < best_seq:
                    best_seq = ids
                for b, sname in bstates:
                    boundary_sets[b].add(sname)
            return
        for ei in out[u]:
            v = idx[edges[ei].target]
            dfs(v, k, used + 1, inserted + 1, seq + [ei], bstates)
            if k < len(obs) and edges[ei].code == obs[k]:
                dfs(v, k + 1, used + 1, inserted, seq + [ei],
                    bstates + [(k + 1, edges[ei].target)])

    dfs(idx[start], 0, 0, 0, [], [])
    return opt, best_seq, boundary_sets


def random_instance(rng):
    n = rng.randint(2, 4)
    states = [f"S{i}" for i in range(n)]
    ids = list({f"e{rng.randrange(300):03d}" for _ in range(rng.randint(1, 6))})
    codes_pool = ["x", "y"]
    edges = [
        Edge(eid, rng.choice(states), rng.choice(states), rng.choice(codes_pool))
        for eid in ids
    ]
    start = rng.choice(states)
    end = rng.choice(states)
    obs = [rng.choice(codes_pool) for _ in range(rng.randint(1, 2))]
    return states, edges, obs, start, end


def test_randomized_matches_brute_force():
    rng = random.Random(20260922)
    checked = 0
    for _ in range(700):
        states, edges, obs, start, end = random_instance(rng)
        ref = brute_force(states, edges, obs, start, end)
        if ref is None:
            with pytest.raises(UnreachableError):
                solve(states, edges, obs, start, end)
            continue
        opt, best_seq, boundary_sets = ref
        res = solve(states, edges, obs, start, end)
        assert res["inserted_count"] == opt
        got_ids = tuple(s["edge_id"] for s in res["canonical_sequence"])
        assert got_ids == best_seq
        assert len(got_ids) == opt + len(obs)
        consumed = [s for s in res["canonical_sequence"] if s["role"] == "consumed"]
        assert [s["observation_index"] for s in consumed] == list(range(1, len(obs) + 1))
        assert [s["code"] for s in consumed] == obs
        # inserted steps form valid graph transitions between consumed steps
        cur = start
        for step in res["canonical_sequence"]:
            assert step["source"] == cur
            cur = step["target"]
        assert cur == end
        for b in range(len(obs) + 1):
            assert set(res["boundary_states"][b]["states"]) == boundary_sets[b]
        checked += 1
    assert checked > 100


# ---------------------------------------------------------------------------
# Hand-built scenarios
# ---------------------------------------------------------------------------

def test_cycle_repeated_consumption_and_insertion():
    states = ["A", "B"]
    edges = [
        Edge("e_x", "A", "B", "x"),
        Edge("e_y", "B", "A", "y"),
        Edge("e_back", "B", "A", "z"),
    ]
    res = solve(states, edges, ["x", "y", "x"], "A", "A")
    assert res["inserted_count"] == 1
    ids = [s["edge_id"] for s in res["canonical_sequence"]]
    assert ids == ["e_x", "e_y", "e_x", "e_back"]
    assert [s["role"] for s in res["canonical_sequence"]] == [
        "consumed", "consumed", "consumed", "inserted"
    ]
    assert res["boundary_states"][0]["states"] == ["A"]
    assert res["boundary_states"][3]["states"] == ["B"]


def test_same_code_parallel_edges_optimal_tie():
    states = ["A", "B", "C", "D"]
    edges = [
        Edge("p", "A", "B", "x"),
        Edge("q", "A", "C", "x"),
        Edge("r", "B", "D", "u"),
        Edge("s", "C", "D", "v"),
    ]
    res = solve(states, edges, ["x"], "A", "D")
    assert res["inserted_count"] == 1
    ids = [s["edge_id"] for s in res["canonical_sequence"]]
    assert ids == ["p", "r"]
    assert set(res["boundary_states"][1]["states"]) == {"B", "C"}
    assert res["boundary_states"][0]["states"] == ["A"]
    assert res["canonical_path_states"] == ["A", "B"]  # boundary states only
    assert res["canonical_sequence"][-1]["target"] == "D"


def test_self_loop_is_never_optimal():
    states = ["A", "B"]
    edges = [
        Edge("a_loop", "A", "A", "u"),
        Edge("a2b", "A", "B", "x"),
    ]
    res = solve(states, edges, ["x"], "A", "B")
    assert res["inserted_count"] == 0
    assert [s["edge_id"] for s in res["canonical_sequence"]] == ["a2b"]


def test_lex_smaller_equal_length_path_wins():
    # Two length-2 insertion routes to C; ids decide; cycle edge never used.
    states = ["A", "B", "C", "Q"]
    edges = [
        Edge("a", "A", "B", "u"),
        Edge("b", "B", "C", "u"),
        Edge("q", "A", "Q", "u"),
        Edge("r", "Q", "C", "u"),
        Edge("loop", "B", "A", "u"),
        Edge("z_consume", "C", "C", "x"),
    ]
    res = solve(states, edges, ["x"], "A", "C")
    assert res["inserted_count"] == 2
    assert [s["edge_id"] for s in res["canonical_sequence"]] == ["a", "b", "z_consume"]


def test_insertions_before_first_observation_lex_order():
    # Need to reach B before consuming x: shortest insertion prefix A->B;
    # candidate ids "z0" vs "a1" with equal continuation -> "a1" wins.
    states = ["A", "B", "C"]
    edges = [
        Edge("z0", "A", "C", "u"),
        Edge("a1", "A", "B", "u"),
        Edge("cb", "C", "B", "u"),
        Edge("bx", "B", "B", "x"),
    ]
    res = solve(states, edges, ["x"], "A", "B")
    assert res["inserted_count"] == 1
    assert [s["edge_id"] for s in res["canonical_sequence"]] == ["a1", "bx"]
    # At boundary 0 only A is possible in an optimum.
    assert res["boundary_states"][0]["states"] == ["A"]


def test_unreachable_unknown_code():
    states = ["A", "B"]
    edges = [Edge("e1", "A", "B", "x")]
    with pytest.raises(UnreachableError) as exc:
        solve(states, edges, ["nope"], "A", "B")
    assert exc.value.observation_index == 1
    assert exc.value.event_code == "nope"


def test_unreachable_final_state():
    states = ["A", "B", "C"]
    edges = [Edge("e1", "A", "B", "x")]
    with pytest.raises(UnreachableError):
        solve(states, edges, ["x"], "A", "C")


def test_validation_errors():
    good_states = ["A", "B"]
    good_edges = [{"id": "e1", "source": "A", "target": "B", "code": "x"}]
    with pytest.raises(ValidationError):
        validate_and_build(["A"], good_edges, "A", "B", ["x"])
    with pytest.raises(ValidationError):
        validate_and_build(good_states, [], "A", "B", ["x"])
    with pytest.raises(ValidationError):
        validate_and_build(good_states, good_edges, "A", "B", [])
    with pytest.raises(ValidationError):
        validate_and_build(["A", "A"], good_edges, "A", "A", ["x"])
    with pytest.raises(ValidationError):
        validate_and_build(
            good_states,
            [{"id": "e1", "source": "A", "target": "B", "code": "x"},
             {"id": "e1", "source": "B", "target": "A", "code": "y"}],
            "A", "B", ["x"],
        )
    with pytest.raises(ValidationError):
        validate_and_build(
            good_states,
            [{"id": "e2", "source": "A", "target": "Z", "code": "x"}],
            "A", "B", ["x"],
        )
    with pytest.raises(ValidationError):
        validate_and_build(good_states, good_edges, "Z", "B", ["x"])
    with pytest.raises(ValidationError):
        validate_and_build(good_states, good_edges, "A", "B", [""])
    with pytest.raises(ValidationError):
        validate_and_build(good_states, good_edges, "A", "B", ["λ"])


def test_limits_enforced():
    states = [f"S{i}" for i in range(81)]
    with pytest.raises(ValidationError):
        validate_and_build(states, [], "S0", "S1", ["x"])
