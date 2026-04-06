# THE ENGINE — Parts Inventory System
# Codename: "The Vault"
# Target: Ready before January 2027 kickoff
# Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════

## The Problem

"We ran out of 10-32 bolts on day 15."
"Who ordered the bearing blocks? Nobody?"
"We bought 8 SPARK MAXes but we already had 4 in the closet."

The Vault solves this with a simple inventory database that knows what
you own, what the CAD Pipeline says you need, and what the gap is.

---

## How It Works

```
OFFSEASON — Walk the shop, count everything, enter into The Vault
KICKOFF — CAD Pipeline BOM minus Vault inventory = Order List
BUILD — Log parts as they are pulled from inventory
PRE-EVENT — Cross-reference wear data + failure logs = Restock List
POST-EVENT — Log what was consumed, auto-generate next restock
```

---

## Inventory Categories

### Cat 1: Electronics (high value, exact count)
| Item | Min Stock | Source | Est. Cost |
|------|-----------|--------|-----------|
| SPARK MAX | 2 spare | REV | $90 |
| Kraken X60 | 1 spare | CTRE/WCP | $60 |
| NEO Brushless | 2 spare | REV | $50 |
| NEO 550 | 1 spare | REV | $35 |
| Through-bore encoder | 2 spare | REV | $30 |
| Magnetic encoder | 2 spare | Thrifty | $15 |
| Ethernet switch | 1 spare | Amazon | $20 |

### Cat 2: Structural (measured, bulk)
| Item | Min Stock | Est. Cost |
|------|-----------|-----------|
| 2x1x0.0625 Al tube | 10 ft | $2.75/ft |
| 1x1x0.0625 Al tube | 6 ft | $1.50/ft |
| 1/8" Al plate | 4 sq ft | $8/sqft |
| 1/4" polycarbonate | 4 sq ft | $6/sqft |
| 3/8" hex shaft | 4 ft | $5/ft |
| 1/2" hex shaft | 4 ft | $5/ft |
| 3D printer filament PETG | 1 kg | $25/kg |

### Cat 3: Fasteners (bulk, cheap but critical)
| Item | Min Stock | Est. Cost |
|------|-----------|-----------|
| 10-32 x 0.5" SHCS | 100 | $8/100 |
| 10-32 Nylock nut | 100 | $6/100 |
| 1/4-20 x 0.75" SHCS | 50 | $10/50 |
| Rivets 3/16" Al | 100 | $5/100 |
| Zip ties small | 100 | $5/100 |

### Cat 4: Transmission
| Item | Min Stock | Est. Cost |
|------|-----------|-----------|
| 15mm HTD5 belt (various) | 2 spare | $15-25 |
| #25 chain | 3 ft | $3/ft |
| #25 master links | 10 | $1 each |
| MaxPlanetary stages | 2 spare | $20/stage |
| Bearing 1/2" hex | 4 spare | $5 |

### Cat 5: Electrical Consumables
| Item | Min Stock | Est. Cost |
|------|-----------|-----------|
| Wago inline connectors | 20 | $15/50 |
| Lever nuts 2-port | 20 | $12/25 |
| Ring terminals 10 AWG | 20 | $8/50 |
| 40A breakers | 4 spare | $8 each |
| 30A breakers | 4 spare | $8 each |
| Anderson SB50 | 2 spare | $5 each |
| Electrical tape | 2 rolls | $3/roll |
| Heat shrink kit | 1 | $10/kit |

### Cat 6: Batteries
| Item | Min Stock | Notes |
|------|-----------|-------|
| FRC battery (MK ES17-12) | 4 total | Retire after 2 seasons |
| Battery strap (metal) | 2 spare | Never use velcro |

---

## The Cross-Reference Engine

On kickoff day:
```
CAD Pipeline BOM:  "Need 12 SPARK MAXes"
The Vault:         "Own 8 SPARK MAXes"
Output:            "ORDER 4 SPARK MAXes — $360 — REV Robotics"
```

Before each event:
```
Wear Tracking:     "Elevator at 847 cycles, inspect belt at 1000"
Robot Reports:     "Used 2 Wagos, 1 breaker at last event"
The Vault:         "18 Wagos remaining, 3 breakers remaining"
Output:            "Pack spare belt (ORDER), reprint 2 brackets"
```

---

## Implementation: Google Sheet

| Tab | Contents |
|-----|----------|
| Inventory | All items: category, count, min stock, bin location |
| BOM Import | Paste CSV from CAD Pipeline, auto-cross-references |
| Order List | =BOM minus Inventory, with vendor links and costs |
| Usage Log | Date, item, quantity used, reason |
| Event Restock | Auto-generated from usage + wear data |
| Audit History | Dated snapshots for consumption rate tracking |

No code needed. Formulas handle cross-referencing. One student
manages this in 10 minutes per meeting.

---

## Bin Organization

| Label | Contents |
|-------|----------|
| E-01 to E-12 | Electronics (controllers, motors, sensors) |
| S-01 to S-08 | Structural (tubes, plates, shaft stock) |
| F-01 to F-10 | Fasteners (bolts by size, nuts, rivets) |
| T-01 to T-08 | Transmission (belts, chain, bearings) |
| C-01 to C-10 | Consumables (Wagos, terminals, tape) |
| B-01 to B-04 | Batteries (numbered by age) |

Print labels with item name AND Vault code. Any student finds and
restocks parts without asking.

---

## Audit Procedure

Full Audit (2x/year: May + December):
Walk shop, count every bin, update counts, flag below-minimum items,
discard damaged items. 2-3 hours with 3-4 students.

Quick Check (before each event):
Print restock list, verify packed, check Brownout Kit (E.6),
check batteries. 30 minutes with 1-2 students.

---

## Development Roadmap

| Block | Task | Hours |
|-------|------|-------|
| V.1 | Create inventory template (Google Sheet) | 4 |
| V.2 | Full shop audit — populate initial inventory | 4 |
| V.3 | BOM cross-reference formulas | 4 |
| **Total** | | **12** |

---

## Integration Map

```
The Blueprint (CAD Pipeline) ──→ BOM ──→ Vault cross-reference
The Vault ──────────────────────→ The Clock (CL.3 Parts Tracker)
The Vault ──────────────────────→ The Grid (E.6 Brownout Kit)
The Pit Crew (P.4 Wear) ───────→ Vault (spare parts list)
The Pit Crew (P.1 Reports) ────→ Vault (consumption logging)
```

---

*Architecture document — The Vault | THE ENGINE | Team 2950 The Devastators*
