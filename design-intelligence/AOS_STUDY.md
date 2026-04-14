# AOS Study Guide: Team 971's Autonomous Operating System

**Purpose:** This guide introduces FRC Team 2950 students to Team 971's AOS middleware, a best-in-class example of distributed robotics software architecture. Reading 971's code teaches how to design systems that scale beyond single-robot control, even if we don't adopt AOS ourselves.

---

## What AOS Is

Team 971 built **AOS (Autonomous Operating System)** as a distributed messaging middleware that sits between their coprocessors and roboRIO. Instead of direct function calls, all robot components communicate via timestamped messages published to **channels**—like a pub-sub system built on shared memory and network protocols. A node (e.g., a vision coprocessor, gripper controller, or drive module) publishes messages to a channel; other nodes subscribe to those channels and react asynchronously.

This architecture lets 971 run multiple specialized coprocessors (CV, motion planning, kinematics, LQR controllers) independently while keeping them time-synchronized. Each coprocessor runs its own event loop and logs every message it sends and receives.

---

## Why It Matters

**Determinism & Replay:** Every message has a timestamp. 971 can replay any match from logs, byte-for-byte, because the messaging order and timing are recorded. This is transformative for debugging crashes and understanding what a robot actually did.

**Multi-Language Support:** AOS works across C++, Rust, and Python, letting teams use the right language for each job. Vision code in Python, core motion control in C++, and utilities in Rust can all communicate seamlessly because messages are serialized via Flatbuffers—a language-agnostic format.

**Realtime Separation:** Not all code needs realtime priority. AOS explicitly separates high-priority loops (drive, sensors) from general computing (logging, visualization). This prevents a slow Python script from blocking a control loop.

**Crash Recovery:** If one coprocessor dies, others keep running. Messages backed by disk logs allow the robot to resume intelligently.

---

## Key Concepts to Learn

**Event Loops:** Each process runs its own event loop that wakes when messages arrive on subscribed channels. This is the foundation of responsive, non-blocking architecture.

**Channels & Topics:** A channel is like a UDP topic; multiple publishers can write to the same channel, and multiple subscribers can listen. Flatbuffers schemas define the message structure.

**Timestamped Messages:** Every message carries a microsecond timestamp assigned by the publish side. This enables perfect replay and time-synchronization across network-connected nodes.

**Realtime Priorities:** Driver code runs at high OS priority; telemetry and analysis run at normal priority. AOS handles this split explicitly.

**Log Replay as Testing:** Recorded logs are a first-class test asset. A test replays a match log and compares the control outputs—no hardware, no randomness, reproducible behavior every time.

---

## What to Read in 971's Repository

Start here: https://github.com/frc971/971-Robot-Code

- **`aos/README.md`** — Overview of the system, how to visualize nodes with `aos_graph_nodes`, and how to dump messages with `aos_dump`.
- **`aos/events/README.md`** — The ping/pong example walks through how two processes communicate via channels and event loops.
- **`aos/logging/`** — Study `logging.h` and `interface.h` to see how messages are recorded and accessed. Look at `dynamic_logging.cc` for how logging is initialized.
- **`aos/network/`** — Check `message_bridge_client_lib.cc` and `message_bridge_server_lib.cc` to see how messages are sent over the network to remote coprocessors. SCTP is used for reliable, ordered delivery.
- **`aos/flatbuffers/`** — See how Flatbuffers schemas define message types. This is the contract between publishers and subscribers.
- **`aos/time/`** — Understand how 971 synchronizes time across multiple nodes; the filter implementations show advanced realtime practices.

The repository also contains complete robots from multiple years. Pick a recent year's robot code and trace how vision, motion control, and the main loop all talk via AOS channels.

---

## What NOT to Adopt

AOS assumes a team with five or more coprocessors, custom LQR controllers, and a Bazel build system. 2950 currently runs a single roboRIO plus maybe one Pi for vision. Porting AOS would add months of infrastructure work for zero near-term benefit.

Additionally, AOS is tightly coupled to 971's hardware (Cortex drives, specific camera pinouts, their gripper design). The middleware is portable; their robot code is not.

---

## Translation to 2950's Stack

Team 2950 today uses a simpler model: roboRIO + optional coprocessors, serial or network comms for I/O. Here's how AOS concepts map:

- **Channels** ↔ 2950's command-response CLI with topic names (e.g., `/drive/setpoint`). The principle is the same: loosely coupled message passing.
- **Event Loops** ↔ The prediction engine's scheduler and the scout live-draft ticker. Both run non-blocking loops that wake on external events.
- **Timestamped Replay** ↔ 2950's match logs store human scout observations with timestamps. Replaying could replay decision logic, though we don't yet.
- **Realtime Separation** ↔ The live scout commands run on a Discord bot (low priority); the matching engine runs separately (not on the robot).

**Bottom line:** Rather than adopting AOS wholesale, 2950 should study *why* 971 built it, then apply those principles at our scale. Deterministic logging and replay are worth borrowing; shipping five coprocessors is not.

---

## Further Learning

After reading AOS, compare it to other FRC middleware: WPILib's Shuffleboard (for telemetry), AdvantageKit (modern equivalent), and teams like 6328 Mechanical Advantage who adopted similar patterns. This teaches you to recognize architectural tradeoffs across the ecosystem.

Study 971's robot code from 2019–2023 to see AOS in action: how the vision code publishes targets, how the motion planner subscribes to them, and how logs reveal the truth when things go wrong.
