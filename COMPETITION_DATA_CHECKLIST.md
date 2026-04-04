# Competition Weekend Data Collection Checklist
# FRC Team 2950 — The Devastators
# "Run your code, collect data for The Engine"

> The kids are running their existing code this weekend — no last-minute
> changes. But they CAN collect data that will massively accelerate
> deploying The Engine on hardware afterward. Here's exactly what to grab.

---

## PRIORITY 1: Swerve Encoder Offsets (5 minutes, do ONCE in pits)

**Why:** The Engine needs calibrated encoder offsets to drive straight.
Without these, the swerve modules point in random directions.

**How:**
1. Power on the robot in the pit (no need to enable)
2. Physically point all 4 swerve modules straight forward
   - Bevel gears should all face the same direction (check your module docs)
3. Open the REV Hardware Client or AdvantageScope
4. Read the raw absolute encoder position for each module:
   - Front Left: _____ degrees
   - Front Right: _____ degrees
   - Back Left: _____ degrees
   - Back Right: _____ degrees
5. Write these 4 numbers on a sticky note and take a photo

**Alternative:** If the robot is already deployed with their code, look for
the encoder positions in the SmartDashboard/AdvantageScope under the swerve
module topics. YAGSL publishes raw encoder values.

---

## PRIORITY 2: AdvantageKit Match Logs (automatic, just save the USB)

**Why:** Match logs contain battery voltage curves, CAN bus usage, cycle
times, and drive patterns. The Engine's analysis scripts can process these
to tune brownout protection and find performance bottlenecks.

**How:**
1. Make sure there's a USB drive plugged into the roboRIO
   (AdvantageKit writes .wpilog files automatically)
2. After EACH match, the log is saved automatically
3. At the END of the day, pull the USB drive and copy all .wpilog files
   to a laptop
4. Label them: `qual1.wpilog`, `qual2.wpilog`, etc.

**Bonus:** Open a log in AdvantageScope and screenshot:
- Battery voltage graph for any match (especially if robot browned out)
- Any error messages in the Driver Station log

---

## PRIORITY 3: Limelight Images for YOLO Training (10 min between matches)

**Why:** The Wave Robotics YOLO model was trained on their field. Images
from YOUR competition venue under YOUR lighting will make fuel detection
much more reliable.

**How:**
1. Open the Limelight web UI: `http://limelight.local:5801`
2. Go to the camera feed tab
3. Point the robot toward game pieces on the field (or practice area)
4. Take screenshots (or use the Limelight snapshot feature) of:

| Shot | What to Capture | How Many |
|------|----------------|----------|
| Close fuel | Single fuel ball, 2-3 feet away | 5 |
| Mid fuel | Single fuel ball, 5-8 feet away | 5 |
| Far fuel | Single fuel ball, 10+ feet away | 5 |
| Multiple fuel | 2-3 balls in one frame | 5 |
| Partial occlusion | Ball behind bumper/field element | 3 |
| No fuel | Empty field (negative example) | 5 |
| Bright lighting | Under venue lights, no shadows | 3 |
| Shadow | Ball in shadow area | 3 |

**Total: ~35 images, 10 minutes of work.**

Save to a folder called `competition_images/` on a USB drive or laptop.

---

## PRIORITY 4: Limelight AprilTag Data (during practice matches)

**Why:** The Engine's vision pose estimation needs to know how far away
AprilTags typically are and what the latency looks like at your venue.
This helps tune the distance-based standard deviations.

**How:**
1. During a practice match or field calibration session, enable the robot
2. Open AdvantageScope connected to the robot
3. Look for Limelight NetworkTables topics:
   - `limelight/botpose_orb_wpiblue` — the vision pose
   - `limelight/tl` — pipeline latency (milliseconds)
   - `limelight/tv` — target valid (0 or 1)
4. Drive the robot to 3 known positions on the field:
   - Against the alliance wall center (known coordinates)
   - At the center of the field
   - Near a scoring target
5. At each position, note:
   - How many AprilTags the Limelight sees (tag count)
   - Reported latency in milliseconds
   - Whether the pose looks correct in AdvantageScope

Write down: "Position X: saw N tags, latency Yms, pose looks correct/wrong"

---

## PRIORITY 5: Drive Team Feedback (conversation, no tech needed)

**Why:** The Engine adds AutoAlign (auto-rotate to target) and
DriveToGamePiece (auto-drive toward fuel). The drivers need to say
whether they'd actually USE these features.

**Ask the drivers after a match:**
- "When you're lining up to score, do you wish the robot would auto-aim?"
- "When you're chasing a ball, would you want the robot to drive itself
  toward it while you control rotation?"
- "What's the most annoying part of driving right now?"
- "Do you ever lose track of where fuel balls are on the field?"

Write down their answers. This shapes which Engine features get deployed
first vs. shelved.

---

## PRIORITY 6: Battery Data (just label your batteries)

**Why:** The Engine has brownout protection that scales motor output based
on battery voltage. Knowing which batteries hold up and which sag tells
us how aggressive to set the threshold.

**How:**
1. Label each battery with a number (sharpie on electrical tape)
2. Before each match, write down: "Match Q3: Battery #4, voltage = 12.8V"
3. After each match, note: "Battery #4 after Q3: 12.1V" (or "browned out")
4. If the robot ever loses power or drives sluggishly, note the battery #

---

## PRIORITY 7: Field Measurements (5 min at the practice field)

**Why:** The Engine's navigation grid and pathfinding are based on the
official field CAD dimensions. Real fields sometimes differ slightly.

**If you get practice field access, measure and photograph:**
- Distance from alliance wall to nearest scoring target
- Width of any gaps the robot drives through
- Location of any field obstacles that aren't in the CAD

Even rough measurements ("about 3 feet from the wall to the coral station")
are helpful.

---

## What to Bring Home

At the end of the competition weekend, bring back:

- [ ] USB drive with AdvantageKit .wpilog files (Priority 2)
- [ ] 4 encoder offset numbers — written down or photographed (Priority 1)
- [ ] Folder of 30+ Limelight images (Priority 3)
- [ ] Notes on AprilTag visibility at 3 field positions (Priority 4)
- [ ] Driver feedback on assist features (Priority 5)
- [ ] Battery performance log (Priority 6)
- [ ] Field measurement notes/photos (Priority 7)

**This data turns a 2-week hardware integration into a 2-day process.**
None of it requires changing any code on the robot.
