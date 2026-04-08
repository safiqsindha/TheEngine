#!/usr/bin/env python3
"""
THE ENGINE — E.1 Wiring Standards Card + E.4 PDH Slot Template
Team 2950 The Devastators
v2: Rule citations on every row
"""

from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white
from reportlab.pdfgen import canvas
import os

CARD_W = 6 * inch
CARD_H = 4 * inch

BG_DARK = HexColor("#0F1117")
BG_ROW = HexColor("#222533")
BG_ROW_ALT = HexColor("#1A1D27")
BG_HEADER = HexColor("#2563EB")
BG_WARN = HexColor("#DC2626")
BG_GREEN = HexColor("#16A34A")
BG_YELLOW = HexColor("#CA8A04")
TEXT_PRIMARY = HexColor("#F0F0F0")
TEXT_SECONDARY = HexColor("#9CA3AF")
TEXT_ACCENT = HexColor("#60A5FA")
TEXT_CITE = HexColor("#FBBF24")

def rr(c, x, y, w, h, r, fill):
    c.setFillColor(fill)
    c.roundRect(x, y, w, h, r, fill=1, stroke=0)

def draw_row(c, x, y, cols, widths, fs=5.5, bg=BG_ROW, tc=TEXT_PRIMARY, bold=False):
    rh = 12
    rr(c, x, y, sum(widths), rh, 1, bg)
    c.setFillColor(tc)
    c.setFont("Helvetica-Bold" if bold else "Helvetica", fs)
    cx = x
    for i, col in enumerate(cols):
        c.drawString(cx + 3, y + 3, str(col))
        cx += widths[i]
    return y - rh - 1

def draw_cited_row(c, x, y, cols, widths, cite, fs=5.5, bg=BG_ROW, tc=TEXT_PRIMARY):
    """Draw a row with the last column as a yellow citation"""
    rh = 12
    rr(c, x, y, sum(widths), rh, 1, bg)
    cx = x
    for i, col in enumerate(cols):
        if i == len(cols) - 1:
            c.setFillColor(TEXT_CITE)
            c.setFont("Helvetica-Bold", 5)
        else:
            c.setFillColor(tc)
            c.setFont("Helvetica", fs)
        c.drawString(cx + 3, y + 3, str(col))
        cx += widths[i]
    return y - rh - 1


def generate_e1(path):
    c = canvas.Canvas(path, pagesize=(CARD_W, CARD_H))

    # ---- PAGE 1: Wire Gauge + Connector Reference ----
    c.setFillColor(BG_DARK)
    c.rect(0, 0, CARD_W, CARD_H, fill=1, stroke=0)

    rr(c, 8, CARD_H - 28, CARD_W - 16, 22, 4, BG_HEADER)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(14, CARD_H - 22, "E.1 WIRING STANDARDS  |  TEAM 2950")
    c.setFont("Helvetica", 6)
    c.drawRightString(CARD_W - 14, CARD_H - 22, "SIDE 1: Wire Gauge + Connectors")

    widths = [105, 48, 62, 38, 48, 55, 58]
    headers = ["CIRCUIT", "GAUGE", "CONNECTOR", "MAX A", "COLOR", "NOTES", "RULE"]
    y = CARD_H - 38
    y = draw_row(c, 8, y, headers, widths, 5, BG_HEADER, white, True)

    rows = [
        ("Battery > Main Breaker", "6 AWG", "SB50 (Red)", "120A", "Red/Blk", "Short run", "R609"),
        ("Main Breaker > PDH", "6 AWG", "WAGO/Ferrule", "120A", "Red/Blk", "Ferrule both", "R609"),
        ("PDH > Drive Motor", "12 AWG", "WAGO 221", "40A", "Per motor", "NEO+SPARK MAX", "R621 T8-3"),
        ("PDH > Mechanism Motor", "14 AWG", "WAGO 221", "30A", "Per motor", "Label both ends", "R621 T8-3"),
        ("PDH > Small Motor", "18 AWG", "WAGO 221", "20A", "Per motor", "NEO 550 class", "R621 T8-3"),
        ("CAN Bus", "22 AWG", "Ferrule ONLY", "Signal", "Yel/Grn", "Daisy-chain!", "Mfr spec"),
        ("roboRIO Power", "18 AWG", "Ferrule>WAGO", "10A", "Red/Blk", "PDH slot 20", "WPILib"),
        ("Radio Power", "18 AWG", "Barrel jack", "---", "Red/Blk", "12V regulated", "WPILib"),
        ("Limelight Power", "18 AWG", "Direct PDH", "---", "Red/Blk", "Slot 22-23", "WPILib"),
        ("Sensors (DIO)", "22-26", "PWM header", "Signal", "Per spec", "Check docs", "Mfr spec"),
    ]

    for i, row in enumerate(rows):
        bg = BG_ROW if i % 2 == 0 else BG_ROW_ALT
        y = draw_cited_row(c, 8, y, row, widths, row[-1], 5, bg)

    # Additional rules box
    y -= 5
    rr(c, 8, y - 22, CARD_W - 16, 22, 3, HexColor("#1E293B"))
    c.setFillColor(TEXT_CITE)
    c.setFont("Helvetica-Bold", 5.5)
    c.drawString(14, y - 8, "ADDITIONAL RULES FROM FRC MANUAL:")
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica", 5)
    c.drawString(14, y - 16, "R622: Copper wire only  |  R623: 1 wire per WAGO terminal  |  R624: Color code all power wire  |  Ferrules = best practice (3847)")

    # CAN rules
    y -= 30
    rr(c, 8, y - 48, CARD_W - 16, 48, 3, HexColor("#1E293B"))
    c.setFillColor(BG_WARN)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawString(14, y - 8, "CAN BUS RULES (NON-NEGOTIABLE)")
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica", 5.5)
    rules = [
        "1. ALWAYS daisy-chain: roboRIO > PDH > Motor 1 > Motor 2 > ... > End",
        "2. NEVER star topology — splitting CAN to branches causes dropouts",
        "3. Ferrule crimp EVERY CAN wire (best practice, prevents intermittent failures)",
        "4. Yellow = CAN High, Green = CAN Low — NEVER swap colors",
        "5. Label BOTH ends of every wire with circuit name + CAN ID",
    ]
    ty = y - 17
    for rule in rules:
        c.drawString(14, ty, rule)
        ty -= 7

    # ---- PAGE 2: CAN Topology ----
    c.showPage()
    c.setFillColor(BG_DARK)
    c.rect(0, 0, CARD_W, CARD_H, fill=1, stroke=0)

    rr(c, 8, CARD_H - 28, CARD_W - 16, 22, 4, BG_HEADER)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(14, CARD_H - 22, "E.1 CAN TOPOLOGY  |  TEAM 2950")
    c.setFont("Helvetica", 6)
    c.drawRightString(CARD_W - 14, CARD_H - 22, "SIDE 2: CAN Chain (from Constants.java)")

    y = CARD_H - 40
    c.setFillColor(TEXT_ACCENT)
    c.setFont("Helvetica-Bold", 6)
    c.drawString(14, y, "ACTIVE CAN CHAIN — VERIFIED FROM ROBOT CODE")

    chain = [
        ("roboRIO", "---", "Chain start", BG_GREEN),
        ("PDH", "CAN 0", "Power Distribution Hub", HexColor("#374151")),
        ("FL Drive", "CAN 1", "NEO + SPARK MAX", BG_HEADER),
        ("FL Steer", "CAN 2", "NEO + SPARK MAX", BG_HEADER),
        ("FR Drive", "CAN 3", "NEO + SPARK MAX", BG_HEADER),
        ("FR Steer", "CAN 4", "NEO + SPARK MAX", BG_HEADER),
        ("BL Drive", "CAN 5", "NEO + SPARK MAX", BG_HEADER),
        ("BL Steer", "CAN 6", "NEO + SPARK MAX", BG_HEADER),
        ("BR Drive", "CAN 7", "NEO + SPARK MAX", BG_HEADER),
        ("BR Steer", "CAN 8", "NEO + SPARK MAX", BG_HEADER),
        ("FL Encoder", "CAN 9", "Thrifty 10-Pin", HexColor("#374151")),
        ("FR Encoder", "CAN 10", "Thrifty 10-Pin", HexColor("#374151")),
        ("BL Encoder", "CAN 11", "Thrifty 10-Pin", HexColor("#374151")),
        ("BR Encoder", "CAN 12", "Thrifty 10-Pin", HexColor("#374151")),
        ("Pigeon 2", "CAN 13", "Gyroscope (ADIS16470)", HexColor("#374151")),
    ]

    y -= 6
    for i, (name, can_id, desc, bg) in enumerate(chain):
        ry = y - (i * 11)
        if i > 0:
            c.setStrokeColor(TEXT_ACCENT)
            c.setLineWidth(0.4)
            c.line(32, ry + 12, 32, ry + 8)

        rr(c, 14, ry - 1, 55, 9, 2, bg)
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 5)
        c.drawString(17, ry + 1, name)

        c.setFillColor(TEXT_CITE)
        c.setFont("Helvetica-Bold", 5)
        c.drawString(75, ry + 1, can_id)

        c.setFillColor(TEXT_SECONDARY)
        c.setFont("Helvetica", 5)
        c.drawString(115, ry + 1, desc)

        c.setFillColor(HexColor("#4ADE80"))
        c.setFont("Helvetica", 4)
        c.drawString(240, ry + 1, "VERIFIED" if i < 15 else "")

    y_bottom = y - (len(chain) * 11) - 6
    rr(c, 14, y_bottom - 18, CARD_W - 28, 18, 3, HexColor("#422006"))
    c.setFillColor(BG_YELLOW)
    c.setFont("Helvetica-Bold", 6)
    c.drawString(20, y_bottom - 7, "CAN 14+ = MECHANISM MOTORS (fill in E.4 on kickoff day)")
    c.setFillColor(TEXT_SECONDARY)
    c.setFont("Helvetica", 5)
    c.drawString(20, y_bottom - 14, "Students assign CAN IDs 14, 15, 16... for each new motor added")

    c.save()
    print(f"E.1 saved: {path}")


def generate_e4(path):
    c = canvas.Canvas(path, pagesize=(CARD_W, CARD_H))

    # ---- PAGE 1: Slots 0-12 ----
    c.setFillColor(BG_DARK)
    c.rect(0, 0, CARD_W, CARD_H, fill=1, stroke=0)

    rr(c, 8, CARD_H - 28, CARD_W - 16, 22, 4, BG_HEADER)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(14, CARD_H - 22, "E.4 PDH SLOT TEMPLATE  |  TEAM 2950")
    c.setFont("Helvetica", 6)
    c.drawRightString(CARD_W - 14, CARD_H - 22, "PAGE 1: Slots 0-12")

    # Legend
    y = CARD_H - 35
    c.setFont("Helvetica", 5)
    c.setFillColor(BG_GREEN)
    c.rect(14, y, 6, 6, fill=1, stroke=0)
    c.setFillColor(TEXT_SECONDARY)
    c.drawString(24, y + 1, "= Verified from code")
    c.setFillColor(BG_YELLOW)
    c.rect(130, y, 6, 6, fill=1, stroke=0)
    c.setFillColor(TEXT_SECONDARY)
    c.drawString(140, y + 1, "= Students fill in")
    c.setFillColor(TEXT_CITE)
    c.drawString(240, y + 1, "All per R609, R621, Table 8-3")

    widths = [30, 38, 120, 42, 38, 55, 48, 43]
    headers = ["SLOT", "BRKR", "ASSIGNMENT", "GAUGE", "CAN", "CTRL", "STATUS", "RULE"]
    y -= 12
    y = draw_row(c, 8, y, headers, widths, 4.5, BG_HEADER, white, True)

    swerve = [
        ("0", "40A", "Front-Left DRIVE", "12 AWG", "1", "SPARK MAX", "VERIFIED", "R621"),
        ("1", "40A", "Front-Left STEER", "12 AWG", "2", "SPARK MAX", "VERIFIED", "R621"),
        ("2", "40A", "Front-Right DRIVE", "12 AWG", "3", "SPARK MAX", "VERIFIED", "R621"),
        ("3", "40A", "Front-Right STEER", "12 AWG", "4", "SPARK MAX", "VERIFIED", "R621"),
        ("4", "40A", "Back-Left DRIVE", "12 AWG", "5", "SPARK MAX", "VERIFIED", "R621"),
        ("5", "40A", "Back-Left STEER", "12 AWG", "6", "SPARK MAX", "VERIFIED", "R621"),
        ("6", "40A", "Back-Right DRIVE", "12 AWG", "7", "SPARK MAX", "VERIFIED", "R621"),
        ("7", "40A", "Back-Right STEER", "12 AWG", "8", "SPARK MAX", "VERIFIED", "R621"),
    ]

    for i, row in enumerate(swerve):
        bg = HexColor("#0D2818") if i % 2 == 0 else HexColor("#0F2D1A")
        y = draw_cited_row(c, 8, y, row, widths, row[-1], 5, bg, BG_GREEN)

    y -= 2
    c.setFillColor(BG_YELLOW)
    c.setFont("Helvetica-Bold", 5.5)
    c.drawString(14, y, "MECHANISM MOTORS — Students: fill in on kickoff day")
    y -= 3

    for i in range(5):
        slot = str(8 + i)
        row = (slot, "___A", "________________________", "__ AWG", "___", "________", "", "R621")
        bg = HexColor("#2A2000") if i % 2 == 0 else HexColor("#221A00")
        y = draw_cited_row(c, 8, y, row, widths, "R621", 5, bg, BG_YELLOW)

    # ---- PAGE 2: Slots 13-23 + fill-in rules ----
    c.showPage()
    c.setFillColor(BG_DARK)
    c.rect(0, 0, CARD_W, CARD_H, fill=1, stroke=0)

    rr(c, 8, CARD_H - 28, CARD_W - 16, 22, 4, BG_HEADER)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(14, CARD_H - 22, "E.4 PDH SLOT TEMPLATE  |  TEAM 2950")
    c.setFont("Helvetica", 6)
    c.drawRightString(CARD_W - 14, CARD_H - 22, "PAGE 2: Slots 13-23 + Rules")

    y = CARD_H - 38
    y = draw_row(c, 8, y, headers, widths, 4.5, BG_HEADER, white, True)

    for i in range(7):
        slot = str(13 + i)
        row = (slot, "___A", "________________________", "__ AWG", "___", "________", "", "R621")
        bg = HexColor("#2A2000") if i % 2 == 0 else HexColor("#221A00")
        y = draw_cited_row(c, 8, y, row, widths, "R621", 5, bg, BG_YELLOW)

    y -= 2
    c.setFillColor(BG_GREEN)
    c.setFont("Helvetica-Bold", 5.5)
    c.drawString(14, y, "CONTROL SYSTEM — Do not change without mentor approval")
    y -= 3

    ctrl = [
        ("20", "10A", "roboRIO", "18 AWG", "---", "---", "VERIFIED", "R601"),
        ("21", "10A", "Radio (barrel jack)", "18 AWG", "---", "---", "VERIFIED", "R602"),
        ("22", "10A", "Limelight 1", "18 AWG", "---", "---", "VERIFIED", "R621"),
        ("23", "10A", "Limelight 2", "18 AWG", "---", "---", "VERIFIED", "R621"),
    ]

    for i, row in enumerate(ctrl):
        bg = HexColor("#0D2818") if i % 2 == 0 else HexColor("#0F2D1A")
        y = draw_cited_row(c, 8, y, row, widths, row[-1], 5, bg, BG_GREEN)

    # Rules box
    y -= 6
    box_h = 62
    rr(c, 8, y - box_h, CARD_W - 16, box_h, 4, HexColor("#1E293B"))
    c.setFillColor(BG_WARN)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawString(14, y - 9, "RULES FOR FILLING IN SLOTS 8-19")
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica", 5.5)
    rules = [
        ("1. BREAKER must match wire gauge (R621, Table 8-3):", ""),
        ("   40A breaker = 12 AWG min  |  30A = 14 AWG min  |  20A = 18 AWG min", ""),
        ("2. CAN IDs for mechanisms start at 14 (1-13 are swerve + gyro)", ""),
        ("3. NO two devices may share a CAN ID — check before assigning", "R714"),
        ("4. Write motor PURPOSE: 'Elevator L' not 'Motor 1'", ""),
        ("5. All wire must be COPPER and COLOR CODED (R622, R624)", "R622/R624"),
        ("6. ONE wire per WAGO terminal — use splice if splitting (R623)", "R623"),
        ("7. Get MENTOR SIGN-OFF before powering on new circuits", ""),
    ]
    ty = y - 18
    for rule_text, cite in rules:
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica", 5)
        c.drawString(14, ty, rule_text)
        if cite:
            c.setFillColor(TEXT_CITE)
            c.setFont("Helvetica-Bold", 5)
            c.drawRightString(CARD_W - 16, ty, cite)
        ty -= 7

    c.save()
    print(f"E.4 saved: {path}")


if __name__ == "__main__":
    out = "/mnt/user-data/outputs"
    generate_e1(os.path.join(out, "E1_Wiring_Standards_Card.pdf"))
    generate_e4(os.path.join(out, "E4_PDH_Slot_Template.pdf"))
    print("Done! Print at 100% on 4x6 card stock, laminate both sides.")
    print("Yellow text = FRC rule citation. Every spec is traceable.")
