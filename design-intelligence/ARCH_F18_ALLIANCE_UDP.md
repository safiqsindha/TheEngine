# F.18 Architecture: Alliance UDP Communication Protocol
# Status: Architecture only — build during alliance selection at Worlds playoffs

## What It Does

Shares robot pose, intended target, and cycle phase between the 3 alliance robots
during a match so they don't drive to the same game piece.

## Legality (Verified Against 2026 Game Manual)

| Rule | Requirement | Compliance |
|------|------------|------------|
| R704 | Use ports from Table 8-5 only | UDP 5800 (team-use port) |
| R706 | All signals through ARENA network | Yes — FMS Ethernet only |
| R707 | No custom wireless | Yes — wired DS bridge, no radios |
| E301 | No 802.11 in venue | Yes — wired Ethernet between DSs |
| R904 | Operator console fits on shelf | Ethernet switch + 2 cables fit in 60in |

## Network Topology

Robots cannot talk directly. Must relay through driver stations:

```
Robot 1 (roboRIO)                          Robot 2 (roboRIO)
    │ UDP 5800                                  │ UDP 5800
    │ (FMS wireless)                            │ (FMS wireless)
    ▼                                           ▼
Driver Station 1                          Driver Station 2
    │                                           │
    └──── Ethernet switch on shelf ─────────────┘
              │
         Driver Station 3
              │
              ▼
         Robot 3 (roboRIO)
```

## Message Schema

Each robot publishes one packet at 10 Hz (every 100ms) on UDP port 5800.
Total payload: 41 bytes per robot. Well under bandwidth limits.

```
Alliance Coordination Message v1.0
Offset  Type      Field
──────  ────      ─────
0       uint8     protocol_version (1)
1       uint16    team_number
3       uint8     sequence_number (wraps at 255)
4       float32   robot_x (field meters)
8       float32   robot_y (field meters)
12      float32   robot_heading (radians)
16      float32   robot_speed (m/s)
20      uint8     action_type (0=IDLE, 1=SCORING, 2=COLLECTING, 3=CLIMBING, 4=DEFENDING)
21      float32   target_x (field meters, 0 if no target)
25      float32   target_y (field meters, 0 if no target)
29      float32   target_utility (decision engine score)
33      uint8     fuel_held (0-8)
34      uint8     cycle_phase (0=IDLE, 1=SEEKING, 2=CARRYING, 3=SCORING)
35      float32   match_time_remaining (seconds)
39      uint8     flags (bit 0: needs_help, bit 1: stalled, bit 2: climbing)
40      uint8     checksum (XOR of bytes 0-39)
```

## Integration with Decision Engine

When alliance data is available, AutonomousStrategy adds a penalty for targets
claimed by partners:

```java
// In evaluateTargets(), for each COLLECT target:
for (AllianceRobotState partner : alliancePartners) {
    if (partner.actionType == COLLECTING) {
        double distToPartnerTarget = fuelPos.getDistance(partner.targetPos);
        if (distToPartnerTarget < 1.0) {
            // Partner is already going for this fuel — heavy penalty
            utility -= 15.0;  // Enough to push it below any unclaimed fuel
        }
    }
}
```

This is a ~10-line addition to the existing strategy engine. The robot works
identically without alliance data — the penalty just doesn't apply.

## Bridge Application

A small standalone app (Python or Java) that runs on each driver station laptop:

```
alliance_bridge.py
├── Listens on UDP 5800 from its own robot (localhost)
├── Forwards received packets to all other DSs on the Ethernet switch
├── Receives packets from other DSs
└── Forwards them to its own robot on UDP 5800
```

~100 lines of Python. Partners download it, run `python3 alliance_bridge.py 2950`,
done.

## Deployment Checklist (Night Before Elims)

- [ ] All 3 alliance teams install alliance_bridge.py on their DS laptop
- [ ] Bring a small 4-port Ethernet switch + 3 short Ethernet cables
- [ ] Connect all 3 DS laptops to the switch (in addition to normal FMS connection)
- [ ] Each team runs: `python3 alliance_bridge.py <team_number>`
- [ ] Verify in practice match: all 3 robots see each other's poses on AdvantageScope
- [ ] If any issues: unplug the switch, robots revert to independent operation

## Graceful Degradation

- **0 partners connected**: Robot operates normally. No penalty applied.
- **1 partner connected**: Deconflicts with that partner only.
- **2 partners connected**: Full alliance coordination.
- **Packet loss**: Stale data older than 500ms is discarded. Robot reverts to
  independent targeting for that partner.
- **Bridge crashes**: Robot never depends on alliance data. It's purely additive.

## What to Build When

| Step | When | Time | Deliverable |
|------|------|------|------------|
| 1. This architecture doc | Now — done | — | Design reference |
| 2. Message schema + serializer | Alliance selection night | 2 hrs | Java class + Python encoder |
| 3. Bridge app | Alliance selection night | 1 hr | alliance_bridge.py |
| 4. Strategy engine integration | Alliance selection night | 30 min | 10 lines in AutonomousStrategy |
| 5. Test in practice match | Before first elim match | 15 min | Visual verification in AScope |
