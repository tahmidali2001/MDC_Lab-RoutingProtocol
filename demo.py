"""
LL-MCMF Routing Protocol  –  Demo
===================================
Demonstrates the Link Lifetime-based Min-Cost Max-Flow routing protocol
on a sample 6-node multi-technology MANET (Wi-Fi + Bluetooth).

Network topology
----------------

           [WiFi 54Mbps, lt=40s]
     0 ─────────────────────────────► 3
     │                                │
     │ [BT 2Mbps, lt=60s]             │ [WiFi 54Mbps, lt=30s]
     ▼                                ▼
     1 ─────────────────────────────► 4 ──────────────────────► 5 (dest)
     │  [WiFi 11Mbps, lt=25s]         │  [WiFi 11Mbps, lt=50s]  ▲
     │                                │                          │
     │ [WiFi 54Mbps, lt=45s]          │ [BT  2Mbps,  lt=70s]    │
     ▼                                ▼                          │
     2 ─────────────────────────────► 3             0 ────────────
                                                      [WiFi 54Mbps, lt=20s]
     (also direct 0→5 low-lifetime link for testing deadline failure)

Source: node 0    Destination: node 5    Data: 100 DU   Deadline: 10 s
"""

from routing_protocol import LLMCMFRouter, Node, Link

# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def separator(title: str = "") -> None:
    width = 60
    if title:
        pad = (width - len(title) - 2) // 2
        print("\n" + "─" * pad + f" {title} " + "─" * pad)
    else:
        print("\n" + "─" * width)


# ─────────────────────────────────────────────────────────────────────────────
# Build the sample network
# ─────────────────────────────────────────────────────────────────────────────

def build_network() -> tuple[list[Node], list[Link]]:
    """
    6-node MANET: nodes 0..5
    Technology: Wi-Fi (54 Mbps / 11 Mbps) and Bluetooth (2 Mbps)

    Link parameters are illustrative values matching the variable definitions
    in the task document.
    """

    # ── Nodes ───────────────────────────────────────────────────────────────
    # Node(id, proc_speed[MIPS], proc_energy[J/ins], memory[MB], residual_energy[J])
    nodes = [
        Node(0, proc_speed=500e6,  proc_energy=1e-9, memory=512e6, residual_energy=5000),
        Node(1, proc_speed=300e6,  proc_energy=1e-9, memory=256e6, residual_energy=3000),
        Node(2, proc_speed=200e6,  proc_energy=1e-9, memory=128e6, residual_energy=2000),
        Node(3, proc_speed=400e6,  proc_energy=1e-9, memory=256e6, residual_energy=4000),
        Node(4, proc_speed=350e6,  proc_energy=1e-9, memory=256e6, residual_energy=3500),
        Node(5, proc_speed=600e6,  proc_energy=1e-9, memory=512e6, residual_energy=6000),
    ]

    # ── Links ────────────────────────────────────────────────────────────────
    # Link(src, dst, tech, bandwidth[Mbps], ttdu[s/DU], energy[J/DU], lifetime[s])
    #
    # ttdu  = D_u / bandwidth   (1 DU = 1 Mbit for simplicity)
    # energy = (P_tx / bandwidth) * D_u   (illustrative values)
    #
    links = [
        # ── Path 1: 0→3→5  (high bandwidth WiFi backbone) ──────────────────
        Link(0, 3, "wifi",      bandwidth=54.0,  ttdu=0.0185, energy=0.050, lifetime=40.0),
        Link(3, 5, "wifi",      bandwidth=54.0,  ttdu=0.0185, energy=0.050, lifetime=30.0),

        # ── Path 2: 0→1→4→5  (mixed WiFi) ──────────────────────────────────
        Link(0, 1, "bluetooth", bandwidth=2.0,   ttdu=0.5000, energy=0.020, lifetime=60.0),
        Link(1, 4, "wifi",      bandwidth=11.0,  ttdu=0.0909, energy=0.080, lifetime=25.0),
        Link(4, 5, "wifi",      bandwidth=11.0,  ttdu=0.0909, energy=0.080, lifetime=50.0),

        # ── Path 3: 0→1→2→3→5  (long path, stable Bluetooth legs) ──────────
        Link(1, 2, "wifi",      bandwidth=54.0,  ttdu=0.0185, energy=0.060, lifetime=45.0),
        Link(2, 3, "bluetooth", bandwidth=2.0,   ttdu=0.5000, energy=0.018, lifetime=55.0),
        # (reuses Link(3,5) above)

        # ── Path 4: 0→4→5  (direct high-bandwidth shortcut) ─────────────────
        Link(0, 4, "wifi",      bandwidth=54.0,  ttdu=0.0185, energy=0.055, lifetime=35.0),
        # (reuses Link(4,5) above)

        # ── Extra: 4→3 cross-link for richer routing options ─────────────────
        Link(4, 3, "bluetooth", bandwidth=2.0,   ttdu=0.5000, energy=0.022, lifetime=70.0),

        # ── Low-lifetime direct link 0→5 for deadline-failure demo ───────────
        Link(0, 5, "wifi",      bandwidth=54.0,  ttdu=0.0185, energy=0.040, lifetime=5.0),
    ]

    return nodes, links


# ─────────────────────────────────────────────────────────────────────────────
# Main demo
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    nodes, links = build_network()
    router = LLMCMFRouter(nodes=nodes, links=links)

    print("╔══════════════════════════════════════════════════════════╗")
    print("║   Link Lifetime-Based Min-Cost Max-Flow Routing Demo     ║")
    print("╠══════════════════════════════════════════════════════════╣")

    # Print network topology
    separator("Network Topology")
    print(f"  Nodes : {len(nodes)}")
    print(f"  Links : {len(links)}")
    print()
    print("  Nodes:")
    for n in nodes:
        print(f"    {n}")
    print()
    print("  Links:")
    for lnk in links:
        print(f"    {lnk}")

    # ── Scenario parameters ──────────────────────────────────────────────────
    SOURCE      = 0
    DESTINATION = 5
    DATA_VOLUME = 100.0    # D_a  – 100 data units
    DATA_UNIT   = 1.0      # D_u  – 1 Mbit per unit
    DEADLINE    = 10.0     # DL_a – 10 seconds

    # ════════════════════════════════════════════════════════════════════════
    # SCENARIO 1 – Minimise Latency (no deadline)
    # ════════════════════════════════════════════════════════════════════════
    separator("Scenario 1: Minimise Latency  (no deadline)")
    print(f"  Source={SOURCE}  Dest={DESTINATION}  "
          f"Data={DATA_VOLUME} DU  Deadline=None")
    result1 = router.route(
        data_volume=DATA_VOLUME,
        source=SOURCE,
        destination=DESTINATION,
        deadline=float("inf"),
        objective=LLMCMFRouter.LATENCY,
        data_unit=DATA_UNIT,
    )
    print(result1.summary())

    # ════════════════════════════════════════════════════════════════════════
    # SCENARIO 2 – Minimise Energy (no deadline)
    # ════════════════════════════════════════════════════════════════════════
    separator("Scenario 2: Minimise Energy  (no deadline)")
    print(f"  Source={SOURCE}  Dest={DESTINATION}  "
          f"Data={DATA_VOLUME} DU  Deadline=None")
    result2 = router.route(
        data_volume=DATA_VOLUME,
        source=SOURCE,
        destination=DESTINATION,
        deadline=float("inf"),
        objective=LLMCMFRouter.ENERGY,
        data_unit=DATA_UNIT,
    )
    print(result2.summary())

    # ════════════════════════════════════════════════════════════════════════
    # SCENARIO 3 – Meet Deadline  (DL_a = 10 s)
    # ════════════════════════════════════════════════════════════════════════
    separator(f"Scenario 3: Meet Deadline = {DEADLINE} s  (latency objective)")
    print(f"  Source={SOURCE}  Dest={DESTINATION}  "
          f"Data={DATA_VOLUME} DU  Deadline={DEADLINE} s")
    result3 = router.route(
        data_volume=DATA_VOLUME,
        source=SOURCE,
        destination=DESTINATION,
        deadline=DEADLINE,
        objective=LLMCMFRouter.DEADLINE,
        data_unit=DATA_UNIT,
    )
    print(result3.summary())

    # ════════════════════════════════════════════════════════════════════════
    # SCENARIO 4 – Very tight deadline (expected: infeasible / partial)
    # ════════════════════════════════════════════════════════════════════════
    TIGHT_DEADLINE = 1.0   # 1 second – intentionally hard to meet
    separator(f"Scenario 4: Very Tight Deadline = {TIGHT_DEADLINE} s")
    print(f"  Source={SOURCE}  Dest={DESTINATION}  "
          f"Data={DATA_VOLUME} DU  Deadline={TIGHT_DEADLINE} s")
    result4 = router.route(
        data_volume=DATA_VOLUME,
        source=SOURCE,
        destination=DESTINATION,
        deadline=TIGHT_DEADLINE,
        objective=LLMCMFRouter.DEADLINE,
        data_unit=DATA_UNIT,
    )
    print(result4.summary())

    # ════════════════════════════════════════════════════════════════════════
    # SCENARIO 5 – Small data, tight deadline (should succeed)
    # ════════════════════════════════════════════════════════════════════════
    SMALL_DATA = 5.0
    separator(f"Scenario 5: Small Data = {SMALL_DATA} DU, Deadline = {TIGHT_DEADLINE} s")
    print(f"  Source={SOURCE}  Dest={DESTINATION}  "
          f"Data={SMALL_DATA} DU  Deadline={TIGHT_DEADLINE} s")
    result5 = router.route(
        data_volume=SMALL_DATA,
        source=SOURCE,
        destination=DESTINATION,
        deadline=TIGHT_DEADLINE,
        objective=LLMCMFRouter.DEADLINE,
        data_unit=DATA_UNIT,
    )
    print(result5.summary())

    # ════════════════════════════════════════════════════════════════════════
    # Comparison Table
    # ════════════════════════════════════════════════════════════════════════
    separator("Scenario Comparison")
    print(f"  {'Scenario':<35s} {'Routed':>8s} {'Cost':>12s} {'Paths':>6s} {'OK?':>5s}")
    print(f"  {'─'*35} {'─'*8} {'─'*12} {'─'*6} {'─'*5}")
    rows = [
        ("1. Latency   (no deadline)",  result1),
        ("2. Energy    (no deadline)",  result2),
        (f"3. Deadline {DEADLINE}s      ",  result3),
        (f"4. Deadline {TIGHT_DEADLINE}s (tight)  ", result4),
        (f"5. Small {SMALL_DATA}DU deadline {TIGHT_DEADLINE}s", result5),
    ]
    for name, r in rows:
        ok = "✓" if r.feasible else "✗"
        print(f"  {name:<35s} {r.total_data_routed:>8.2f} "
              f"{r.total_cost:>12.4f} {len(r.paths):>6d} {ok:>5s}")
    print()


if __name__ == "__main__":
    main()
