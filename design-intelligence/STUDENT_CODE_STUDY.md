# Student Robot Code — Study List

**Purpose:** Curated list of robot-code-layer repos worth students reading for the FRC 2950 robot code. These are **NOT Engine ports** — The Engine operates above the robot code layer (prediction, scouting, pit ops, vision). These repos are training material for the students who *do* write the robot code.

**Use this list for:** code reviews during build season, student training modules, reference implementations when 2950 hits a problem these teams already solved.

**Do NOT use this list for:** Engine workstream ports. Language (Java/Kotlin/C++) and layer (robot code) mismatch makes integration cost prohibitive.

---

## Tier 1 — Championship-quality robot code (most valuable study)

| Team | Repo | Why students should read it |
|---|---|---|
| **971** Spartan Robotics | [frc971/971-Robot-Code](https://github.com/frc971/971-Robot-Code) | 69★. Most sophisticated FRC codebase publicly available. AOS distributed middleware, LQR/DARE state-space control, CUDA AprilTags, Bazel build. Overkill for 2950 but sets the ceiling for what FRC code *can* be. |
| **4096** Ctrl-Z | [CtrlZ-FRC4096](https://github.com/CtrlZ-FRC4096) | Only Python/robotpy Einstein winner. VSCode live execution tracer, coroutine command framework, remote REPL into running robot, **PIDD2 controller**. Relevant if 2950 students prefer Python. |
| **1323** MadTown | [Team1323](https://github.com/Team1323) | 3x Einstein winner. Swerve code 2017-2019 is considered canonical. Code quality high. |
| **125** NUTRONs | [gitlab.com/nutrons125](https://gitlab.com/nutrons125) | Championship code NU22/NU23/NU25 public. GitLab (not GitHub). |
| **1678** Citrus Circuits | C2024-Public, C2025-Public | Mechanism patterns. Regression + shooting math. Already studied for scouting — worth studying for robot code too. |
| **254** Cheesy Poofs | 2024-Public, etc. | The reference point for FRC code quality. Students should read at least one year of their robot code. |

## Tier 2 — Well-structured, approachable robot code

| Team | Repo | Why students should read it |
|---|---|---|
| **1690** Orbit | Their robot code repos | Swerve + mechanism patterns. Open source annually. |
| **3061** Huskie Robotics | [3061-lib](https://github.com/HuskieRobotics/3061-lib) | 32★. Reusable Java FRC library — good structural reference. |
| **2471** Mean Machine | [meanlib](https://github.com/TeamMeanMachine/meanlib) | 20★. Kotlin FRC library. Interesting if students want Kotlin. |
| **217** ThunderChickens | [FRC-217-Libraries](https://github.com/Team217/FRC-217-Libraries) | **GeometricProfiler** — sinusoidal motion profiles with [Desmos viz](https://www.desmos.com/calculator/qqevqwzzzu). Good introduction to motion profile math for students. |
| **4522** Team SCREAM | [SCREAMLib](https://github.com/TeamSCREAMRobotics/SCREAMLib) | Proper WPILib vendor library with **2-joint IK solver**, projectile trajectory with air resistance. Strong mechanism math reference. |
| **862** Lightning Robotics | LightningLib | Java library. Reference. |
| **2590** Nemesis | NomadLib | Java library. Reference. |
| **1477** Texas Torque | [TorqueLib](https://github.com/TexasTorque) | Texas team, similar district. Reasonable reference point. |
| **5406** Celt-X | PurpleLib | Small well-structured lib. |

## Tier 3 — Reference-only (look when you hit a specific problem)

| Team | Repo | When to reference |
|---|---|---|
| 2910 | Robot code | Oracle validation ground truth — also worth student read for mechanism patterns |
| 4481 Rembrandts | Robot code + LED controller | LED controller is a nice small read |
| 6672 Fusion Corps | ballistic-simulator (C++/Python/Java + LaTeX paper) | If building shooter in 2027 |
| 4272 Maverick | DefenseSwerve | If 2950 decides to build a defensive robot |
| 6328 | Robot code | Reference for certain subsystem patterns |
| 461 Westside Boiler | Robot code | Reference only |
| 2718 Tiger Robotics | Robot code | Reference only |
| 2539 Krypton Cougars | Robot code | Reference only |
| 5940 BREAD | Robot code | Reference only |
| 195 CyberKnights | Robot code | Reference only |
| 3310 Black Hawks | Robot code | Reference only |
| 4481 Rembrandts | Robot code | Reference only |
| 294 Beach Cities | Robot code | Reference only |
| 1619 Up-A-Creek | Robot code | Reference only |
| 4414 HighTide | Robot code | 4x Einstein finalist, minimal public code |

## Hardware repos (study for 2950 electrical/fabrication students)

| Team | Repo | What |
|---|---|---|
| **4788** CurtinFRC | CAN-over-RJ45 | Custom PCB KiCad: CANbus+power+DIO over RJ45 |
| **4272** Maverick | MAVcoder PCB | Custom shaft encoder in KiCad |
| **321** RoboLancers | Helios | Orange Pi 5 + ArduCam custom vision hardware, PCB |
| **6672** Fusion Corps | lidar (Rust) | GPU-accelerated LiDAR localization |

---

## What belongs in The Engine (not here)

These teams' non-robot-code work (scouting systems, pit tools, vision pipelines, analytics) lives in the `ENGINE_AUDIT_2026-04-13.md` and `LANDSCAPE_SCAN_254_BINNER_2026-04-12.md` — those are the Engine-level adoption targets.

This doc is only for **robot-code-layer study material**.

---

*Created 2026-04-13 to separate student training references from Engine ports after the Blueprint postmortem clarified the layer distinction.*
