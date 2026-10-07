"""
Electrical connectivity for Fiberboard AIO Logic.
- Schematic: global labels placed exactly on pin tips (= KiCad connection)
- Optional local wires for visual chains
- PCB: pad net assignment + simple Manhattan tracks
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

# KiCad schematic connection grid
GRID = 1.27

# Field I/O: socket 2EDG5.08 (cái trên bo) — cắm đực 2EDG mua Shopee/Lazada.
FP_EDG_2P = "Fiberboard:Terminal_2EDG5.08-1x02_P5.08mm_Horizontal"
FP_EDG_3P = "Fiberboard:Terminal_2EDG5.08-1x03_P5.08mm_Horizontal"


def snap(v: float) -> float:
    return round(v / GRID) * GRID


# Pin geometry: pin_number -> (x_off, y_off) tip position relative to symbol origin
# Sourced from KiCad 10 symbol libraries / Fiberboard local lib
PIN_GEOM: dict[str, dict[str, tuple[float, float]]] = {
    "Device:R": {"1": (0.0, 3.81), "2": (0.0, -3.81)},
    "Device:C": {"1": (0.0, 3.81), "2": (0.0, -3.81)},
    "Device:L": {"1": (0.0, 3.81), "2": (0.0, -3.81)},
    "Device:LED": {"1": (-3.81, 0.0), "2": (3.81, 0.0)},  # 1=K, 2=A
    "Device:D": {"1": (-3.81, 0.0), "2": (3.81, 0.0)},  # 1=K, 2=A
    "Device:Fuse": {"1": (0.0, 3.81), "2": (0.0, -3.81)},
    "Device:D_TVS": {"1": (-3.81, 0.0), "2": (3.81, 0.0)},
    "Transistor_FET:Q_PMOS_GSD": {"1": (-5.08, 0.0), "2": (2.54, -5.08), "3": (2.54, 5.08)},  # G,S,D
    "Device:R_Potentiometer": {"1": (0.0, 3.81), "2": (3.81, 0.0), "3": (0.0, -3.81)},
    "Transistor_FET:AO3400A": {"1": (-5.08, 0.0), "2": (2.54, -5.08), "3": (2.54, 5.08)},  # G,S,D
    "Transistor_BJT:2N3904": {"1": (2.54, -5.08), "2": (-5.08, 0.0), "3": (2.54, 5.08)},  # E,B,C
    "Sensor_Optical:SFH309": {"1": (2.54, 5.08), "2": (2.54, -5.08)},  # C,E
    "Amplifier_Operational:LM358": {
        "1": (7.62, 0.0),
        "2": (-7.62, -2.54),
        "3": (-7.62, 2.54),
        "4": (-2.54, -7.62),
        "5": (-7.62, 2.54),
        "6": (-7.62, -2.54),
        "7": (7.62, 0.0),
        "8": (-2.54, 7.62),
    },
    "Comparator:LM393": {
        "1": (7.62, 0.0),
        "2": (-7.62, -2.54),
        "3": (-7.62, 2.54),
        "4": (-2.54, -7.62),
        "5": (-7.62, 2.54),
        "6": (-7.62, -2.54),
        "7": (7.62, 0.0),
        "8": (-2.54, 7.62),
    },
    "Regulator_Linear:AMS1117-3.3": {"1": (0.0, -7.62), "2": (7.62, 0.0), "3": (-7.62, 0.0)},  # GND,VO,VI
    "Regulator_Switching:XL1509-5.0": {
        "1": (-10.16, 2.54),
        "2": (10.16, 2.54),
        "3": (10.16, -2.54),
        "4": (-10.16, -2.54),
        "5": (0.0, -7.62),
    },
    "Interface_UART:MAX485E": {
        "1": (-10.16, 5.08),
        "2": (-10.16, 2.54),
        "3": (-10.16, 0.0),
        "4": (-10.16, -5.08),
        "5": (0.0, -15.24),
        "6": (10.16, 7.62),
        "7": (10.16, 2.54),
        "8": (0.0, 15.24),
    },
    "Fiberboard:ESP32_DevKitC_Socket": {
        **{str(i): (-15.24, -(i - 1) * 2.54) for i in range(1, 20)},
        **{str(i): (15.24, -(i - 20) * 2.54) for i in range(20, 39)},
    },
    "Fiberboard:G5LE-1": {
        "1": (0.0, -2.54),
        "2": (-6.0, -0.54),
        "3": (-6.0, 16.74),
        "4": (6.0, 16.74),
        "5": (6.0, -0.54),
    },
    "Fiberboard:Opto_DIP6": {
        "1": (-2.54, 0.0),
        "2": (-2.54, 2.54),
        "3": (-2.54, 5.08),
        "4": (10.16, 5.08),
        "5": (10.16, 2.54),
        "6": (10.16, 0.0),
    },
    "Fiberboard:Screw_Terminal_01x02": {"1": (0.0, 2.54), "2": (5.08, 2.54)},
    "Fiberboard:Screw_Terminal_01x03": {"1": (0.0, 2.54), "2": (5.08, 2.54), "3": (10.16, 2.54)},
    "Fiberboard:Screw_Terminal_01x04": {
        "1": (0.0, 2.54),
        "2": (2.54, 2.54),
        "3": (5.08, 2.54),
        "4": (7.62, 2.54),
    },
    "Amplifier_Operational:LMV321": {"1": (-7.62, 2.54), "2": (-2.54, -7.62), "3": (-7.62, -2.54), "4": (7.62, 0.0), "5": (-2.54, 7.62)},
    "Comparator:LMV331": {"1": (-7.62, 2.54), "2": (-2.54, -7.62), "3": (-7.62, -2.54), "4": (7.62, 0.0), "5": (-2.54, 7.62)},
    "Fiberboard:AFBR_1624Z": {
        "1": (5.08, 2.54),
        "3": (0.0, 2.54),
        "4": (-5.08, 2.54),
        "5": (-5.08, -2.54),
        "8": (5.08, -2.54),
    },
    "Fiberboard:AFBR_2624Z": {
        "1": (5.08, 2.54),
        "2": (2.54, 2.54),
        "3": (0.0, 2.54),
        "4": (-5.08, 2.54),
        "5": (-5.08, -2.54),
        "8": (5.08, -2.54),
    },
    "Fiberboard:PC817": {
        "1": (-5.08, 2.54),
        "2": (-5.08, -2.54),
        "3": (5.08, -2.54),
        "4": (5.08, 2.54),
    },
    "Fiberboard:SOT23": {"1": (-4.415, -1.9), "2": (-4.415, 1.9), "3": (4.415, 0.0)},
    "power:GND": {"1": (0.0, 0.0)},
    "power:PWR_FLAG": {"1": (0.0, 0.0)},
    "Fiberboard:NetTie_2": {"1": (-5.08, 0.0), "2": (5.08, 0.0)},
    "Fiberboard:CM_Choke_4": {
        "1": (-7.62, 2.54),
        "2": (-7.62, -2.54),
        "3": (7.62, 2.54),
        "4": (7.62, -2.54),
    },
    "power:+3V3": {"1": (0.0, 0.0)},
    "power:+5V": {"1": (0.0, 0.0)},
    "power:+12V": {"1": (0.0, 0.0)},
    "power:+24V": {"1": (0.0, 0.0)},
}


@dataclass
class Comp:
    ref: str
    lib_id: str
    value: str
    footprint: str
    x: float
    y: float
    rot: int = 0
    unit: int = 1
    pins: int = 2

    def __post_init__(self):
        self.x = snap(self.x)
        self.y = snap(self.y)


@dataclass
class Design:
    comps: list[Comp] = field(default_factory=list)
    # net -> list of (ref, pin)
    nets: dict[str, list[tuple[str, str]]] = field(default_factory=lambda: defaultdict(list))

    def add(self, c: Comp):
        self.comps.append(c)

    def connect(self, net: str, *pins: tuple[str, str]):
        for p in pins:
            self.nets[net].append(p)

    def by_ref(self) -> dict[str, Comp]:
        return {c.ref: c for c in self.comps}


def rotate_schematic(fx: float, fy: float, rot: int) -> tuple[float, float]:
    """Rotate a point in schematic space (Y increases downward), CCW degrees."""
    r = rot % 360
    if r == 0:
        return fx, fy
    if r == 90:
        return fy, -fx
    if r == 180:
        return -fx, -fy
    if r == 270:
        return -fy, fx
    return fx, fy


def pin_abs(c: Comp, pin: str) -> tuple[float, float]:
    """Absolute schematic pin-tip position.

    Symbol libraries use Y-up; schematic sheets use Y-down, so local pin (ox, oy)
    becomes (ox, -oy) before applying the instance rotation/translation.
    """
    geom = PIN_GEOM.get(c.lib_id)
    if not geom or pin not in geom:
        return c.x, c.y
    ox, oy = geom[pin]
    fx, fy = rotate_schematic(ox, -oy, c.rot)
    return c.x + fx, c.y + fy


def build_logic_design() -> Design:
    """Full board connectivity — schematic coordinates (mm), readable layout."""
    d = Design()

    # ========== POWER (24V IN PROTECTION + BUCK) ==========
    # J1 -> F1 (giá 5x20, thay cầu chì tay) -> CM L2 -> MOV RV1 + TVS D7 -> P-FET Q12 -> bulk C4
    # FB1/FB2 rails; GND star NT1 + D11/C23/FB3; +5V_RLY branch F2/D12/C24; F3 on +24V solenoid
    FP_FUSE_5X20 = "Fiberboard:Fuseholder_5x20mm_Horizontal"
    px, py = 18, 28
    d.add(Comp("J1", "Fiberboard:Screw_Terminal_01x02", "VIN", FP_EDG_2P, px, py, pins=2))
    # Tap +24V đã qua F1/L2/Q12, cấp cho J_PWR của mạch keyboard (keyboard tự bảo vệ).
    d.add(Comp("J2", "Fiberboard:Screw_Terminal_01x02", "KB24", FP_EDG_2P, px + 30, py + 16, pins=2))
    d.add(Comp("F1", "Device:Fuse", "5x20 F4A", FP_FUSE_5X20, px + 18, py, pins=2))
    d.add(
        Comp(
            "L2",
            "Fiberboard:CM_Choke_4",
            "ACM2012",
            "Inductor_SMD:L_CommonModeChoke_Coilank_ACM2012",
            px + 32,
            py,
            pins=4,
        )
    )
    d.add(
        Comp(
            "RV1",
            "Device:R",
            "MOV-26V",
            "Varistor:Varistor_Panasonic_VF",
            px + 48,
            py + 14,
            pins=2,
        )
    )
    d.add(Comp("D7", "Device:D_TVS", "SMAJ28A", "Diode_SMD:D_SMA", px + 48, py + 28, pins=2))
    d.add(Comp("C19", "Device:C", "10uF", "Capacitor_SMD:C_0805_2012Metric", px + 62, py + 14, pins=2))
    d.add(Comp("Q12", "Transistor_FET:Q_PMOS_GSD", "AO4407A", "Package_TO_SOT_SMD:SOT-23", px + 48, py, pins=3))
    d.add(Comp("R17", "Device:R", "100k", "Resistor_SMD:R_0805_2012Metric", px + 48, py + 18, pins=2))
    d.add(Comp("C15", "Device:C", "100nF", "Capacitor_SMD:C_0805_2012Metric", px + 34, py, pins=2))
    d.add(Comp("C4", "Device:C", "1000uF", "Capacitor_SMD:CP_Elec_10x12.5", px + 64, py, pins=2))
    d.add(
        Comp(
            "NT1",
            "Fiberboard:NetTie_2",
            "GND_STAR",
            "NetTie:NetTie-2_SMD_Pad2.0mm",
            px + 64,
            py + 14,
            pins=2,
        )
    )
    d.add(Comp("C14", "Device:C", "100nF", "Capacitor_SMD:C_0805_2012Metric", px + 78, py, pins=2))
    d.add(Comp("FB3", "Device:L", "BLM21PG121", "Inductor_SMD:L_0805_2012Metric", px + 70, py + 22, pins=2))
    d.add(Comp("D11", "Device:D_TVS", "SMAJ5.0A", "Diode_SMD:D_SMA", px + 58, py + 22, pins=2))
    d.add(Comp("C23", "Device:C", "100nF", "Capacitor_SMD:C_0805_2012Metric", px + 52, py + 22, pins=2))
    # --- Buck 24V -> 5V (XL1509) ---
    bx, by = px + 88, py
    d.add(Comp("U2", "Regulator_Switching:XL1509-5.0", "XL1509-5.0", "Package_TO_SOT_SMD:TO-263-5_TabPin3", bx, by, pins=5))
    d.add(Comp("C16", "Device:C", "10uF", "Capacitor_SMD:C_0805_2012Metric", bx - 12, by, pins=2))
    d.add(Comp("C17", "Device:C", "100nF", "Capacitor_SMD:C_0805_2012Metric", bx - 12, by + 12, pins=2))
    d.add(Comp("D8", "Device:D", "SS34", "Diode_SMD:D_SOD-123", bx + 14, by + 14, pins=2))
    d.add(Comp("L1", "Device:L", "47uH", "Inductor_SMD:L_1210_3225Metric", bx + 28, by, pins=2))
    d.add(Comp("C2", "Device:C", "220uF", "Capacitor_SMD:CP_Elec_6.3x5.4", bx + 44, by, pins=2))
    d.add(Comp("C5", "Device:C", "100nF", "Capacitor_SMD:C_0805_2012Metric", bx + 44, by + 12, pins=2))
    d.add(Comp("R36", "Device:R", "3k", "Resistor_SMD:R_0805_2012Metric", bx + 20, by + 26, pins=2))
    d.add(Comp("R37", "Device:R", "1k", "Resistor_SMD:R_0805_2012Metric", bx + 8, by + 26, pins=2))
    d.add(Comp("R38", "Device:R", "10k", "Resistor_SMD:R_0805_2012Metric", bx, by + 12, pins=2))
    # --- LDO 5V -> 3.3V (AMS1117) for ESP32 + logic ---
    d.add(Comp("U3", "Regulator_Linear:AMS1117-3.3", "AMS1117-3.3", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", bx + 62, by, pins=3))
    d.add(Comp("C7", "Device:C", "10uF", "Capacitor_SMD:C_0805_2012Metric", bx + 56, by, pins=2))
    d.add(Comp("C3", "Device:C", "22uF", "Capacitor_SMD:C_0805_2012Metric", bx + 78, by, pins=2))
    d.add(Comp("C18", "Device:C", "100nF", "Capacitor_SMD:C_0805_2012Metric", bx + 78, by + 12, pins=2))
    d.add(Comp("FB1", "Device:L", "BLM21PG121", "Inductor_SMD:L_0805_2012Metric", bx + 72, by + 24, pins=2))
    d.add(Comp("C21", "Device:C", "100nF", "Capacitor_SMD:C_0805_2012Metric", bx + 84, by + 24, pins=2))
    d.add(Comp("FB2", "Device:L", "BLM21PG121", "Inductor_SMD:L_0805_2012Metric", bx + 44, by + 24, pins=2))
    d.add(Comp("C22", "Device:C", "220uF", "Capacitor_SMD:CP_Elec_6.3x5.4", bx + 56, by + 24, pins=2))
    d.add(Comp("FB4", "Device:L", "BLM21PG121", "Inductor_SMD:L_0805_2012Metric", bx + 56, by + 38, pins=2))
    d.add(Comp("F2", "Device:Fuse", "5x20 F0.5A", FP_FUSE_5X20, bx + 70, by + 38, pins=2))
    d.add(Comp("D12", "Device:D_TVS", "SMAJ5.0A", "Diode_SMD:D_SMA", bx + 84, by + 38, pins=2))
    d.add(Comp("C24", "Device:C", "220uF", "Capacitor_SMD:CP_Elec_6.3x5.4", bx + 98, by + 38, pins=2))
    d.add(Comp("C25", "Device:C", "100nF", "Capacitor_SMD:C_0805_2012Metric", bx + 98, by + 50, pins=2))
    d.add(Comp("#PWR24", "power:+24V", "+24V", "", px + 64, 12, pins=1))
    d.add(Comp("#PWR5", "power:+5V", "+5V", "", bx + 44, 12, pins=1))
    d.add(Comp("#PWR33", "power:+3V3", "+3V3", "", bx + 78, 12, pins=1))
    d.add(Comp("#GND1", "power:GND", "GND", "", px + 70, 48, pins=1))
    d.add(Comp("#FLG_GNDP", "power:PWR_FLAG", "", "", px + 78, py + 22, pins=1))

    d.connect("VIN_RAW", ("J1", "1"), ("F1", "1"))
    d.connect("VIN_CM_IN", ("F1", "2"), ("L2", "1"))
    d.connect("VIN_CM_RET", ("J1", "2"), ("L2", "3"))
    d.connect(
        "VIN_FUSE",
        ("L2", "2"),
        ("D7", "1"),
        ("RV1", "1"),
        ("Q12", "2"),
        ("C15", "1"),
        ("C19", "1"),
    )
    d.connect("GND_PWR", ("L2", "4"), ("D7", "2"), ("RV1", "2"), ("C19", "2"))
    # Split ground: switching / 24V return (GND_PWR) vs logic (GND), star at C4 bulk + NT1
    d.connect("GND_SPLICE", ("NT1", "2"), ("D11", "2"), ("C23", "2"), ("FB3", "1"))
    d.connect(
        "GND_PWR",
        ("C15", "2"),
        ("C14", "2"),
        ("C4", "2"),
        ("NT1", "1"),
        ("D11", "1"),
        ("C23", "1"),
        ("U2", "5"),
        ("C16", "2"),
        ("C17", "2"),
        ("D8", "2"),
        ("R37", "2"),
        ("R17", "2"),
        ("Q3", "1"),
        ("Q4", "1"),
        ("Q5", "2"),
        ("R14", "2"),
        ("J4", "3"),
        ("J2", "2"),
        ("#FLG_GNDP", "1"),
    )
    d.connect(
        "GND",
        ("#GND1", "1"),
        ("FB3", "2"),
        ("C2", "2"),
        ("C3", "2"),
        ("C5", "2"),
        ("C22", "2"),
        ("C7", "2"),
        ("C18", "2"),
        ("U3", "1"),
    )
    d.connect("FET_G", ("Q12", "1"), ("R17", "1"))
    d.connect(
        "+24V",
        ("#PWR24", "1"),
        ("Q12", "3"),
        ("C4", "1"),
        ("C14", "1"),
        ("U2", "1"),
        ("C16", "1"),
        ("C17", "1"),
        ("R38", "1"),
        ("J2", "1"),
    )
    # XL1509 async buck: SW -> L -> +5V ; Schottky K=SW A=GND ; FB divider ~5V
    d.connect("+5V_SW", ("U2", "2"), ("L1", "1"), ("D8", "1"))
    d.connect("+5V_RAW", ("L1", "2"), ("C2", "1"), ("C5", "1"), ("FB2", "1"))
    d.connect(
        "+5V",
        ("FB2", "2"),
        ("C22", "1"),
        ("C7", "1"),
        ("#PWR5", "1"),
        ("U3", "3"),
        ("R36", "1"),
        ("FB4", "1"),
    )
    d.connect("+5V_RLY", ("FB4", "2"), ("F2", "1"))
    d.connect(
        "+5V_RLY",
        ("F2", "2"),
        ("D12", "1"),
        ("C24", "1"),
        ("C25", "1"),
    )
    d.connect("GND_PWR", ("D12", "2"), ("C24", "2"), ("C25", "2"))
    d.connect("+3V3_REG", ("U3", "2"), ("C3", "1"), ("C18", "1"), ("FB1", "1"))
    d.connect("+3V3", ("FB1", "2"), ("C21", "1"), ("#PWR33", "1"))
    d.connect("BUCK_FB", ("U2", "3"), ("R36", "2"), ("R37", "1"))
    d.connect("BUCK_EN", ("U2", "4"), ("R38", "2"))  # EN pull-up R38 to +24V
    d.connect("GND", ("C21", "2"))

    # ========== ESP32 ==========
    d.add(Comp("U1", "Fiberboard:ESP32_DevKitC_Socket", "ESP32-DevKitC-32E", "Fiberboard:ESP32_DevKitC_Socket", 70, 130, pins=38))
    # Kéo xuống khi không lắp opto (OPT_J3/J4 DNP) — song song R9/R10 trong nhóm opto.
    d.add(Comp("R20", "Device:R", "100k", "Resistor_SMD:R_0805_2012Metric", 62, 118, pins=2))
    d.add(Comp("R21", "Device:R", "100k", "Resistor_SMD:R_0805_2012Metric", 62, 122, pins=2))
    d.connect("+3V3", ("U1", "1"))
    d.connect("+5V", ("U1", "19"))
    # DevKitC-32E J2: 13=IO12 (để trống, chân strap), 14=GND, 15=IO13. J3: 20/26=GND
    d.connect("GND", ("U1", "14"), ("U1", "20"), ("U1", "26"))
    d.connect("FIBER1_PWM", ("U1", "7"))   # IO32 -> AFBR-1624Z TX
    d.connect("FIBER2_PWM", ("U1", "8"))   # IO33
    d.connect("IN_FOOT", ("U1", "9"))     # IO25
    d.connect("IN_NPN", ("U1", "10"))     # IO26
    d.connect("OUT_RLY1", ("U1", "11"))   # IO27
    d.connect("OUT_RLY2", ("U1", "12"))   # IO14
    d.connect("OUT_MOS", ("U1", "15"))    # IO13
    d.connect("I2C_SCL", ("U1", "22"))    # IO22
    d.connect("I2C_SDA", ("U1", "25"))    # IO21
    d.connect("RS485_TX", ("U1", "21"))   # IO23
    d.connect("RS485_RX", ("U1", "31"))   # IO16
    d.connect("RS485_DE", ("U1", "30"))   # IO17
    d.connect("FIBER1_DIG", ("U1", "32")) # IO4
    d.connect("FIBER2_DIG", ("U1", "35")) # IO15
    # EN pull-up
    d.connect("+3V3", ("U1", "2"))
    # ========== FIBER (2ch) — Broadcom Versatile Link on PCB, 1 mm POF plug-in ==========
    # TX AFBR-1624Z: VCC, TTL data in (PWM), GND | RX AFBR-2624Z: VCC, TTL out, mount, GND
    bx, by = 200, 40
    d.add(
        Comp(
            "F1T",
            "Fiberboard:AFBR_1624Z",
            "AFBR-1624Z",
            "Fiberboard:AFBR_1624Z_VL",
            bx,
            by,
            pins=5,
        )
    )
    d.add(
        Comp(
            "F1R",
            "Fiberboard:AFBR_2624Z",
            "AFBR-2624Z",
            "Fiberboard:AFBR_2624Z_VL",
            bx + 28,
            by,
            pins=6,
        )
    )
    d.add(Comp("C12", "Device:C", "100nF", "Capacitor_SMD:C_0805_2012Metric", bx + 14, by + 18, pins=2))
    d.connect("+5V", ("F1T", "1"), ("F1R", "3"), ("C12", "1"))
    d.connect("FIBER1_PWM", ("F1T", "4"))
    d.connect("GND", ("F1T", "3"), ("F1T", "5"), ("F1T", "8"), ("F1R", "2"), ("F1R", "4"), ("F1R", "5"), ("F1R", "8"), ("C12", "2"))
    d.connect("FIBER1_DIG", ("F1R", "1"))

    bx2 = 320
    d.add(
        Comp(
            "F2T",
            "Fiberboard:AFBR_1624Z",
            "AFBR-1624Z",
            "Fiberboard:AFBR_1624Z_VL",
            bx2,
            by,
            pins=5,
        )
    )
    d.add(
        Comp(
            "F2R",
            "Fiberboard:AFBR_2624Z",
            "AFBR-2624Z",
            "Fiberboard:AFBR_2624Z_VL",
            bx2 + 28,
            by,
            pins=6,
        )
    )
    d.add(Comp("C13", "Device:C", "100nF", "Capacitor_SMD:C_0805_2012Metric", bx2 + 14, by + 18, pins=2))
    d.connect("+5V", ("F2T", "1"), ("F2R", "3"), ("C13", "1"))
    d.connect("FIBER2_PWM", ("F2T", "4"))
    d.connect("GND", ("F2T", "3"), ("F2T", "5"), ("F2T", "8"), ("F2R", "2"), ("F2R", "4"), ("F2R", "5"), ("F2R", "8"), ("C13", "2"))
    d.connect("FIBER2_DIG", ("F2R", "1"))

    # ========== DIGITAL IN FOOT / NPN ==========
    dx, dy = 30, 220
    d.add(Comp("J3", "Fiberboard:Screw_Terminal_01x02", "FOOT", FP_EDG_2P, dx, dy, pins=2))
    d.add(Comp("R7", "Device:R", "1k", "Resistor_SMD:R_0805_2012Metric", dx + 30, dy, pins=2))
    d.add(Comp("U5", "Fiberboard:PC817", "PC817", "Fiberboard:PC817_SO4", dx + 55, dy, pins=4))
    d.add(Comp("R9", "Device:R", "10k", "Resistor_SMD:R_0805_2012Metric", dx + 85, dy, pins=2))
    # Foot: J3.1 - R7 - U5 LED (1-2); phototransistor (4) - R9 - +3V3 & IN_FOOT ; pin 3 = GND
    d.connect("FOOT_A", ("J3", "1"), ("R7", "1"))
    d.connect("FOOT_LED", ("R7", "2"), ("U5", "1"))
    d.connect("FOOT_K", ("J3", "2"), ("U5", "2"))
    d.connect("GND", ("U5", "3"))
    d.connect("+3V3", ("R9", "1"))
    d.connect("IN_FOOT", ("R9", "2"), ("U5", "4"), ("R20", "1"))
    d.connect("GND", ("R20", "2"))

    d.add(Comp("J4", "Fiberboard:Screw_Terminal_01x03", "NPN", FP_EDG_3P, dx + 130, dy, pins=3))
    d.add(Comp("R8", "Device:R", "1k", "Resistor_SMD:R_0805_2012Metric", dx + 170, dy, pins=2))
    d.add(Comp("U6", "Fiberboard:PC817", "PC817", "Fiberboard:PC817_SO4", dx + 195, dy, pins=4))
    d.add(Comp("R10", "Device:R", "10k", "Resistor_SMD:R_0805_2012Metric", dx + 225, dy, pins=2))
    # J4:1=+24V, J4:2=SIG, J4:3=GND(field) — SIG via R8 to opto LED
    d.connect("NPN_V+", ("J4", "1"))
    d.connect("NPN_SIG", ("J4", "2"), ("R8", "1"))
    d.connect("NPN_LED", ("R8", "2"), ("U6", "1"))
    d.connect("GND", ("U6", "3"))
    d.connect("GND_PWR", ("U6", "2"), ("J4", "3"))
    d.connect("+3V3", ("R10", "1"))
    d.connect("IN_NPN", ("R10", "2"), ("U6", "4"), ("R21", "1"))
    d.connect("GND", ("R21", "2"))

    # ========== RELAYS ==========
    rx, ry = 30, 280
    d.add(Comp("R11", "Device:R", "1k", "Resistor_SMD:R_0805_2012Metric", rx, ry, pins=2))
    d.add(Comp("Q3", "Transistor_BJT:2N3904", "2N3904", "Package_TO_SOT_SMD:SOT-23", rx + 25, ry, pins=3))
    d.add(Comp("D3", "Device:D", "SS34", "Diode_SMD:D_SOD-123", rx + 50, ry - 15, pins=2))
    d.add(Comp("K1", "Fiberboard:G5LE-1", "G6KU-2F-Y", "Fiberboard:G6KU-2F_SMD", rx + 70, ry, pins=5))
    d.add(Comp("J5", "Fiberboard:Screw_Terminal_01x03", "RLY1", FP_EDG_3P, rx + 70, ry + 35, pins=3))
    d.connect("OUT_RLY1", ("R11", "1"))
    d.connect("RLY1_B", ("R11", "2"), ("Q3", "2"))
    # Flyback: Device:D pin1=K to +5V, pin2=A to switched coil end
    d.connect("+5V_RLY", ("K1", "1"), ("D3", "1"))
    d.connect("RLY1_COIL", ("K1", "2"), ("Q3", "3"), ("D3", "2"))
    d.connect("RLY1_COM", ("K1", "4"), ("J5", "1"))
    d.connect("RLY1_NO", ("K1", "3"), ("J5", "2"))
    d.connect("RLY1_NC", ("K1", "5"), ("J5", "3"))

    d.add(Comp("R12", "Device:R", "1k", "Resistor_SMD:R_0805_2012Metric", rx + 140, ry, pins=2))
    d.add(Comp("Q4", "Transistor_BJT:2N3904", "2N3904", "Package_TO_SOT_SMD:SOT-23", rx + 165, ry, pins=3))
    d.add(Comp("D4", "Device:D", "SS34", "Diode_SMD:D_SOD-123", rx + 190, ry - 15, pins=2))
    d.add(Comp("K2", "Fiberboard:G5LE-1", "G6KU-2F-Y", "Fiberboard:G6KU-2F_SMD", rx + 210, ry, pins=5))
    d.add(Comp("J6", "Fiberboard:Screw_Terminal_01x03", "RLY2", FP_EDG_3P, rx + 210, ry + 35, pins=3))
    d.connect("OUT_RLY2", ("R12", "1"))
    d.connect("RLY2_B", ("R12", "2"), ("Q4", "2"))
    d.connect("+5V_RLY", ("K2", "1"), ("D4", "1"))
    d.connect("RLY2_COIL", ("K2", "2"), ("Q4", "3"), ("D4", "2"))
    d.connect("RLY2_COM", ("K2", "4"), ("J6", "1"))
    d.connect("RLY2_NO", ("K2", "3"), ("J6", "2"))
    d.connect("RLY2_NC", ("K2", "5"), ("J6", "3"))

    # ========== MOSFET SOLENOID ==========
    mx, my = 320, 280
    d.add(Comp("R13", "Device:R", "100", "Resistor_SMD:R_0805_2012Metric", mx, my, pins=2))
    d.add(Comp("R14", "Device:R", "10k", "Resistor_SMD:R_0805_2012Metric", mx, my + 20, pins=2))
    d.add(Comp("Q5", "Transistor_FET:AO3400A", "AO3400A", "Package_TO_SOT_SMD:SOT-23", mx + 30, my, pins=3))
    d.add(Comp("D5", "Device:D", "SS34", "Diode_SMD:D_SOD-123", mx + 55, my, pins=2))
    d.add(Comp("F3", "Device:Fuse", "5x20 F0.25A", FP_FUSE_5X20, mx + 65, my, pins=2))
    d.add(Comp("J7", "Fiberboard:Screw_Terminal_01x02", "SOL", FP_EDG_2P, mx + 80, my, pins=2))
    d.connect("OUT_MOS", ("R13", "1"))
    d.connect("MOS_G", ("R13", "2"), ("Q5", "1"), ("R14", "1"))
    # Solenoid between J7.1 (+12V) and J7.2 (low side switched by Q5); D5 = flyback
    d.connect("+24V_SOL", ("F3", "2"), ("J7", "1"), ("D5", "1"))
    d.connect("+24V", ("F3", "1"))
    d.connect("SOL_LO", ("Q5", "3"), ("D5", "2"), ("J7", "2"))

    # ========== RS485 ==========
    sx, sy = 420, 280
    d.add(Comp("U7", "Interface_UART:MAX485E", "MAX485E", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", sx, sy, pins=8))
    d.add(Comp("R15", "Device:R", "100", "Resistor_SMD:R_0805_2012Metric", sx + 35, sy, pins=2))
    d.add(Comp("R18", "Device:R", "10R", "Resistor_SMD:R_0805_2012Metric", sx + 48, sy - 12, pins=2))
    d.add(Comp("R19", "Device:R", "10R", "Resistor_SMD:R_0805_2012Metric", sx + 58, sy - 12, pins=2))
    d.add(Comp("D9", "Device:D_TVS", "SMAJ5.0A", "Diode_SMD:D_SMA", sx + 48, sy + 18, pins=2))
    d.add(Comp("D10", "Device:D_TVS", "SMAJ5.0A", "Diode_SMD:D_SMA", sx + 58, sy + 18, pins=2))
    # 2EDG5.08-3P socket — cắm đực 2EDG + dây xoắn đôi field (Modbus RTU)
    d.add(
        Comp(
            "J8",
            "Fiberboard:Screw_Terminal_01x03",
            "RS485-2EDG3P",
            FP_EDG_3P,
            sx + 60,
            sy,
            pins=3,
        )
    )
    d.connect("+5V", ("U7", "8"))
    d.connect("GND", ("U7", "5"), ("J8", "3"))
    d.connect("RS485_RX", ("U7", "1"))
    d.connect("RS485_DE", ("U7", "2"), ("U7", "3"))  # RE# and DE tied
    d.connect("RS485_TX", ("U7", "4"))
    d.connect("RS485_A", ("U7", "6"), ("R18", "1"))
    d.connect("RS485_A_BUS", ("R18", "2"), ("R15", "1"), ("J8", "1"), ("D9", "1"))
    d.connect("RS485_B", ("U7", "7"), ("R19", "1"))
    d.connect("RS485_B_BUS", ("R19", "2"), ("R15", "2"), ("J8", "2"), ("D10", "1"))
    d.connect("GND", ("D9", "2"), ("D10", "2"))

    # ========== STATUS LED (no on-board OLED header) ==========
    d.add(Comp("R16", "Device:R", "1k", "Resistor_SMD:R_0805_2012Metric", sx + 40, sy + 50, pins=2))
    d.add(Comp("D6", "Device:LED", "STATUS", "LED_SMD:LED_0805_2012Metric", sx + 60, sy + 50, pins=2))
    d.connect("GND", ("D6", "1"))
    d.connect("+3V3", ("R16", "1"))
    d.connect("STAT_LED", ("R16", "2"), ("D6", "2"))

    from assembly_groups import omitted_refs

    drop = omitted_refs()
    if drop:
        d.comps = [c for c in d.comps if c.ref not in drop]
        for net in list(d.nets):
            kept = [p for p in d.nets[net] if p[0] not in drop]
            if kept:
                d.nets[net] = kept
            else:
                del d.nets[net]
    return d


def net_index_map(design: Design) -> dict[str, int]:
    """Assign net numbers; 0 = empty."""
    nets = sorted(design.nets.keys())
    return {n: i + 1 for i, n in enumerate(nets)}


def find_comp(design: Design, ref: str, pin: str) -> Comp | None:
    """Resolve component placement for a pin (handles multi-unit LM358/LM393)."""
    cands = [c for c in design.comps if c.ref == ref]
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    unit_for_pin = {
        "1": 1,
        "2": 1,
        "3": 1,
        "5": 2,
        "6": 2,
        "7": 2,
        "4": 3,
        "8": 3,
    }
    want = unit_for_pin.get(pin)
    if want is not None:
        for c in cands:
            if c.unit == want:
                return c
    return cands[0]


def label_shape(net: str) -> str:
    if net in {"GND", "GND_PWR"}:
        return "passive"
    if net.startswith("+") or net in {"+3V3", "+5V", "+5V_RLY", "+24V", "+24V_SOL", "+5V_SW"}:
        return "input"
    if net.endswith("_PWM") or net.endswith("_TX") or net.startswith("OUT_"):
        return "output"
    if net.endswith("_ADC") or net.endswith("_DIG") or net.startswith("IN_"):
        return "input"
    return "passive"


def wire_chains_for_net(
    design: Design, net: str, max_dist: float = 80.0
) -> list[tuple[float, float, float, float]]:
    """Connect nearby pins on same net with wires (visual + electrical)."""
    pts = []
    for ref, pin in design.nets[net]:
        c = find_comp(design, ref, pin)
        if not c:
            continue
        pts.append(pin_abs(c, pin))
    # greedy nearest-neighbor chain
    if len(pts) < 2:
        return []
    remaining = pts[1:]
    cur = pts[0]
    ordered = [cur]
    while remaining:
        nxt = min(remaining, key=lambda p: (p[0] - cur[0]) ** 2 + (p[1] - cur[1]) ** 2)
        remaining.remove(nxt)
        ordered.append(nxt)
        cur = nxt
    segs = []
    for a, b in zip(ordered, ordered[1:]):
        dist = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
        if dist <= max_dist:
            # Manhattan for readability
            if abs(a[0] - b[0]) > 0.01 and abs(a[1] - b[1]) > 0.01:
                mid = (b[0], a[1])
                segs.append((a[0], a[1], mid[0], mid[1]))
                segs.append((mid[0], mid[1], b[0], b[1]))
            else:
                segs.append((a[0], a[1], b[0], b[1]))
    return segs
