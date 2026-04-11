# D.3 — Operator Console Hardware Standard
# The Cockpit | Team 2950 The Devastators
# Any student can set up the driver station identically in under 3 minutes.

---

## Goal

Every event, every practice, the driver station looks exactly the same. Same cable routing, same controller position, same velcro placement. The driver sits down and everything is where they expect it. Zero surprises.

---

## Physical Layout

```
                    ┌─ FIELD SIDE ─┐

    ┌───────────────────────────────────────────┐
    │                                           │
    │   ┌─────────────────────────────────┐     │
    │   │                                 │     │
    │   │         LAPTOP SCREEN           │     │
    │   │       (Shuffleboard open)       │     │
    │   │                                 │     │
    │   └─────────────────────────────────┘     │
    │                                           │
    │   ┌──────────┐  ┌─────┐  ┌──────────┐    │
    │   │ ETHERNET │  │POWER│  │   USB     │    │
    │   │  (left)  │  │(rear)│  │  (right) │    │
    │   └──────────┘  └─────┘  └──────────┘    │
    │                                           │
    │       CONTROLLER                          │
    │       (right of laptop)                   │
    │       ┌──────────────┐                    │
    │       │   Xbox / Pro │                    │
    │       └──────────────┘                    │
    │                                           │
    └───────────────── SHELF ───────────────────┘

                    ┌─ DRIVER SIDE ─┐
```

---

## Equipment List

| Item | Model | Quantity | Location |
|------|-------|----------|----------|
| Driver station laptop | Any (Windows, FRC DS installed) | 1 | Center of shelf |
| Primary controller | Xbox controller (wired or wireless + USB) | 1 | Right of laptop |
| Backup controller | Same model as primary | 1 | In tote, zip-tied cable |
| Ethernet cable | Cat6, 10ft | 1 | Left side of laptop |
| USB extension cable | USB-A, 6ft | 1 | Zip-tied to shelf for controller |
| Power cable | Laptop charger | 1 | Routed behind laptop |
| Velcro strips | 2" wide, industrial strength | 2 strips | Under laptop, on shelf |
| Controller mapping card | Laminated printout from D.1 | 1 | Taped to shelf surface |

---

## Setup Procedure (3 minutes)

### Step 1: Laptop (30 seconds)
1. Place laptop on center of shelf
2. Press down to engage velcro (loop on shelf, hook on laptop bottom)
3. Open the lid

### Step 2: Cables (60 seconds)
1. **Ethernet** — plug into the LEFT port on the laptop (labeled with tape)
   - Route cable behind the laptop, leave 6" slack loop
   - Plug other end into the field ethernet port
2. **Power** — plug laptop charger into field outlet
   - Route cable behind laptop, not across the shelf surface
3. **USB** — plug USB extension into the RIGHT port on the laptop
   - Extension cable is zip-tied to the shelf — it stays put

### Step 3: Controller (30 seconds)
1. Plug primary controller into the USB extension cable
2. Place controller to the right of the laptop
3. Verify controller shows as Port 0 in FRC Driver Station

### Step 4: Software (60 seconds)
1. Open FRC Driver Station — verify green lights for Comms and Robot Code
2. Open Shuffleboard — verify it loads `2950_match_layout.json` automatically
3. Verify camera feed appears in the main area
4. Select autonomous mode in the auto chooser
5. Verify battery voltage shows > 12.0V

### Step 5: Verify (15 seconds)
- [ ] Laptop secured with velcro
- [ ] Ethernet plugged into labeled port
- [ ] Power plugged in
- [ ] Controller on Port 0
- [ ] Shuffleboard showing match layout
- [ ] Auto mode selected
- [ ] Battery > 12V

**Done. Driver sits down.**

---

## Cable Routing Diagram

```
        ┌──────── SHELF (top view) ────────┐
        │                                   │
   ETH ─┤←─ LEFT PORT              ┌───┐   │
        │    (labeled               │USB│   ├─ USB extension
        │     with tape)            │ext│   │  (zip-tied to
        │                           └───┘   │   shelf rail)
        │    ┌───────────────┐              │
        │    │    LAPTOP     │              │
        │    │               │   CONTROLLER │
        │    └───────────────┘              │
        │          ↑                        │
        │        POWER                      │
        │    (routed BEHIND                 │
        │     laptop to outlet)             │
        └───────────────────────────────────┘

  All cables exit BEHIND the laptop.
  Nothing crosses the shelf surface in front of the laptop.
  The driver never touches a cable during a match.
```

---

## Failure Prevention

| Problem | Prevention | How |
|---------|-----------|-----|
| Laptop slides during hard defense | Velcro strips | 2" industrial velcro on shelf + laptop bottom |
| Ethernet pulled during match | Slack loop | Leave 6" of slack behind laptop, route along shelf edge |
| Controller disconnects mid-match | USB extension zip-tied to shelf | Controller plugs into extension, not directly into laptop |
| Wrong ethernet port | Label the port | Small piece of tape on the correct port: "ETH → FIELD" |
| Laptop dies mid-match | Always plugged in | Power cable is the first thing connected |
| Controller drift / stick drift | Pre-match calibration | Open DS → check joystick axes → recalibrate if needed |
| Backup controller not ready | Pre-staged in tote | Backup stays in tote lid, USB cable zip-tied and coiled |
| Dashboard layout wrong | Auto-load on startup | Shuffleboard → Preferences → Default Layout → `2950_match_layout.json` |

---

## Tote Contents

The driver station tote goes to every event and practice. It contains everything needed to set up the station from scratch.

| Item | Location in Tote |
|------|-----------------|
| Laptop + charger | Main compartment |
| Primary controller | Side pocket |
| Backup controller + cable | Lid pocket (zip-tied cable, coiled) |
| Ethernet cable (10ft) | Side pocket |
| USB extension cable (6ft) | Built into setup (stays on shelf if possible, spare in tote) |
| Velcro strips (spare) | Bottom of tote |
| Controller mapping card (laminated) | Lid pocket |
| Console setup photo guide (laminated) | Lid pocket |
| Small roll of electrical tape | Bottom of tote |
| Zip ties (spare) | Bottom of tote |

---

## Photo Guide Checklist

Take these 6 photos once the station is set up correctly. Print on a single sheet, laminate, and store in the tote lid.

1. **Full station from driver's perspective** — what the driver sees when they sit down
2. **Cable routing (top view)** — ethernet left, power behind, USB right
3. **Velcro placement** — underside of laptop + shelf surface
4. **Controller position** — right of laptop, plugged into USB extension
5. **Backup controller location** — in tote lid pocket, cable coiled
6. **View from behind** — what the drive coach sees (screen, cables, controller)

---

## Pre-Event Checklist

Run this the night before every event:

- [ ] Laptop charged and FRC Driver Station updated
- [ ] Shuffleboard layout file present (`2950_match_layout.json`)
- [ ] Primary controller tested (all buttons, no drift)
- [ ] Backup controller tested
- [ ] Ethernet cable inspected (no damaged ends)
- [ ] USB extension cable inspected
- [ ] Velcro on laptop bottom intact
- [ ] Controller mapping card in tote
- [ ] Photo guide in tote
- [ ] Tote packed with all items from contents list above

---

## Event Day: Between Matches

Between matches, the pit crew checks:
1. Battery voltage (swap if < 12.0V)
2. Controller cable still secure
3. Ethernet connection still solid
4. Run `PitCrewDiagnosticCommand` if any mechanism acted weird last match

The driver station should never need to be torn down between matches. If it does, any student can rebuild it from the photo guide in under 3 minutes.

---

*Last verified: April 8, 2026*
*Source: ARCH_DRIVER_STATION.md, Section D.3*
