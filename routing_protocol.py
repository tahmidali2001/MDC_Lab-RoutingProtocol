"""
Link Lifetime-Based Min-Cost Max-Flow (LL-MCMF) Routing Protocol
=================================================================
Implements the algorithm described in:

    "Task Multinetwork Routing Protocol Design"
     Section: "A Link Lifetime-based Min Cost Max Flow Routing Algorithm"

The algorithm is a successive-shortest-path (Dijkstra-based) min-cost
max-flow solver for multi-technology MANETs (Wi-Fi + Bluetooth).
It selects single or multiple paths based on link lifetime, bandwidth,
energy, and an optional hard deadline.

Variables (matching the task document notation)
-----------------------------------------------
  D_a        – total application data to transfer (data units)
  DL_a       – application task deadline (seconds)
  D_u        – one data unit size
  n_s, n_t   – source / destination nodes
  b_ij       – available bandwidth on link l between nodes i and j
  ttdu_ij    – transmission time per data unit on link l
  ec_ij      – energy consumption per data unit on link l
  llt_ij     – link lifetime of link l between i and j
  plt_p      – lifetime of path p = min(llt_ij) over all links in p
  pre_p      – remaining energy of path p = min(re_ij) over all links in p
  re_ij      – min(re_i, re_j)  residual energy of a link
  d_ij       – flow (data) assigned to link l
"""

from __future__ import annotations

import heapq
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1 – NETWORK MODEL
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Node:
    """A device in the multi-technology MANET."""
    node_id:         int
    proc_speed:      float   # ps_i   – instructions per second
    proc_energy:     float   # pec_i  – energy per instruction (J)
    memory:          float   # mem_i  – available memory (bytes)
    residual_energy: float   # re_i   – remaining battery (J)

    def __repr__(self) -> str:
        return f"Node(id={self.node_id}, re={self.residual_energy:.1f}J)"


@dataclass
class Link:
    """
    Directed wireless link between two nodes for one radio technology.

    Two nodes may have multiple parallel links (one per technology),
    forming the multi-layer directed capacitated multigraph G=(N,L).
    """
    src:       int    # source node id
    dst:       int    # destination node id
    tech:      str    # 'wifi' | 'bluetooth'
    bandwidth: float  # b_ij   – available bandwidth  (Mbps)
    ttdu:      float  # ttdu_ij – transmission time per data unit (s / DU)
    energy:    float  # ec_ij  – energy per data unit  (J / DU)
    lifetime:  float  # llt_ij – estimated link lifetime (s)

    def residual_energy(self, nodes: dict[int, Node]) -> float:
        """re_ij = min(re_i, re_j)  (link residual energy)."""
        n_i = nodes.get(self.src)
        n_j = nodes.get(self.dst)
        re_i = n_i.residual_energy if n_i else math.inf
        re_j = n_j.residual_energy if n_j else math.inf
        return min(re_i, re_j)

    def __repr__(self) -> str:
        return (f"Link({self.src}→{self.dst} [{self.tech:>9s}] "
                f"bw={self.bandwidth:6.2f} Mbps  ttdu={self.ttdu:.4f} s/DU  "
                f"ec={self.energy:.4f} J/DU  lt={self.lifetime:.1f} s)")


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2 – RESIDUAL GRAPH  (internal use)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class _REdge:
    """Edge in the residual graph."""
    dst:      int
    cap:      float   # residual capacity (data units)
    cost:     float   # cost per unit (ttdu or energy)
    lifetime: float   # safe lifetime of underlying physical link
    energy:   float   # ec_ij per data unit  (0 for reverse edges)
    rev_idx:  int     # index of the reverse edge in adj[dst]
    orig:     Optional[Link] = None   # None for reverse (back-flow) edges


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3 – RESULT TYPES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class PathResult:
    """One augmenting path found during the algorithm."""
    nodes:     list[int]   # node sequence  [n_s, ..., n_t]
    data:      float        # d_st_pm – data assigned to this path (DU)
    lifetime:  float        # plt_p   – minimum link lifetime on path (s)
    bandwidth: float        # bottleneck bandwidth (Mbps)
    cost:      float        # total objective cost for this path

    def __repr__(self) -> str:
        arrow = " → ".join(str(n) for n in self.nodes)
        return (f"[{arrow}]  data={self.data:.3f} DU  "
                f"bw={self.bandwidth:.2f} Mbps  lt={self.lifetime:.2f} s  "
                f"cost={self.cost:.5f}")


@dataclass
class RoutingResult:
    """Complete output of one call to LLMCMFRouter.route()."""
    paths:             list[PathResult]
    total_data_routed: float
    remaining_data:    float
    total_cost:        float
    deadline_met:      bool
    feasible:          bool
    iterations:        int

    def summary(self) -> str:
        lines = [
            "╔══════════════════════════════════════════════════════╗",
            "║         LL-MCMF ROUTING RESULT SUMMARY               ║",
            "╠══════════════════════════════════════════════════════╣",
            f"║  Feasible      : {str(self.feasible):<35s}║",
            f"║  Deadline met  : {str(self.deadline_met):<35s}║",
            f"║  Data routed   : {self.total_data_routed:<35.3f}║",
            f"║  Data remaining: {self.remaining_data:<35.3f}║",
            f"║  Total cost    : {self.total_cost:<35.5f}║",
            f"║  Iterations    : {self.iterations:<35d}║",
            f"║  Paths used    : {len(self.paths):<35d}║",
            "╠══════════════════════════════════════════════════════╣",
        ]
        for i, p in enumerate(self.paths, 1):
            lines.append(f"║  Path {i:>2}: {str(p):<44s}║")
        lines.append("╚══════════════════════════════════════════════════════╝")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4 – THE LL-MCMF ROUTING ALGORITHM
# ═══════════════════════════════════════════════════════════════════════════

class LLMCMFRouter:
    """
    Link Lifetime-Based Min-Cost Max-Flow Router
    =============================================

    Implements the successive-shortest-path algorithm from the task document.

    Objectives
    ----------
    LATENCY  : minimise total transmission time   (cost = ttdu)
    ENERGY   : minimise total energy consumption  (cost = ec)
    DEADLINE : minimise ttdu subject to deadline  (same cost, deadline enforced)

    Safety Margin
    -------------
    A 15% safety factor is applied to all link lifetime estimates before use,
    so that a link is considered available for  llt × 0.85  seconds.
    """

    LATENCY  = "latency"
    ENERGY   = "energy"
    DEADLINE = "deadline"

    _SAFETY   = 0.15   # 15% lifetime safety margin
    _MAX_ITER = 1000   # guard against infinite loops

    def __init__(self, nodes: list[Node], links: list[Link]):
        self.nodes: dict[int, Node] = {n.node_id: n for n in nodes}
        self.links: list[Link] = links

    # ─────────────────────────────────────────────────────────────────────
    # Public: route()
    # ─────────────────────────────────────────────────────────────────────

    def route(
        self,
        data_volume:  float,                  # D_a  total data (DU)
        source:       int,                    # n_s
        destination:  int,                    # n_t
        deadline:     float = math.inf,       # DL_a (s)
        objective:    str   = LATENCY,
        data_unit:    float = 1.0,            # D_u  size of one data unit
    ) -> RoutingResult:
        """
        Transfer data_volume data units from source to destination.

        Algorithm (pseudocode from task document, Algorithm 1):
        ─────────────────────────────────────────────────────────
        1.  d_st = 0 ; create residual network R(d_st)
        2.  WHILE D_a > 0 AND deadline not missed:
        3.    Find shortest path p via Dijkstra (min cost)
        4.    plt = min(llt_ij) over links in p       [path lifetime]
        5.    pre = min(re_ij)  over links in p       [path residual energy]
        6.    b   = min(b_ij)   over links in p       [bottleneck bandwidth]
        7.    t_eff = min(DL_a, plt)
        8.    d_pm  = t_eff × b / hops(p)
        9.    IF (d_pm/D_u)×ec_p >= pre  → skip path
        10.   Augment flow d_pm along p ; update residual graph
        11.   D_a -= d_pm
        12. RETURN paths and data amounts
        ─────────────────────────────────────────────────────────
        """
        adj = self._build_residual(objective)
        remaining = data_volume
        paths_used: list[PathResult] = []
        total_cost = 0.0
        iterations = 0

        while remaining > 1e-9 and iterations < self._MAX_ITER:
            iterations += 1

            # ── Step 3: Dijkstra shortest path ──────────────────────────
            path, path_dist = self._dijkstra(adj, source, destination)
            if path is None:
                break   # no augmenting path → infeasible for remaining data

            # ── Step 4: path lifetime  plt = min(llt_ij) ────────────────
            plt = self._path_min_lifetime(adj, path)
            if plt <= 0:
                break

            # ── Step 5: path residual energy  pre = min(re_ij) ──────────
            pre = self._path_min_residual_energy(path)

            # ── Step 6: bottleneck bandwidth ─────────────────────────────
            bw   = self._path_bottleneck_bw(adj, path)
            hops = len(path) - 1
            if bw <= 0 or hops == 0:
                break

            # ── Step 7–8: effective time window and data estimate ────────
            t_eff  = min(deadline, plt)
            if t_eff <= 0:
                break
            d_path = (t_eff * bw) / hops

            # Clamp to residual capacity and remaining demand
            cap_bottleneck = self._path_min_capacity(adj, path)
            d_path = min(d_path, remaining, cap_bottleneck)
            if d_path < 1e-9:
                break

            # ── Step 9: energy feasibility check ────────────────────────
            ec_total = self._path_energy_cost(adj, path)
            energy_needed = (d_path / data_unit) * ec_total
            if energy_needed >= pre:
                # Insufficient node energy → block this path, try another
                self._block_path(adj, path)
                continue

            # ── Step 10: augment flow along path ────────────────────────
            actual_flow = self._augment(adj, path, d_path)

            # ── Accumulate results ───────────────────────────────────────
            path_cost = path_dist * actual_flow
            total_cost += path_cost
            paths_used.append(PathResult(
                nodes=list(path),
                data=actual_flow,
                lifetime=plt,
                bandwidth=bw,
                cost=path_cost,
            ))

            # ── Step 11: update remaining data ───────────────────────────
            remaining -= actual_flow

        # ── Evaluate outcome ─────────────────────────────────────────────
        routed       = data_volume - remaining
        deadline_met = remaining < 1e-9
        feasible     = deadline_met

        return RoutingResult(
            paths=paths_used,
            total_data_routed=routed,
            remaining_data=remaining,
            total_cost=total_cost,
            deadline_met=deadline_met,
            feasible=feasible,
            iterations=iterations,
        )

    # ─────────────────────────────────────────────────────────────────────
    # Residual graph construction
    # ─────────────────────────────────────────────────────────────────────

    def _build_residual(
        self, objective: str
    ) -> dict[int, list[_REdge]]:
        """
        Build adjacency list for the residual graph.

        Edge capacity = bandwidth × safe_lifetime  (total transferable volume).
        Cost = ttdu (latency/deadline objective) or ec (energy objective).
        Safe lifetime = llt_ij × (1 - SAFETY_MARGIN).
        """
        adj: dict[int, list[_REdge]] = defaultdict(list)

        for lnk in self.links:
            cost     = lnk.energy if objective == self.ENERGY else lnk.ttdu
            safe_lt  = lnk.lifetime * (1.0 - self._SAFETY)
            capacity = lnk.bandwidth * safe_lt          # volume in Mbps·s

            fwd_idx = len(adj[lnk.src])
            rev_idx = len(adj[lnk.dst])

            # Forward edge
            adj[lnk.src].append(_REdge(
                dst=lnk.dst, cap=capacity, cost=cost,
                lifetime=safe_lt, energy=lnk.energy,
                rev_idx=rev_idx, orig=lnk,
            ))
            # Reverse edge (zero initial capacity, negative cost for SSP)
            adj[lnk.dst].append(_REdge(
                dst=lnk.src, cap=0.0, cost=-cost,
                lifetime=safe_lt, energy=0.0,
                rev_idx=fwd_idx, orig=None,
            ))

        return adj

    # ─────────────────────────────────────────────────────────────────────
    # Dijkstra on residual graph
    # ─────────────────────────────────────────────────────────────────────

    def _dijkstra(
        self,
        adj: dict[int, list[_REdge]],
        src: int,
        dst: int,
    ) -> tuple[Optional[list[int]], float]:
        """
        Dijkstra shortest path on residual graph.
        Only traverses edges with positive capacity and positive lifetime.
        Back-flow edges use max(cost, 0) to stay non-negative for Dijkstra.
        """
        dist   = {src: 0.0}
        prev_n: dict[int, int]   = {}
        pq     = [(0.0, src)]

        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, math.inf):
                continue
            if u == dst:
                break
            for e in adj.get(u, []):
                if e.cap < 1e-9 or e.lifetime <= 0:
                    continue
                w  = max(e.cost, 0.0)   # Dijkstra requires non-negative weights
                nd = d + w
                if nd < dist.get(e.dst, math.inf):
                    dist[e.dst]  = nd
                    prev_n[e.dst] = u
                    heapq.heappush(pq, (nd, e.dst))

        if dst not in dist:
            return None, math.inf

        # Reconstruct node path
        path, cur = [], dst
        while cur != src:
            path.append(cur)
            cur = prev_n[cur]
        path.append(src)
        path.reverse()
        return path, dist[dst]

    # ─────────────────────────────────────────────────────────────────────
    # Path property helpers
    # ─────────────────────────────────────────────────────────────────────

    def _best_fwd_edge(
        self, adj: dict[int, list[_REdge]], u: int, v: int
    ) -> Optional[_REdge]:
        """First forward edge from u→v with positive residual capacity."""
        # Prefer original (forward) edges
        for e in adj.get(u, []):
            if e.dst == v and e.cap > 1e-9 and e.orig is not None:
                return e
        # Fallback to any edge (back-flow)
        for e in adj.get(u, []):
            if e.dst == v and e.cap > 1e-9:
                return e
        return None

    def _path_min_lifetime(self, adj, path) -> float:
        """plt = min(llt_ij) for all links in path (after safety margin)."""
        lt = math.inf
        for u, v in zip(path, path[1:]):
            e = self._best_fwd_edge(adj, u, v)
            if e:
                lt = min(lt, e.lifetime)
        return 0.0 if lt == math.inf else lt

    def _path_bottleneck_bw(self, adj, path) -> float:
        """b_path = min(b_ij) for all links in path."""
        bw = math.inf
        for u, v in zip(path, path[1:]):
            e = self._best_fwd_edge(adj, u, v)
            if e and e.orig:
                bw = min(bw, e.orig.bandwidth)
        return 0.0 if bw == math.inf else bw

    def _path_min_capacity(self, adj, path) -> float:
        """Bottleneck residual capacity along path."""
        cap = math.inf
        for u, v in zip(path, path[1:]):
            e = self._best_fwd_edge(adj, u, v)
            if e:
                cap = min(cap, e.cap)
        return 0.0 if cap == math.inf else cap

    def _path_min_residual_energy(self, path) -> float:
        """pre = min(re_ij) = min(min(re_i, re_j)) for links in path."""
        re = math.inf
        for u, v in zip(path, path[1:]):
            n_u = self.nodes.get(u)
            n_v = self.nodes.get(v)
            re_u = n_u.residual_energy if n_u else math.inf
            re_v = n_v.residual_energy if n_v else math.inf
            re   = min(re, re_u, re_v)
        return re if re != math.inf else 0.0

    def _path_energy_cost(self, adj, path) -> float:
        """Sum of ec_ij along path (energy cost per data unit)."""
        total = 0.0
        for u, v in zip(path, path[1:]):
            e = self._best_fwd_edge(adj, u, v)
            if e:
                total += e.energy
        return total

    # ─────────────────────────────────────────────────────────────────────
    # Flow augmentation
    # ─────────────────────────────────────────────────────────────────────

    def _augment(
        self, adj: dict[int, list[_REdge]], path: list[int], flow: float
    ) -> float:
        """
        Augment 'flow' units along path.
        Updates forward capacity (decrease) and reverse capacity (increase).
        Returns the actual flow augmented (clamped to bottleneck).
        """
        flow = min(flow, self._path_min_capacity(adj, path))
        for u, v in zip(path, path[1:]):
            for e in adj[u]:
                if e.dst == v and e.cap >= flow - 1e-9:
                    e.cap                  -= flow
                    adj[v][e.rev_idx].cap  += flow
                    break
        return flow

    def _block_path(
        self, adj: dict[int, list[_REdge]], path: list[int]
    ) -> None:
        """
        Mark first edge of this path as temporarily exhausted so Dijkstra
        finds a different augmenting path on the next iteration.
        """
        if len(path) >= 2:
            u, v = path[0], path[1]
            for e in adj[u]:
                if e.dst == v and e.cap > 1e-9:
                    e.cap = 0.0
                    break
