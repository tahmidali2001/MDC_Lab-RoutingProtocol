"""
LL-MCMF Routing Protocol  –  Demo 2
=====================================
Extended 10-node multi-technology MANET (Wi-Fi + Bluetooth).
NO direct link between source (0) and destination (9).

Design goal
-----------
Link lifetimes are deliberately tuned so that each path has a limited
transferable capacity (bandwidth × safe_lifetime), forcing the SSP
algorithm to exhaust one physical path and then discover a new one.
This showcases genuine multi-path routing across diverse topologies.

Path capacities (capacity = bottleneck bw × bottleneck safe_lt)
---------------------------------------------------------------
  P1 : 0→1→5→9          — bottleneck 1→5 (WiFi 11Mbps, lt=12s) → ~112 DU
  P2 : 0→2→5→9          — bottleneck 2→5 (WiFi 54Mbps, lt=3s)  → ~138 DU
  P3 : 0→1→3→6→9        — bottleneck 1→3 (BT   2Mbps, lt=40s)  →  ~68 DU (shared)
  P4 : 0→2→4→7→9        — bottleneck 2→4 (WiFi 11Mbps, lt=12s) → ~112 DU
  P5 : 0→1→3→7→9        — bottleneck 1→3 (BT   2Mbps, lt=40s)  →  ~68 DU (shared)
  P6 : 0→2→4→6→9        — bottleneck 4→6 (BT   2Mbps, lt=40s)  →  ~68 DU
  P7 : 0→2→4→8→9        — bottleneck 2→4 (WiFi 11Mbps, lt=12s) → ~112 DU (shared)
  P8 : 0→1→5→8→9        — bottleneck 1→5 (WiFi 11Mbps, lt=12s) → ~112 DU (shared)
  P9 : 0→2→5→6→9        — bottleneck 2→5 (WiFi 54Mbps, lt=3s)  → ~138 DU (shared)
  P10: 0→1→3→7→8→9      — bottleneck 1→3 (BT   2Mbps, lt=40s)  →  ~68 DU (shared)

  Shared-link constraint: 1→5 (112 DU) is shared by P1 and P8 → P1 wins (cheaper).
                          2→4 (112 DU) is shared by P4 and P7 → P4 wins (cheaper).
                          1→3  (68 DU) shared by P3, P5, P10  → P5 wins (cheapest).
                          2→5 (138 DU) shared by P2 and P9.

  Total deliverable (latency objective):
    P2  138 DU  +  P1  112 DU  +  P4  112 DU  +  P5/P3  68 DU  ≈  430 DU

Network topology (directed, 0 → 9, no direct link)
----------------------------------------------------

      0 ──[WiFi54, lt=45s]──► 1 ──[WiFi11, lt=12s]──► 5 ──[WiFi54, lt=25s]──► 9
      │                       │                        │                        ▲
      │                       │[BT2, lt=40s]           │[WiFi11, lt=12s]        │
      │                       ▼                        ▼                        │
      │                       3 ──[WiFi11,lt=25s]──► 6 ──[BT2, lt=40s]────────►│
      │                       │                        ^                        │
      │                       │[WiFi54, lt=20s]        │                        │
      │                       ▼                        │[BT2, lt=40s]           │
      └──[WiFi54, lt=45s]──► 2 ──[WiFi54, lt=3s]──► 5 │                        │
                              │                        │                        │
                              └──[WiFi11, lt=12s]──► 4 ─────────────────────────┤
                                                     │  [WiFi54, lt=20s]──► 7 ──┤[WiFi11, lt=25s]
                                                     │  [WiFi11, lt=15s]──► 8 ──┘[WiFi54, lt=25s]

Source: node 0    Destination: node 9    (no direct 0→9 link)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from routing_protocol import LLMCMFRouter, Node, Link


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def separator(title: str = "") -> None:
    width = 68
    if title:
        inner = f" {title} "
        pad_l = (width - len(inner)) // 2
        pad_r = width - len(inner) - pad_l
        print("\n" + "─" * pad_l + inner + "─" * pad_r)
    else:
        print("\n" + "─" * width)


# ─────────────────────────────────────────────────────────────────────────────
# Build the network
# ─────────────────────────────────────────────────────────────────────────────

def build_network() -> tuple[list[Node], list[Link]]:
    """
    10-node MANET: nodes 0..9.
    Source = 0,  Destination = 9.
    NO direct 0→9 link — all traffic must traverse ≥ 3 hops.

    Link lifetime tuning
    ─────────────────────
    First-hop links (0→1, 0→2) have large lifetime → not bottlenecks.
    Exit links (5→9, 7→9, 8→9)  have large lifetime → not bottlenecks.
    Middle links are deliberately short-lived to create per-path capacity
    limits, so the SSP algorithm must switch to new physical paths as each
    saturates.

      Bottleneck link   Tech         BW       lt    safe_lt   cap (DU)
      ───────────────   ─────────    ─────    ───   ───────   ────────
      2→5               WiFi 54M    54 Mbps   3 s    2.55 s    ~138
      1→5               WiFi 11M    11 Mbps  12 s   10.20 s    ~112
      2→4               WiFi 11M    11 Mbps  12 s   10.20 s    ~112
      1→3 (BT)          Bluetooth    2 Mbps  40 s   34.00 s     ~68

    Node parameters: Node(id, proc_speed, proc_energy, memory, residual_energy)
    Link parameters: Link(src, dst, tech, bandwidth[Mbps], ttdu[s/DU], energy[J/DU], lifetime[s])
      ttdu   = 1 / bandwidth_Mbps    (1 DU = 1 Mbit)
      energy = P_tx / bandwidth_Mbps (J/DU, illustrative)
        WiFi 54 Mbps: P_tx ≈ 1.0 W → energy ≈ 0.0185 J/DU
        WiFi 11 Mbps: P_tx ≈ 1.0 W → energy ≈ 0.0909 J/DU
        Bluetooth 2M: P_tx ≈ 0.05W → energy ≈ 0.0250 J/DU  ← cheapest per DU
    """

    # ── Nodes ────────────────────────────────────────────────────────────────
    nodes = [
        Node(0, proc_speed=600e6, proc_energy=1e-9, memory=512e6, residual_energy=8000),   # source
        Node(1, proc_speed=400e6, proc_energy=1e-9, memory=256e6, residual_energy=4000),   # relay
        Node(2, proc_speed=500e6, proc_energy=1e-9, memory=256e6, residual_energy=5000),   # relay
        Node(3, proc_speed=200e6, proc_energy=1e-9, memory=128e6, residual_energy=2500),   # relay, low energy
        Node(4, proc_speed=450e6, proc_energy=1e-9, memory=256e6, residual_energy=4500),   # relay
        Node(5, proc_speed=350e6, proc_energy=1e-9, memory=256e6, residual_energy=3500),   # hub
        Node(6, proc_speed=150e6, proc_energy=1e-9, memory=128e6, residual_energy=1800),   # relay, low energy
        Node(7, proc_speed=500e6, proc_energy=1e-9, memory=256e6, residual_energy=5500),   # relay
        Node(8, proc_speed=400e6, proc_energy=1e-9, memory=256e6, residual_energy=4000),   # relay
        Node(9, proc_speed=700e6, proc_energy=1e-9, memory=512e6, residual_energy=9000),   # destination
    ]

    # ── Links ────────────────────────────────────────────────────────────────
    #
    # IMPORTANT: 2→5 has lt=3s  → its safe capacity ≈ 138 DU  (P2/P9 bottleneck)
    #            1→5 has lt=12s → its safe capacity ≈ 112 DU  (P1/P8 bottleneck)
    #            2→4 has lt=12s → its safe capacity ≈ 112 DU  (P4/P7 bottleneck)
    #            1→3 has lt=40s → its safe capacity ≈  68 DU  (BT path bottleneck)
    #
    links = [
        # ── First-hop links from source 0  (large capacity, not bottlenecks) ─
        Link(0, 1, "wifi",      bandwidth=54.0, ttdu=0.0185, energy=0.0185, lifetime=45.0),
        Link(0, 2, "wifi",      bandwidth=54.0, ttdu=0.0185, energy=0.0185, lifetime=45.0),

        # ── Relay links from node 1 ─────────────────────────────────────────
        Link(1, 3, "bluetooth", bandwidth=2.0,  ttdu=0.5000, energy=0.0250, lifetime=40.0),  # BT, long-lived
        Link(1, 5, "wifi",      bandwidth=11.0, ttdu=0.0909, energy=0.0909, lifetime=12.0),  # ← BOTTLENECK ~112 DU

        # ── Relay links from node 2 ─────────────────────────────────────────
        Link(2, 4, "wifi",      bandwidth=11.0, ttdu=0.0909, energy=0.0909, lifetime=12.0),  # ← BOTTLENECK ~112 DU
        Link(2, 5, "wifi",      bandwidth=54.0, ttdu=0.0185, energy=0.0185, lifetime=3.0),   # ← BOTTLENECK ~138 DU (short-lived)

        # ── Relay links from node 3 ─────────────────────────────────────────
        Link(3, 6, "wifi",      bandwidth=11.0, ttdu=0.0909, energy=0.0909, lifetime=25.0),
        Link(3, 7, "wifi",      bandwidth=54.0, ttdu=0.0185, energy=0.0185, lifetime=20.0),

        # ── Relay links from node 4 ─────────────────────────────────────────
        Link(4, 6, "bluetooth", bandwidth=2.0,  ttdu=0.5000, energy=0.0250, lifetime=40.0),  # BT, long-lived
        Link(4, 7, "wifi",      bandwidth=54.0, ttdu=0.0185, energy=0.0185, lifetime=20.0),
        Link(4, 8, "wifi",      bandwidth=11.0, ttdu=0.0909, energy=0.0909, lifetime=15.0),

        # ── Relay links from node 5 ─────────────────────────────────────────
        Link(5, 6, "wifi",      bandwidth=54.0, ttdu=0.0185, energy=0.0185, lifetime=10.0),
        Link(5, 8, "wifi",      bandwidth=11.0, ttdu=0.0909, energy=0.0909, lifetime=12.0),
        Link(5, 9, "wifi",      bandwidth=54.0, ttdu=0.0185, energy=0.0185, lifetime=25.0),  # exit via 5, large cap

        # ── Relay links from node 6 ─────────────────────────────────────────
        Link(6, 9, "bluetooth", bandwidth=2.0,  ttdu=0.5000, energy=0.0250, lifetime=40.0),  # BT exit

        # ── Relay links from node 7 ─────────────────────────────────────────
        Link(7, 8, "wifi",      bandwidth=54.0, ttdu=0.0185, energy=0.0185, lifetime=20.0),
        Link(7, 9, "wifi",      bandwidth=11.0, ttdu=0.0909, energy=0.0909, lifetime=25.0),  # exit via 7

        # ── Relay links from node 8 ─────────────────────────────────────────
        Link(8, 9, "wifi",      bandwidth=54.0, ttdu=0.0185, energy=0.0185, lifetime=25.0),  # exit via 8, large cap
    ]

    return nodes, links


# ─────────────────────────────────────────────────────────────────────────────
# Print network summary
# ─────────────────────────────────────────────────────────────────────────────

def print_topology(nodes: list[Node], links: list[Link]) -> None:
    separator("Network Topology")
    print(f"  Nodes : {len(nodes)}")
    print(f"  Links : {len(links)}")
    print(f"  Source: node 0   Destination: node 9   (NO direct 0→9 link)")
    print()
    print("  Nodes:")
    for n in nodes:
        print(f"    {n}")
    print()
    print("  Links:")
    for lnk in links:
        print(f"    {lnk}")
    print()

    # Annotate each known path with estimated capacity
    separator("Known paths 0 → 9  with estimated capacity")
    print("  Path      Route                   Bottleneck link     ~Cap (DU)")
    print("  ────────  ──────────────────────  ──────────────────  ─────────")
    paths_info = [
        ("P1",  "0→1→5→9       (3 hops)", "1→5  WiFi 11Mbps lt=12s", "~112"),
        ("P2",  "0→2→5→9       (3 hops)", "2→5  WiFi 54Mbps lt= 3s", "~138"),
        ("P3",  "0→1→3→6→9     (4 hops)", "1→3  BT    2Mbps lt=40s", " ~68 (shared 1→3)"),
        ("P4",  "0→2→4→7→9     (4 hops)", "2→4  WiFi 11Mbps lt=12s", "~112"),
        ("P5",  "0→1→3→7→9     (4 hops)", "1→3  BT    2Mbps lt=40s", " ~68 (shared 1→3)"),
        ("P6",  "0→2→4→6→9     (4 hops)", "4→6  BT    2Mbps lt=40s", " ~68"),
        ("P7",  "0→2→4→8→9     (4 hops)", "2→4  WiFi 11Mbps lt=12s", "~112 (shared 2→4)"),
        ("P8",  "0→1→5→8→9     (4 hops)", "1→5  WiFi 11Mbps lt=12s", "~112 (shared 1→5)"),
        ("P9",  "0→2→5→6→9     (4 hops)", "2→5  WiFi 54Mbps lt= 3s", "~138 (shared 2→5)"),
        ("P10", "0→1→3→7→8→9   (5 hops)", "1→3  BT    2Mbps lt=40s", " ~68 (shared 1→3)"),
    ]
    for pid, route, bottleneck, cap in paths_info:
        print(f"  {pid:<8}  {route:<22}  {bottleneck:<18}  {cap}")
    print()
    print("  SSP path-selection order (latency objective, cheapest ttdu first):")
    print("    P2 (ttdu=0.0555) → P1 (ttdu=0.1279) → P4 (ttdu=0.2188)")
    print("    → P5 (ttdu=0.6279, BT hop)  after P1/P2/P4 saturate")
    print()
    print("  SSP path-selection order (energy objective, cheapest ec first):")
    print("    P2 (ec=0.0555) → P1 (ec=0.1279) → P5 (ec=0.1529, BT cheap!)")
    print("    → P4 (ec=0.2188)   [P5 beats P4 because BT ec < WiFi11 ec]")


# ─────────────────────────────────────────────────────────────────────────────
# Main demo
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    nodes, links = build_network()
    router = LLMCMFRouter(nodes=nodes, links=links)

    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║   LL-MCMF Routing Demo 2 — Rich 10-Node Topology (No Direct Link) ║")
    print("╚════════════════════════════════════════════════════════════════════╝")

    print_topology(nodes, links)

    SOURCE      = 0
    DESTINATION = 9
    DATA_UNIT   = 1.0     # D_u – 1 Mbit per data unit

    # Network total deliverable capacity ≈ 430 DU (see module docstring)
    DATA_300  = 300.0     # fully achievable across 3–4 distinct paths
    DATA_500  = 500.0     # exceeds total capacity → partial delivery expected

    # ════════════════════════════════════════════════════════════════════════
    # SCENARIO 1 – Minimise Latency, no deadline, 300 DU
    #
    #  Expected path sequence (SSP picks lowest ttdu first):
    #    Iter 1–4  : P2 (0→2→5→9) — saturates 2→5 at ~138 DU
    #    Iter 5–7  : P1 (0→1→5→9) — saturates 1→5 at ~112 DU
    #    Iter 8+   : P4 (0→2→4→7→9) — routes remaining ~50 DU
    #  Result: 3 distinct physical paths, ~10 augmentation steps
    # ════════════════════════════════════════════════════════════════════════
    separator("Scenario 1: Minimise Latency  (no deadline, 300 DU)")
    print(f"  Source={SOURCE}  Dest={DESTINATION}  Data={DATA_300} DU  Deadline=None")
    print("  Expected: P2 saturates → switches to P1 → switches to P4")
    result1 = router.route(
        data_volume=DATA_300,
        source=SOURCE,
        destination=DESTINATION,
        deadline=float("inf"),
        objective=LLMCMFRouter.LATENCY,
        data_unit=DATA_UNIT,
    )
    print(result1.summary())

    # ════════════════════════════════════════════════════════════════════════
    # SCENARIO 2 – Minimise Energy, no deadline, 300 DU
    #
    #  Energy costs per DU:
    #    WiFi 54Mbps → 0.0185 J/DU   WiFi 11Mbps → 0.0909 J/DU
    #    BT   2Mbps  → 0.0250 J/DU   (BT is cheaper than WiFi 11Mbps!)
    #
    #  Expected path sequence (SSP picks lowest energy first):
    #    P2 (ec=0.0555) → P1 (ec=0.1279) → P5 (ec=0.1529, BT hop 1→3)
    #    P5 beats P4 (ec=0.2188) because BT ec (0.025) < WiFi11 ec (0.091)
    #  Contrast with Scenario 1 where P4 came before P5.
    # ════════════════════════════════════════════════════════════════════════
    separator("Scenario 2: Minimise Energy  (no deadline, 300 DU)")
    print(f"  Source={SOURCE}  Dest={DESTINATION}  Data={DATA_300} DU  Deadline=None")
    print("  Expected: P2 → P1 → P5 (BT path, cheap energy) — P4 avoided")
    result2 = router.route(
        data_volume=DATA_300,
        source=SOURCE,
        destination=DESTINATION,
        deadline=float("inf"),
        objective=LLMCMFRouter.ENERGY,
        data_unit=DATA_UNIT,
    )
    print(result2.summary())

    # ════════════════════════════════════════════════════════════════════════
    # SCENARIO 3 – Comfortable deadline = 15 s, latency objective, 300 DU
    #
    #  For each path, t_eff = min(deadline, path_safe_lifetime):
    #    P2: plt_safe = min(38.25, 2.55, 21.25) = 2.55s  →  t_eff = min(15, 2.55) = 2.55s
    #    P1: plt_safe = min(38.25, 10.20, 21.25) = 10.20s →  t_eff = min(15, 10.20) = 10.20s
    #    P4: plt_safe = min(38.25, 10.20, 17.00, 21.25) = 10.20s → t_eff = 10.20s
    #
    #  Deadline (15s) > all path safe-lifetimes → same path order as Scenario 1
    #  but slightly more flow per iteration for P1/P4 (deadline doesn't bind).
    # ════════════════════════════════════════════════════════════════════════
    DEADLINE_COMFORTABLE = 15.0
    separator(f"Scenario 3: Latency + Deadline={DEADLINE_COMFORTABLE}s  (300 DU)")
    print(f"  Source={SOURCE}  Dest={DESTINATION}  Data={DATA_300} DU  Deadline={DEADLINE_COMFORTABLE} s")
    print("  Expected: feasible; deadline does not bind (plt_safe < deadline)")
    result3 = router.route(
        data_volume=DATA_300,
        source=SOURCE,
        destination=DESTINATION,
        deadline=DEADLINE_COMFORTABLE,
        objective=LLMCMFRouter.DEADLINE,
        data_unit=DATA_UNIT,
    )
    print(result3.summary())

    # ════════════════════════════════════════════════════════════════════════
    # SCENARIO 4 – Tight deadline = 2 s, latency objective, 300 DU
    #
    #  t_eff is now capped at 2s for ALL paths, drastically reducing per-
    #  iteration flow:
    #    P2: d_path = (2s × 54Mbps) / 3 hops = 36 DU/iter  (vs 45.9 no-deadline)
    #    P1: d_path = (2s × 11Mbps) / 3 hops =  7.3 DU/iter (vs 37.4 no-deadline)
    #    P4: d_path = (2s × 11Mbps) / 4 hops =  5.5 DU/iter
    #
    #  More iterations needed → more path entries in output, same 3 physical paths.
    #  Demonstrates how tight deadlines create finer-grained augmentation steps.
    # ════════════════════════════════════════════════════════════════════════
    DEADLINE_TIGHT = 2.0
    separator(f"Scenario 4: Tight Deadline={DEADLINE_TIGHT}s  (300 DU)")
    print(f"  Source={SOURCE}  Dest={DESTINATION}  Data={DATA_300} DU  Deadline={DEADLINE_TIGHT} s")
    print("  Expected: same 3 paths but many more augmentation steps (t_eff=2s caps flow/iter)")
    result4 = router.route(
        data_volume=DATA_300,
        source=SOURCE,
        destination=DESTINATION,
        deadline=DEADLINE_TIGHT,
        objective=LLMCMFRouter.DEADLINE,
        data_unit=DATA_UNIT,
    )
    print(result4.summary())

    # ════════════════════════════════════════════════════════════════════════
    # SCENARIO 5 – Exceeds network capacity: 500 DU, no deadline
    #
    #  Total network capacity (latency objective, shared-link analysis):
    #    P2  via 2→5 (138 DU) + P1 via 1→5 (112 DU)
    #    + P4 via 2→4 (112 DU) + P5 via 1→3 ( 68 DU)
    #    ≈ 430 DU  <  500 DU  →  infeasible (partial delivery)
    #
    #  Algorithm exhausts all WiFi paths then BT paths, reports infeasibility.
    # ════════════════════════════════════════════════════════════════════════
    separator(f"Scenario 5: Exceeds capacity  (500 DU, no deadline)")
    print(f"  Source={SOURCE}  Dest={DESTINATION}  Data={DATA_500} DU  Deadline=None")
    print(f"  Expected: INFEASIBLE — network max ~430 DU < 500 DU demand")
    print(f"  All paths exhausted: P2→P1→P4→P5→... no more augmenting paths")
    result5 = router.route(
        data_volume=DATA_500,
        source=SOURCE,
        destination=DESTINATION,
        deadline=float("inf"),
        objective=LLMCMFRouter.LATENCY,
        data_unit=DATA_UNIT,
    )
    print(result5.summary())
    if not result5.feasible:
        print(f"  [!] {result5.remaining_data:.1f} DU could NOT be delivered — network capacity exhausted")

    # ════════════════════════════════════════════════════════════════════════
    # SCENARIO 6 – Energy objective, moderate deadline = 12 s, 200 DU
    #
    #  With energy objective, P5 (BT path via 1→3) ranks before P4:
    #    ec(P5) = 0.0185+0.025+0.0185+0.0909 = 0.1529 J/DU
    #    ec(P4) = 0.0185+0.0909+0.0185+0.0909 = 0.2188 J/DU
    #  Deadline = 12s > plt_safe of P2 (2.55s) and P1/P4 (10.2s)
    #  → deadline binds lightly; energy objective still routes via BT paths
    # ════════════════════════════════════════════════════════════════════════
    DEADLINE_MOD = 12.0
    DATA_200 = 200.0
    separator(f"Scenario 6: Minimise Energy + Deadline={DEADLINE_MOD}s  (200 DU)")
    print(f"  Source={SOURCE}  Dest={DESTINATION}  Data={DATA_200} DU  Deadline={DEADLINE_MOD} s")
    print("  Expected: P2 (WiFi54) → P1 (WiFi11) → P5 (BT, cheap energy) before P4")
    result6 = router.route(
        data_volume=DATA_200,
        source=SOURCE,
        destination=DESTINATION,
        deadline=DEADLINE_MOD,
        objective=LLMCMFRouter.ENERGY,
        data_unit=DATA_UNIT,
    )
    print(result6.summary())

    # ════════════════════════════════════════════════════════════════════════
    # Comparison Table
    # ════════════════════════════════════════════════════════════════════════
    separator("Scenario Comparison")
    print(f"  {'Scenario':<46s} {'Demand':>7} {'Routed':>8} {'Cost':>10} {'Iter':>5} {'OK?':>4}")
    print(f"  {'─'*46} {'─'*7} {'─'*8} {'─'*10} {'─'*5} {'─'*4}")
    rows = [
        ("1. Latency   no deadline         300 DU",  DATA_300, result1),
        ("2. Energy    no deadline         300 DU",  DATA_300, result2),
        (f"3. Latency + Deadline {DEADLINE_COMFORTABLE}s        300 DU",  DATA_300, result3),
        (f"4. Latency + Deadline {DEADLINE_TIGHT}s (tight)  300 DU",  DATA_300, result4),
        ("5. Latency   no deadline         500 DU",  DATA_500, result5),
        (f"6. Energy  + Deadline {DEADLINE_MOD}s        200 DU",  DATA_200, result6),
    ]
    for name, demand, r in rows:
        ok = "✓" if r.feasible else "✗"
        print(f"  {name:<46s} {demand:>7.0f} {r.total_data_routed:>8.1f} "
              f"{r.total_cost:>10.3f} {r.iterations:>5d} {ok:>4s}")
    print()

    # Quick path-diversity summary
    separator("Path Diversity Summary")
    print("  Scenario   Distinct physical paths observed")
    print("  ─────────  ─────────────────────────────────────────────────────")
    all_results = [result1, result2, result3, result4, result5, result6]
    labels = ["Sc.1 (Lat)", "Sc.2 (Ene)", "Sc.3 (DL15)", "Sc.4 (DL2)", "Sc.5 (500DU)", "Sc.6 (E+DL)"]
    for lbl, res in zip(labels, all_results):
        seen = {}
        for p in res.paths:
            key = "→".join(str(n) for n in p.nodes)
            seen[key] = seen.get(key, 0) + p.data
        paths_str = "  |  ".join(f"[{k}]={v:.0f}DU" for k, v in seen.items())
        print(f"  {lbl:<12} {paths_str}")
    print()


if __name__ == "__main__":
    main()
