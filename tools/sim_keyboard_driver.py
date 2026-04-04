#!/usr/bin/env python3
"""
Keyboard-to-WPILib Sim bridge — replaces the Sim GUI for joystick + DriverStation.

Sends keyboard input as joystick axes to the WPILib simulator via WebSocket,
and manages DriverStation enable/disable. Use with AdvantageScope for visualization.

Controls:
  W/S       — Forward / Backward  (Left stick Y)
  A/D       — Strafe left / right (Left stick X)
  J/L       — Rotate CCW / CW     (Right stick X)
  SPACE     — Button A  (zero gyro)
  E         — Button B
  Q         — Button X
  R         — Button Y
  1         — Button LB
  2         — Button RB
  T         — Toggle Teleop enabled/disabled
  ESC       — Quit

Usage:
  1. Start sim:    JAVA_HOME=~/wpilib/2026/jdk ./gradlew simulateJava
  2. Start driver: python3 tools/sim_keyboard_driver.py
  3. Open AdvantageScope → Connect to Simulator
  4. Press T to enable teleop, then WASD to drive!

Requires: pip3 install websockets
"""

import asyncio
import json
import sys
import time

try:
    import websockets
except ImportError:
    print("Missing 'websockets' — run: pip3 install websockets")
    sys.exit(1)

import tty
import termios
import select

WS_URI = "ws://localhost:3300/wpilibws"
SEND_HZ = 50
# How long a key "sticks" after being pressed (seconds).
# Terminal key-repeat sends ~30 chars/sec, so 0.12s covers gaps between repeats.
KEY_HOLD_TIME = 0.12


async def main():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    print("═══ WPILib Sim Keyboard Driver ═══")
    print()
    print("  W/S       = Forward / Back")
    print("  A/D       = Strafe Left / Right")
    print("  J/L       = Rotate CCW / CW")
    print("  SPACE     = Button A (zero gyro)")
    print("  Q/E/R     = Buttons X / B / Y")
    print("  1/2       = LB / RB")
    print("  T         = Toggle Teleop enable")
    print("  ESC       = Quit")
    print()
    print(f"Connecting to {WS_URI}...")

    try:
        tty.setcbreak(fd)

        async with websockets.connect(WS_URI) as ws:
            print("✓ Connected to WPILib simulator!")
            print()
            print("Press T to enable Teleop, then WASD to drive!")
            print()

            axes = [0.0] * 6
            buttons = [False] * 16
            teleop_enabled = False
            frame = 0

            # Track when each key was last seen (for hold behavior)
            key_last_seen = {}

            while True:
                now = time.time()

                # Read all pending characters
                while select.select([fd], [], [], 0)[0]:
                    ch = sys.stdin.read(1)
                    if ch == "\x1b":
                        # Check for arrow key sequence
                        if select.select([fd], [], [], 0.01)[0]:
                            ch2 = sys.stdin.read(1)
                            if ch2 == "[" and select.select([fd], [], [], 0.01)[0]:
                                ch3 = sys.stdin.read(1)
                                if ch3 == "C":
                                    key_last_seen["RIGHT"] = now
                                elif ch3 == "D":
                                    key_last_seen["LEFT"] = now
                                continue
                        # Bare ESC = quit
                        print("\nQuitting...")
                        return
                    elif ch == "t" or ch == "T":
                        teleop_enabled = not teleop_enabled
                        ds_msg = json.dumps({
                            "type": "DriverStation", "device": "",
                            "data": {
                                ">enabled": teleop_enabled,
                                ">autonomous": False, ">test": False,
                                ">estop": False, ">fms": False,
                                ">ds": True, ">station": "red1",
                                ">new_data": True,
                            },
                        })
                        await ws.send(ds_msg)
                    else:
                        key_last_seen[ch.lower()] = now

                # Build axes from recently-active keys
                for i in range(6):
                    axes[i] = 0.0
                for i in range(len(buttons)):
                    buttons[i] = False

                def held(k):
                    return now - key_last_seen.get(k, 0) < KEY_HOLD_TIME

                # Translation
                if held("w"):
                    axes[1] = -1.0
                if held("s"):
                    axes[1] = 1.0
                if held("a"):
                    axes[0] = -1.0
                if held("d"):
                    axes[0] = 1.0
                # Rotation (J/L since arrow keys can be unreliable in raw terminal)
                if held("j") or held("LEFT"):
                    axes[4] = -1.0
                if held("l") or held("RIGHT"):
                    axes[4] = 1.0

                # Buttons
                if held(" "):
                    buttons[0] = True  # A
                if held("e"):
                    buttons[1] = True  # B
                if held("q"):
                    buttons[2] = True  # X
                if held("r"):
                    buttons[3] = True  # Y
                if held("1"):
                    buttons[4] = True  # LB
                if held("2"):
                    buttons[5] = True  # RB

                # Send joystick
                joy = json.dumps({
                    "type": "Joystick", "device": "0",
                    "data": {
                        ">axes": list(axes),
                        ">buttons": list(buttons),
                        ">povs": [-1],
                    },
                })
                await ws.send(joy)

                # Keep DS enabled
                if frame % 10 == 0:
                    ds_msg = json.dumps({
                        "type": "DriverStation", "device": "",
                        "data": {
                            ">enabled": teleop_enabled,
                            ">autonomous": False, ">test": False,
                            ">estop": False, ">fms": False,
                            ">ds": True, ">station": "red1",
                            ">new_data": True,
                        },
                    })
                    await ws.send(ds_msg)

                # Drain incoming
                try:
                    while True:
                        await asyncio.wait_for(ws.recv(), timeout=0.001)
                except:
                    pass

                # Status
                if frame % 10 == 0:
                    state = "ENABLED " if teleop_enabled else "DISABLED"
                    ax_str = f"LX={axes[0]:+.0f} LY={axes[1]:+.0f} RX={axes[4]:+.0f}"
                    btn_names = []
                    for name, idx in [("A",0),("B",1),("X",2),("Y",3),("LB",4),("RB",5)]:
                        if buttons[idx]:
                            btn_names.append(name)
                    btn_str = f" [{' '.join(btn_names)}]" if btn_names else ""
                    sys.stdout.write(f"\r  [{state}]  {ax_str}{btn_str}              ")
                    sys.stdout.flush()

                frame += 1
                await asyncio.sleep(1.0 / SEND_HZ)

    except ConnectionRefusedError:
        print("ERROR: Can't connect. Is ./gradlew simulateJava running?")
    except websockets.exceptions.ConnectionClosed:
        print("\nSimulator disconnected.")
    except KeyboardInterrupt:
        print("\nQuitting...")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
