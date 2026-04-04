# ═══════════════════════════════════════════════════════════════════════════════
# THE ENGINE — Hardware Configuration Questionnaire
# FRC Team 2950 (The Devastators)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Someone on the team who knows the hardware needs to answer these questions.
# This takes ~10 minutes. The answers directly generate the robot's software
# configuration files.
#
# ═══════════════════════════════════════════════════════════════════════════════

## 1. SWERVE MODULES

Module type: Thrifty Swerve (confirmed)

Drive motor: Kraken X60 (confirmed)

Steer motor: Kraken X60 (confirmed)

Absolute encoder: Thrifty Absolute Magnetic Encoder (confirmed)

Q1: Which drive gear ratio kit was purchased?
    Thrifty Swerve offers 6 options. Check the order receipt or look at the
    gear markings on the module. Common choices:
    [ ] 5.36:1
    [ ] 5.90:1
    [ ] 6.55:1
    [ ] 7.13:1
    [ ] 7.80:1
    [ ] 8.68:1
    Answer: _______________

Q2: What is the wheel diameter?
    [ ] 3 inches
    [ ] 4 inches (most common for Thrifty Swerve)
    [ ] Other: _____ inches
    Answer: _______________

## 2. GYROSCOPE

Q3: What gyroscope/IMU is the team using?
    [ ] CTRE Pigeon 2.0 (CAN bus)
    [ ] Kauai Labs NavX2-MXP (MXP SPI port)
    [ ] Kauai Labs NavX2-Micro (USB)
    [ ] ADIS16470 (SPI)
    [ ] Other: _______________
    Answer: _______________

Q4: If Pigeon 2.0, what CAN ID is it assigned?
    Answer: _______________

## 3. CAN BUS

Q5: What CAN IDs are assigned to each drive motor (Kraken/TalonFX)?
    Front Left  Drive: ___
    Front Right Drive: ___
    Back Left   Drive: ___
    Back Right  Drive: ___

Q6: What CAN IDs are assigned to each steer motor (Kraken/TalonFX)?
    Front Left  Steer: ___
    Front Right Steer: ___
    Back Left   Steer: ___
    Back Right  Steer: ___

Q7: Are CAN IDs already assigned, or should we pick them?
    [ ] Already assigned (fill in Q5 and Q6)
    [ ] Not assigned yet — use whatever makes sense
    Answer: _______________

## 4. ENCODER WIRING

Q8: Which roboRIO analog input ports are the Thrifty encoders wired to?
    (Thrifty Absolute Magnetic Encoders connect to the roboRIO analog inputs,
     NOT the CAN bus. They use ports 0-3 on the roboRIO analog input header.)
    Front Left  Encoder: Analog Port ___
    Front Right Encoder: Analog Port ___
    Back Left   Encoder: Analog Port ___
    Back Right  Encoder: Analog Port ___

    [ ] Not wired yet — use ports 0, 1, 2, 3
    Answer: _______________

## 5. CHASSIS DIMENSIONS

Q9: What is the trackwidth (center-to-center distance between left and right
    swerve module wheel contact patches)?
    Answer: _______________ inches

Q10: What is the wheelbase (center-to-center distance between front and rear
     swerve module wheel contact patches)?
     Answer: _______________ inches

Q11: Is the chassis square (trackwidth = wheelbase)?
     [ ] Yes
     [ ] No
     Answer: _______________

## 6. OTHER HARDWARE

Q12: Does the robot have a CANivore (CTRE CAN-to-USB adapter)?
     [ ] Yes — all swerve devices are on the CANivore bus
     [ ] Yes — but swerve devices are on the roboRIO CAN bus
     [ ] No — everything is on the roboRIO CAN bus
     Answer: _______________

Q13: How many Limelight cameras does the team have?
     [ ] 0 (none yet)
     [ ] 1
     [ ] 2 (needed for dual pipeline switching in Phase 2)
     [ ] Other: ___
     Answer: _______________

Q14: What Limelight version?
     [ ] Limelight 4 (has built-in Hailo AI accelerator)
     [ ] Limelight 3/3A/3G
     [ ] Limelight 2/2+
     [ ] Don't have one yet
     Answer: _______________

Q15: What power distribution hub is being used?
     [ ] REV Power Distribution Hub (PDH)
     [ ] CTRE Power Distribution Panel (PDP)
     Answer: _______________

## 7. EXISTING CODE

Q16: Does the team have any existing robot code from previous seasons?
     [ ] Yes — GitHub link: _______________
     [ ] No — starting fresh
     Answer: _______________

# ═══════════════════════════════════════════════════════════════════════════════
# RETURN THIS QUESTIONNAIRE TO YOUR SOFTWARE LEAD
# Once answered, all configuration files will be generated automatically.
# ═══════════════════════════════════════════════════════════════════════════════
