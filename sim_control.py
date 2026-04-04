#!/usr/bin/env python3
"""
HALSim WebSocket control script for simulation verification.
Connects to the WPILib simulation WebSocket server (port 3300) and provides
programmatic control of DriverStation state, joystick inputs, and data reading.

Usage:
    python3 sim_control.py <command> [args...]

Commands:
    status              - Print current sim state
    drive_test          - Drive forward briefly to verify swerve motion
    auto_test           - Run autonomous mode for 15 seconds
    button_test         - Test all driver button bindings
    full_verify         - Run complete verification sequence
    vision_test         - Inject fake botpose/detections via NT4
    led_timing_test     - Verify LED transitions and timing params
"""

import json
import sys
import time
import threading
import websocket

WS_URL = "ws://localhost:3300/wpilibws"

# Received state from the robot
robot_state = {}
state_lock = threading.Lock()


def on_message(ws, message):
    try:
        msg = json.loads(message)
        device_type = msg.get("type", "")
        device = msg.get("device", "")
        data = msg.get("data", {})
        key = f"{device_type}/{device}"
        with state_lock:
            if key not in robot_state:
                robot_state[key] = {}
            robot_state[key].update(data)
    except json.JSONDecodeError:
        pass


def on_error(ws, error):
    print(f"WebSocket error: {error}")


def on_close(ws, close_status_code, close_msg):
    pass


def on_open(ws):
    print("Connected to HALSim WebSocket")


def send_msg(ws, msg_type, device, data):
    ws.send(json.dumps({"type": msg_type, "device": device, "data": data}))


def send_ds(ws, enabled=True, autonomous=False, test=False, estop=False, match_time=135.0):
    """Send DriverStation state update."""
    send_msg(ws, "DriverStation", "", {
        ">enabled": enabled,
        ">autonomous": autonomous,
        ">test": test,
        ">estop": estop,
        ">fms_attached": False,
        ">ds_attached": True,
        ">new_data": True,
        ">match_time": match_time,
    })


def send_joystick(ws, port=0, axes=None, buttons=0, povs=None):
    """Send joystick data. Xbox controller has 6 axes, up to 12 buttons."""
    if axes is None:
        axes = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    if povs is None:
        povs = [-1]
    # Buttons as a list of booleans (12 buttons for Xbox)
    button_list = []
    for i in range(12):
        button_list.append(bool(buttons & (1 << i)))
    send_msg(ws, "Joystick", str(port), {
        ">axes": axes,
        ">buttons": button_list,
        ">povs": povs,
    })


def tick(ws, port=0, axes=None, buttons=0):
    """Send one simulation tick: joystick data + new_data flag."""
    send_joystick(ws, port=port, axes=axes, buttons=buttons)
    send_joystick(ws, port=1)  # Operator stick (empty)
    send_msg(ws, "DriverStation", "", {">new_data": True})


def connect():
    ws = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    wst = threading.Thread(target=ws.run_forever, daemon=True)
    wst.start()
    time.sleep(1)
    return ws


def wait_ticking(ws, seconds, axes=None, buttons=0):
    """Keep sending ticks for the given duration."""
    start = time.time()
    while time.time() - start < seconds:
        tick(ws, axes=axes, buttons=buttons)
        time.sleep(0.02)


def cmd_status():
    ws = connect()
    time.sleep(1.5)
    with state_lock:
        # Show just DriverStation and Joystick
        for key in sorted(robot_state.keys()):
            if "DriverStation" in key or "Joystick/0" in key:
                print(f"\n{key}:")
                for k, v in sorted(robot_state[key].items()):
                    print(f"  {k}: {v}")
    ws.close()


def cmd_drive_test():
    """Drive robot forward for 3 seconds, verify pose changes via console."""
    print("=" * 60)
    print("VERIFY #3: Swerve Motion — Drive forward test")
    print("=" * 60)
    ws = connect()

    # Initialize both joysticks
    send_joystick(ws, port=0)
    send_joystick(ws, port=1)

    # Enable teleop
    print("[1] Enabling teleop...")
    send_ds(ws, enabled=True, autonomous=False)
    wait_ticking(ws, 0.5)

    # Record initial state
    print("[2] Driving forward (left stick Y = -0.5) for 3 seconds...")
    # Xbox: axis 0=leftX, axis 1=leftY, axis 2=leftTrigger, axis 3=rightTrigger, axis 4=rightX, axis 5=rightY
    # DriveCommand typically uses: leftY=forward, leftX=strafe, rightX=rotation
    forward_axes = [0.0, -0.5, 0.0, 0.0, 0.0, 0.0]
    wait_ticking(ws, 3.0, axes=forward_axes)

    print("[3] Stopping...")
    wait_ticking(ws, 1.0)

    print("[4] Disabling...")
    send_ds(ws, enabled=False)
    wait_ticking(ws, 0.5)

    print("RESULT: Check OutlineViewer Drive/Pose — should have moved from origin.")
    print("        Check Drive/SimGroundTruth for physics ground truth position.")
    time.sleep(1)
    ws.close()


def cmd_auto_test():
    """Run autonomous mode for 15 seconds."""
    print("=" * 60)
    print("VERIFY #4: Autonomous / Choreo Trajectory Following")
    print("=" * 60)
    ws = connect()

    send_joystick(ws, port=0)
    send_joystick(ws, port=1)

    # Disable first for clean state
    print("[1] Disabling for clean auto init...")
    send_ds(ws, enabled=False)
    wait_ticking(ws, 1.0)

    # Enable auto
    print("[2] Enabling AUTONOMOUS mode...")
    send_ds(ws, enabled=True, autonomous=True, match_time=15.0)

    print("[3] Running auto for 15 seconds...")
    start = time.time()
    while time.time() - start < 15.0:
        tick(ws)
        time.sleep(0.02)
        elapsed = time.time() - start
        if int(elapsed * 50) % 50 == 0 and int(elapsed) % 3 == 0:
            print(f"     {elapsed:.1f}s elapsed...")

    print("[4] Disabling...")
    send_ds(ws, enabled=False)
    wait_ticking(ws, 0.5)

    print("RESULT: Check OutlineViewer for:")
    print("  - Drive/Pose should show trajectory path")
    print("  - Choreo Alerts should be empty (no errors)")
    print("  - Superstructure/State may have changed during auto")
    time.sleep(1)
    ws.close()


def cmd_button_test():
    """Test each button binding."""
    print("=" * 60)
    print("VERIFY #5: Button Bindings")
    print("=" * 60)
    ws = connect()

    send_joystick(ws, port=0)
    send_joystick(ws, port=1)

    # Enable teleop
    send_ds(ws, enabled=True, autonomous=False)
    wait_ticking(ws, 0.5)

    # Xbox buttons: A=0, B=1, X=2, Y=3, LB=4, RB=5, Back=6, Start=7
    buttons = [
        (1 << 0, "A (Intake)"),
        (1 << 1, "B (Score)"),
        (1 << 2, "X"),
        (1 << 3, "Y"),
        (1 << 4, "LB"),
        (1 << 5, "RB"),
        (1 << 6, "Back"),
        (1 << 7, "Start (Practice Reset)"),
    ]

    for bitmask, name in buttons:
        print(f"  Pressing {name}...")
        # Press for 0.5s
        wait_ticking(ws, 0.5, buttons=bitmask)
        # Release for 0.5s
        wait_ticking(ws, 0.5, buttons=0)

    print("\n[Done] Check Superstructure/State for state transitions:")
    print("  - A press should trigger INTAKING")
    print("  - B press should trigger SCORING")
    print("  - Start press should reset DriverPracticeMode pose")

    send_ds(ws, enabled=False)
    wait_ticking(ws, 0.3)
    time.sleep(1)
    ws.close()


def cmd_full_verify():
    """Run complete verification sequence."""
    print("=" * 60)
    print("FULL SIMULATION VERIFICATION SEQUENCE")
    print("=" * 60)
    ws = connect()

    send_joystick(ws, port=0)
    send_joystick(ws, port=1)

    # ── Step 1: Verify teleop drive ──
    print("\n[STEP 1/5] Teleop Drive — verify swerve motion")
    send_ds(ws, enabled=True, autonomous=False)
    wait_ticking(ws, 0.5)

    print("  Driving forward 3s...")
    wait_ticking(ws, 3.0, axes=[0.0, -0.5, 0.0, 0.0, 0.0, 0.0])
    print("  Stopping 1s...")
    wait_ticking(ws, 1.0)

    print("  Strafing right 2s...")
    wait_ticking(ws, 2.0, axes=[0.5, 0.0, 0.0, 0.0, 0.0, 0.0])
    print("  Stopping 1s...")
    wait_ticking(ws, 1.0)

    print("  Rotating 2s...")
    wait_ticking(ws, 2.0, axes=[0.0, 0.0, 0.0, 0.0, 0.5, 0.0])
    print("  Stopping 1s...")
    wait_ticking(ws, 1.0)

    # ── Step 2: Button bindings ──
    print("\n[STEP 2/5] Button Bindings")
    # A button = intake
    print("  A button (Intake trigger)...")
    wait_ticking(ws, 1.0, buttons=(1 << 0))
    wait_ticking(ws, 0.5)

    # B button = score
    print("  B button (Score trigger)...")
    wait_ticking(ws, 1.0, buttons=(1 << 1))
    wait_ticking(ws, 0.5)

    # RB = climb
    print("  RB button (Climb trigger)...")
    wait_ticking(ws, 1.0, buttons=(1 << 5))
    wait_ticking(ws, 0.5)

    # Start = practice reset
    print("  Start button (Practice reset)...")
    wait_ticking(ws, 0.5, buttons=(1 << 7))
    wait_ticking(ws, 0.5)

    # ── Step 3: Disable and switch to auto ──
    print("\n[STEP 3/5] Autonomous Mode")
    send_ds(ws, enabled=False)
    wait_ticking(ws, 1.0)

    print("  Enabling auto for 15s...")
    send_ds(ws, enabled=True, autonomous=True, match_time=15.0)
    start = time.time()
    while time.time() - start < 15.0:
        tick(ws)
        time.sleep(0.02)
        elapsed = time.time() - start
        if int(elapsed) > int(elapsed - 0.02) and int(elapsed) % 5 == 0:
            print(f"    {int(elapsed)}s...")

    # ── Step 4: Back to teleop ──
    print("\n[STEP 4/5] Return to Teleop")
    send_ds(ws, enabled=False)
    wait_ticking(ws, 0.5)
    send_ds(ws, enabled=True, autonomous=False)
    wait_ticking(ws, 2.0)

    # ── Step 5: Field-relative drive with rotation ──
    print("\n[STEP 5/5] Field-Relative Drive (rotated)")
    print("  Rotating 90 degrees...")
    wait_ticking(ws, 2.0, axes=[0.0, 0.0, 0.0, 0.0, 0.8, 0.0])
    wait_ticking(ws, 0.5)
    print("  Driving 'forward' (should move field-relative, not robot-relative)...")
    wait_ticking(ws, 2.0, axes=[0.0, -0.5, 0.0, 0.0, 0.0, 0.0])
    wait_ticking(ws, 1.0)

    # ── Cleanup ──
    print("\n[DONE] Disabling...")
    send_ds(ws, enabled=False)
    wait_ticking(ws, 0.5)

    print("\n" + "=" * 60)
    print("VERIFICATION COMPLETE — Check OutlineViewer for:")
    print("  Drive/Pose: should show movement in multiple directions")
    print("  Drive/GyroYaw: should be non-zero after rotation")
    print("  Superstructure/State: should have cycled through states")
    print("  Vision/HasTarget: false (no injected botpose)")
    print("  Intake/WheelCurrentAmps: may show sim current during intake")
    print("  LEDs/*: should show animation transitions")
    print("=" * 60)
    time.sleep(1)
    ws.close()


def cmd_vision_test():
    """Inject fake botpose via NT4 and verify VisionSubsystem accepts it."""
    import ntcore

    print("=" * 60)
    print("VERIFY: Vision Pipeline — Inject fake botpose via NT4")
    print("=" * 60)

    # Connect HALSim WebSocket (for DS control)
    ws = connect()
    send_joystick(ws, port=0)
    send_joystick(ws, port=1)

    # Connect NT4 (for vision data injection + reading outputs)
    nt = ntcore.NetworkTableInstance.getDefault()
    nt.setServer("127.0.0.1", 5810)
    nt.startClient4("vision_test")
    time.sleep(2)
    print(f"  NT4 connected: {nt.isConnected()}")
    if not nt.isConnected():
        print("ERROR: Could not connect to NT4 server")
        ws.close()
        return

    ll_table = nt.getTable("limelight")
    botpose_pub = ll_table.getDoubleArrayTopic("botpose_orb_wpiblue").publish()
    llpython_pub = ll_table.getDoubleArrayTopic("llpython").publish()

    # Enable teleop so periodic() runs
    print("\n[1] Enabling teleop...")
    send_ds(ws, enabled=True, autonomous=False)
    wait_ticking(ws, 1.0)

    # ── Test A: Valid botpose near robot's initial pose (2.0, 4.0) ──
    print("\n[2] Injecting VALID botpose (x=2.1, y=4.0, 2 tags, 20ms latency)...")
    valid_botpose = [2.1, 4.0, 0.0, 0.0, 0.0, 5.0, 20.0, 2.0, 2.0, 2.0, 5.0]
    for i in range(50):  # Send for 1 second (50 ticks * 20ms)
        botpose_pub.set(valid_botpose)
        nt.flush()
        tick(ws)
        time.sleep(0.02)

    print("  Waiting 1s for VisionSubsystem to process...")
    for i in range(50):
        botpose_pub.set(valid_botpose)
        nt.flush()
        tick(ws)
        time.sleep(0.02)

    # Read Vision/ outputs
    vision_table = nt.getTable("SmartDashboard")  # AKit logs to root NT
    # AdvantageKit logs go to NT as /Drive/Pose etc — check topics
    topics = nt.getTopicInfo()
    vision_topics = [t.name for t in topics if "Vision" in t.name or "vision" in t.name.lower()]
    print(f"  Vision-related NT topics: {vision_topics}")
    all_topics = [t.name for t in topics]
    print(f"  Total topics visible: {len(all_topics)}")
    if len(all_topics) <= 5:
        for t in all_topics:
            print(f"    {t}")

    # ── Test B: Invalid botpose (too far from odometry) ──
    print("\n[3] Injecting INVALID botpose (x=10.0, y=4.0 — >1m from odometry)...")
    invalid_botpose = [10.0, 4.0, 0.0, 0.0, 0.0, 0.0, 20.0, 2.0, 2.0, 2.0, 5.0]
    for i in range(25):
        botpose_pub.set(invalid_botpose)
        nt.flush()
        tick(ws)
        time.sleep(0.02)

    # ── Test C: Invalid botpose (out of field bounds) ──
    print("\n[4] Injecting INVALID botpose (x=-1.0 — out of field bounds)...")
    oob_botpose = [-1.0, 4.0, 0.0, 0.0, 0.0, 0.0, 20.0, 2.0, 2.0, 2.0, 5.0]
    for i in range(25):
        botpose_pub.set(oob_botpose)
        nt.flush()
        tick(ws)
        time.sleep(0.02)

    # ── Test D: Inject fuel + opponent detections ──
    print("\n[5] Injecting fuel + opponent detections via llpython...")
    # Format: [numFuel, fx1, fy1, fConf1, ..., numOpponents, ox1, oy1, oConf1, ...]
    llpython_data = [
        1.0, 3.0, 3.5, 0.95,  # 1 fuel at (3.0, 3.5) with 95% confidence
        1.0, 5.0, 6.0, 0.88,  # 1 opponent at (5.0, 6.0) with 88% confidence
    ]
    # Need 3 consecutive frames for fuel detection persistence gate
    print("  Sending 4 seconds of detections (fuel needs 3 frames)...")
    for i in range(200):  # 4 seconds
        llpython_pub.set(llpython_data)
        botpose_pub.set(valid_botpose)  # keep valid pose too
        nt.flush()
        tick(ws)
        time.sleep(0.02)

    # ── Test E: Clear detections ──
    print("\n[6] Clearing all detections...")
    botpose_pub.set([0.0] * 11)  # zeros = invalid (0 tags)
    llpython_pub.set([0.0])  # empty detections
    nt.flush()
    wait_ticking(ws, 0.5)

    # ── Cleanup ──
    print("\n[7] Disabling...")
    send_ds(ws, enabled=False)
    wait_ticking(ws, 0.5)

    botpose_pub.close()
    llpython_pub.close()
    nt.stopClient()
    ws.close()

    print("\n" + "=" * 60)
    print("VISION TEST COMPLETE")
    print("Check console output and OutlineViewer for:")
    print("  Vision/HasTarget — should be true during step 2, false during 3-4")
    print("  Vision/BotPose — should show (2.1, 4.0) during step 2")
    print("  Vision/FuelDetectionCount — should be 1 after step 5")
    print("  Vision/OpponentDetectionCount — should be 1 during step 5")
    print("  Vision/RejectedDistM — should appear during step 3")
    print("=" * 60)


def cmd_led_timing_test():
    """Verify LED log transitions and timing parameters."""
    import ntcore

    print("=" * 60)
    print("VERIFY: LED Transitions + Timing Parameters")
    print("=" * 60)

    ws = connect()
    send_joystick(ws, port=0)
    send_joystick(ws, port=1)

    nt = ntcore.NetworkTableInstance.getDefault()
    nt.setServer("127.0.0.1", 5810)
    nt.startClient4("led_timing_test")
    time.sleep(2)
    print(f"  NT4 connected: {nt.isConnected()}")

    ll_table = nt.getTable("limelight")
    botpose_pub = ll_table.getDoubleArrayTopic("botpose_orb_wpiblue").publish()

    # ── Phase 1: Disabled → LED should show disabled animation ──
    print("\n[1] Robot DISABLED — checking LED idle state...")
    send_ds(ws, enabled=False)
    wait_ticking(ws, 2.0)

    # ── Phase 2: Enable teleop → LED should transition ──
    print("\n[2] Enabling TELEOP — LED should transition to teleop animation...")
    send_ds(ws, enabled=True, autonomous=False)
    wait_ticking(ws, 2.0)

    # ── Phase 3: Press A (intake) → LED should show intake animation ──
    print("\n[3] Pressing A button (intake request)...")
    wait_ticking(ws, 2.0, buttons=(1 << 0))
    wait_ticking(ws, 1.0)  # release

    # ── Phase 4: Press B (score) → LED should show scoring animation ──
    print("\n[4] Pressing B button (score request)...")
    wait_ticking(ws, 2.0, buttons=(1 << 1))
    wait_ticking(ws, 1.0)

    # ── Phase 5: Switch to auto → LED + timing test ──
    print("\n[5] Switching to AUTONOMOUS — testing re-eval timing...")
    send_ds(ws, enabled=False)
    wait_ticking(ws, 1.0)
    send_ds(ws, enabled=True, autonomous=True, match_time=15.0)

    # Inject vision data during auto to test 0.25s vision gate
    valid_botpose = [2.1, 4.0, 0.0, 0.0, 0.0, 0.0, 20.0, 2.0, 2.0, 2.0, 5.0]
    print("  Running auto for 10s with vision injection...")
    start = time.time()
    while time.time() - start < 10.0:
        botpose_pub.set(valid_botpose)
        nt.flush()
        tick(ws)
        time.sleep(0.02)
        elapsed = time.time() - start
        if int(elapsed) > int(elapsed - 0.02) and int(elapsed) % 3 == 0:
            print(f"    {int(elapsed)}s...")

    # ── Cleanup ──
    print("\n[6] Disabling...")
    send_ds(ws, enabled=False)
    wait_ticking(ws, 1.0)

    botpose_pub.close()
    nt.stopClient()
    ws.close()

    print("\n" + "=" * 60)
    print("LED + TIMING TEST COMPLETE")
    print("Check OutlineViewer / console for:")
    print("  LEDs/* — animation transitions between phases")
    print("  FullAuto/Status — should show re-eval cycles (~every 0.5s)")
    print("  Vision/TargetValidDurationSec — should increment continuously")
    print("  Vision/HasTarget — should be true during auto phase")
    print("=" * 60)


def cmd_full_auto_test():
    """Run FullAutonomousCommand with fuel + opponent injection."""
    import ntcore

    print("=" * 60)
    print("VERIFY: FullAutonomousCommand with opponent injection")
    print("=" * 60)

    ws = connect()
    send_joystick(ws, port=0)
    send_joystick(ws, port=1)

    nt = ntcore.NetworkTableInstance.getDefault()
    nt.setServer("127.0.0.1", 5810)
    nt.startClient4("full_auto_test")
    time.sleep(2)
    print(f"  NT4 connected: {nt.isConnected()}")

    ll_table = nt.getTable("limelight")
    botpose_pub = ll_table.getDoubleArrayTopic("botpose_orb_wpiblue").publish()
    llpython_pub = ll_table.getDoubleArrayTopic("llpython").publish()

    # Select "Full Autonomous" in the auto chooser via NT4
    chooser_table = nt.getTable("SmartDashboard/Auto Chooser")
    selected_pub = chooser_table.getStringTopic("selected").publish()
    selected_pub.set("Full Autonomous")
    nt.flush()
    print("  Auto chooser set to 'Full Autonomous'")

    # ── Phase 1: Disable to reset state ──
    print("\n[1] Disabling for clean auto init...")
    send_ds(ws, enabled=False)
    wait_ticking(ws, 2.0)

    # ── Phase 2: Enable autonomous (no detections first) ──
    print("\n[2] Enabling AUTONOMOUS — no fuel/opponents initially...")
    send_ds(ws, enabled=True, autonomous=True, match_time=30.0)

    # Provide valid botpose so vision works
    valid_botpose = [2.0, 4.0, 0.0, 0.0, 0.0, 0.0, 20.0, 2.0, 2.0, 2.0, 5.0]

    # Run 5s with no detections — FullAuto should pick targets from strategy
    print("  Running 5s with no detections...")
    start = time.time()
    while time.time() - start < 5.0:
        botpose_pub.set(valid_botpose)
        llpython_pub.set([0.0])  # no detections
        nt.flush()
        tick(ws)
        time.sleep(0.02)

    # ── Phase 3: Inject fuel positions ──
    print("\n[3] Injecting fuel detections for 5s...")
    # 2 fuel positions at high confidence (needs 3 frames to confirm)
    llpython_fuel = [
        2.0, 5.0, 3.0, 0.95, 6.0, 5.0, 0.92,  # 2 fuel
        0.0,  # 0 opponents
    ]
    start = time.time()
    while time.time() - start < 5.0:
        botpose_pub.set(valid_botpose)
        llpython_pub.set(llpython_fuel)
        nt.flush()
        tick(ws)
        time.sleep(0.02)

    # ── Phase 4: Inject opponent near current target to trigger abort ──
    print("\n[4] Injecting opponent near target to trigger Bot Aborter (5s)...")
    # Opponent very close to a scoring position — should trigger ABORT
    llpython_opp = [
        1.0, 5.0, 3.0, 0.95,  # 1 fuel
        1.0, 2.5, 4.5, 0.90,  # 1 opponent near origin area
    ]
    start = time.time()
    while time.time() - start < 5.0:
        botpose_pub.set(valid_botpose)
        llpython_pub.set(llpython_opp)
        nt.flush()
        tick(ws)
        time.sleep(0.02)

    # ── Phase 5: Clear opponents, continue auto ──
    print("\n[5] Clearing opponents, running 5s more...")
    start = time.time()
    while time.time() - start < 5.0:
        botpose_pub.set(valid_botpose)
        llpython_pub.set([0.0])
        nt.flush()
        tick(ws)
        time.sleep(0.02)

    # ── Cleanup ──
    print("\n[6] Disabling...")
    send_ds(ws, enabled=False)
    wait_ticking(ws, 1.0)

    botpose_pub.close()
    llpython_pub.close()
    selected_pub.close()
    nt.stopClient()
    ws.close()

    print("\n" + "=" * 60)
    print("FULL AUTO TEST COMPLETE")
    print("Check sim console for [FULLAUTO] tags:")
    print("  STARTING → Target selection")
    print("  ARRIVED → Path completed")
    print("  ABORT → Opponent triggered Bot Aborter")
    print("  RETARGETING → Better target appeared")
    print("  NO_TARGETS → No candidates available")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    commands = {
        "status": cmd_status,
        "drive_test": cmd_drive_test,
        "auto_test": cmd_auto_test,
        "button_test": cmd_button_test,
        "full_verify": cmd_full_verify,
        "vision_test": cmd_vision_test,
        "led_timing_test": cmd_led_timing_test,
        "full_auto_test": cmd_full_auto_test,
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)
