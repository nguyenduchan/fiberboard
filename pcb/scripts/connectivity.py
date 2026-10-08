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
        **{p: (0.0, -7.62) for p in ("5", "6", "7", "8")},
    },
    "Transistor_FET:AO3401A": {"1": (-5.08, 0.0), "2": (2.54, -5.08), "3": (2.54, 5.08)},  # G,S,D
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
    # --- rev B: linh kiện phổ biến (tọa độ chân lấy từ thư viện KiCad 10) ---
    "RF_Module:ESP32-C3-WROOM-02": {
        "1": (0.0, 22.86),
        "2": (-15.24, 17.78),
        "3": (-15.24, 2.54),
        "4": (-15.24, 0.0),
        "5": (-15.24, -2.54),
        "6": (-15.24, -5.08),
        "7": (-15.24, -7.62),
        "8": (-15.24, -10.16),
        "9": (0.0, -22.86),
        "10": (-15.24, -12.7),
        "11": (15.24, 17.78),
        "12": (15.24, 15.24),
        "13": (-15.24, -15.24),
        "14": (-15.24, -17.78),
        "15": (-15.24, 5.08),
        "16": (-15.24, 7.62),
        "17": (-15.24, 10.16),
        "18": (-15.24, 12.7),
        "19": (0.0, -22.86),
    },
    # 1=COM, 2/5=cuộn, 3=NO, 4=NC (Form A giữ chân 3, Form B giữ chân 4)
    "Relay:SANYOU_SRD_Form_C": {
        "1": (5.08, -7.62),
        "2": (-5.08, -7.62),
        "3": (7.62, 7.62),
        "4": (2.54, 7.62),
        "5": (-5.08, 7.62),
    },
    "Connector:USB_C_Receptacle_USB2.0_16P": {
        **{p: (0.0, -22.86) for p in ("A1", "B1", "A12", "B12")},
        **{p: (15.24, 15.24) for p in ("A4", "A9", "B4", "B9")},
        "A5": (15.24, 10.16),
        "B5": (15.24, 7.62),
        "A6": (15.24, -2.54),
        "B6": (15.24, -5.08),
        "A7": (15.24, 2.54),
        "B7": (15.24, 0.0),
        "A8": (15.24, -12.7),
        "B8": (15.24, -15.24),
        "SH": (-7.62, -22.86),
    },
    "Power_Protection:USBLC6-2SC6": {
        "1": (-5.08, 0.0),
        "2": (0.0, -7.62),
        "3": (-5.08, -2.54),
        "4": (5.08, -2.54),
        "5": (0.0, 5.08),
        "6": (5.08, 0.0),
    },
    "Diode:SM712_SOT23": {"1": (-8.89, 0.0), "2": (8.89, 0.0), "3": (0.0, -3.81)},
    "Transistor_BJT:MMBT3904": {"1": (-5.08, 0.0), "2": (2.54, -5.08), "3": (2.54, 5.08)},  # B,E,C
    "Device:D_Zener": {"1": (-3.81, 0.0), "2": (3.81, 0.0)},  # 1=K, 2=A
    "Device:D_Schottky": {"1": (-3.81, 0.0), "2": (3.81, 0.0)},  # 1=K, 2=A
    "Switch:SW_Push": {"1": (-5.08, 0.0), "2": (5.08, 0.0)},
    "Regulator_Switching:XL1509-3.3": {
        "1": (-10.16, 2.54),
        "2": (10.16, 2.54),
        "3": (10.16, -2.54),
        "4": (-10.16, -2.54),
        **{p: (0.0, -7.62) for p in ("5", "6", "7", "8")},
    },
    "Interface_UART:MAX3485": {
        "1": (-10.16, 5.08),
        "2": (-10.16, 2.54),
        "3": (-10.16, 0.0),
        "4": (-10.16, -5.08),
        "5": (0.0, -15.24),
        "6": (10.16, 7.62),
        "7": (10.16, 2.54),
        "8": (0.0, 15.24),
    },
    # SO-8 P-FET chuẩn SSSGDDDD (AO4407A cùng chân)
    "Transistor_FET:FDS9435A": {
        **{p: (2.54, -5.08) for p in ("1", "2", "3")},
        "4": (-5.08, 0.0),
        **{p: (2.54, 5.08) for p in ("5", "6", "7", "8")},
    },
}

# Chân USB-C 16P theo symbol KiCad (không đánh số 1..N).
USB_C_PINS = [
    "A1", "A4", "A5", "A6", "A7", "A8", "A9", "A12",
    "B1", "B4", "B5", "B6", "B7", "B8", "B9", "B12", "SH",
]
# Chân để trống có chủ đích (cờ no-connect trên sơ đồ).
NC_PINS: dict[str, list[str]] = {"J11": ["A4", "A9", "B4", "B9", "A8", "B8"]}


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
    lcsc: str = ""

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
    """Full board connectivity — schematic coordinates (mm), readable layout.

    Rev B (linh kiện phổ biến): ESP32-C3-WROOM-02 hàn thẳng + USB-C, một buck XL1509-3.3,
    relay SRD/HF3FF cuộn 24 V, 4 đầu vào NPN cách ly (FOOT, NPN, AMP1, AMP2), RS485 3,3 V.
    """
    d = Design()
    fp_r = "Resistor_SMD:R_0805_2012Metric"
    fp_c = "Capacitor_SMD:C_0805_2012Metric"
    fp_c1206 = "Capacitor_SMD:C_1206_3216Metric"
    fp_led = "LED_SMD:LED_0805_2012Metric"
    fp_sod = "Diode_SMD:D_SOD-123"
    fp_sma = "Diode_SMD:D_SMA"
    fp_sot = "Package_TO_SOT_SMD:SOT-23"
    fp_opto = "Package_DIP:SMDIP-4_W9.53mm"

    def lamp(led: str, res: str, name: str, rval: str, x: float, y: float) -> None:
        d.add(Comp(res, "Device:R", rval, fp_r, x, y, pins=2))
        d.add(Comp(led, "Device:LED", name, fp_led, x + 14, y, pins=2))

    # ========== NGUỒN VÀO 24 V + BẢO VỆ ==========
    # J1 -> F1 (5x20 có nắp) -> TVS D7 -> P-FET Q12 chống ngược cực -> +24V (C4 bulk)
    # Q12 AO3401A: D phía vào, S phía tải (diode thân dẫn đúng chiều). Cổng lấy từ cầu
    # R63 (G-S 10k) / R17 (G-mass 27k): Vgs = -24*10/37 = -6,5 V; -11,4 V khi TVS kẹp 42 V
    # (AO3401A chịu ±12 V) -> không cần zener (không có zener trong thư viện Basic JLC).
    px, py = 20, 30
    d.add(Comp("J1", "Fiberboard:Screw_Terminal_01x02", "VIN", FP_EDG_2P, px, py, pins=2))
    d.add(Comp("J2", "Fiberboard:Screw_Terminal_01x02", "KB24", FP_EDG_2P, px, py + 40, pins=2))
    d.add(Comp("F1", "Device:Fuse", "5x20 su 4A", "Fiberboard:Fuseholder_5x20mm_Covered", px + 18, py, pins=2))
    d.add(Comp("D7", "Device:D_TVS", "SMAJ26A", fp_sma, px + 34, py + 14, pins=2))
    d.add(Comp("C15", "Device:C", "100nF 50V", fp_c, px + 44, py + 14, pins=2))
    d.add(Comp("Q12", "Transistor_FET:AO3401A", "AO3401A", fp_sot, px + 56, py, pins=3))
    d.add(Comp("R17", "Device:R", "27k", fp_r, px + 52, py + 16, pins=2))
    d.add(Comp("R63", "Device:R", "10k", fp_r, px + 64, py + 16, pins=2))
    d.add(Comp("C4", "Device:C", "470uF 35V", "Capacitor_SMD:CP_Elec_10x10.5", px + 76, py + 8, pins=2))
    d.add(Comp("C14", "Device:C", "100nF 50V", fp_c, px + 86, py + 8, pins=2))
    lamp("D27", "R39", "24V", "10k", px + 76, py + 26)
    d.add(Comp("#PWR24", "power:+24V", "+24V", "", px + 76, 14, pins=1))
    d.add(Comp("#FLG_GNDP", "power:PWR_FLAG", "", "", px + 34, py + 30, pins=1))

    d.connect("VIN_RAW", ("J1", "1"), ("F1", "1"))
    d.connect("VIN_FUSE", ("F1", "2"), ("D7", "1"), ("C15", "1"), ("Q12", "3"))
    d.connect("FET_G", ("Q12", "1"), ("R17", "1"), ("R63", "2"))
    d.connect(
        "+24V",
        ("#PWR24", "1"),
        ("Q12", "2"),
        ("R63", "1"),
        ("C4", "1"),
        ("C14", "1"),
        ("R39", "1"),
        ("J2", "1"),
    )
    d.connect("P24_AN", ("R39", "2"), ("D27", "2"))
    d.connect(
        "GND_PWR",
        ("J1", "2"),
        ("J2", "2"),
        ("D7", "2"),
        ("C15", "2"),
        ("R17", "2"),
        ("C4", "2"),
        ("C14", "2"),
        ("D27", "1"),
        ("#FLG_GNDP", "1"),
    )

    # ========== BUCK 24 V -> 5 V (XL1509-5.0) + LDO 3,3 V (AMS1117) ==========
    # Cả hai là mã Basic của JLC. ~EN nối mass = luôn chạy; FB nối thẳng ra 5 V (bản cố định).
    # LDO chỉ tụt 1,7 V x ~0,1 A trung bình (đỉnh WiFi ~0,35 A) -> SOT-223 đủ.
    bx, by = 140, 30
    d.add(Comp("U2", "Regulator_Switching:XL1509-5.0", "XL1509-5.0", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", bx, by, pins=8))
    d.add(Comp("C16", "Device:C", "10uF 50V", fp_c1206, bx - 22, by, pins=2))
    d.add(Comp("C17", "Device:C", "100nF 50V", fp_c, bx - 14, by + 14, pins=2))
    d.add(Comp("D8", "Device:D_Schottky", "SS34", fp_sma, bx + 18, by + 16, pins=2))
    d.add(Comp("L1", "Device:L", "47uH 6045", "Inductor_SMD:L_Sunlord_SWPA6045S", bx + 30, by, pins=2))
    d.add(Comp("C2", "Device:C", "220uF 10V", "Capacitor_SMD:CP_Elec_6.3x5.4", bx + 44, by + 8, pins=2))
    d.add(Comp("C5", "Device:C", "100nF", fp_c, bx + 54, by + 8, pins=2))
    d.add(Comp("U3", "Regulator_Linear:AMS1117-3.3", "AMS1117-3.3", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", bx + 70, by, pins=3))
    d.add(Comp("C7", "Device:C", "10uF", fp_c, bx + 62, by + 12, pins=2))
    d.add(Comp("C3", "Device:C", "22uF", fp_c, bx + 80, by + 12, pins=2))
    d.add(Comp("C18", "Device:C", "100nF", fp_c, bx + 90, by + 12, pins=2))
    lamp("D6", "R16", "3V3", "1k", bx + 44, by + 26)
    # Sao mass: GND_PWR (nguồn, relay, van, phía hiện trường) gặp GND (logic) tại NT1.
    d.add(Comp("NT1", "Fiberboard:NetTie_2", "GND_STAR", "NetTie:NetTie-2_SMD_Pad2.0mm", bx + 10, by + 30, pins=2))
    d.add(Comp("#PWR5", "power:+5V", "+5V", "", bx + 44, 14, pins=1))
    d.add(Comp("#PWR33", "power:+3V3", "+3V3", "", bx + 80, 14, pins=1))
    d.add(Comp("#GND1", "power:GND", "GND", "", bx + 24, by + 40, pins=1))

    d.connect("+24V", ("U2", "1"), ("C16", "1"), ("C17", "1"))
    d.connect("BUCK_SW", ("U2", "2"), ("L1", "1"), ("D8", "1"))
    d.connect("+5V", ("L1", "2"), ("U2", "3"), ("C2", "1"), ("C5", "1"), ("U3", "3"), ("C7", "1"), ("#PWR5", "1"))
    d.connect("+3V3", ("U3", "2"), ("C3", "1"), ("C18", "1"), ("R16", "1"), ("#PWR33", "1"))
    d.connect("P3V3_AN", ("R16", "2"), ("D6", "2"))
    d.connect(
        "GND_PWR",
        ("U2", "4"),
        *[("U2", p) for p in "5678"],
        ("C16", "2"),
        ("C17", "2"),
        ("D8", "2"),
        ("C2", "2"),
        ("C5", "2"),
        ("NT1", "1"),
    )
    d.connect("GND", ("NT1", "2"), ("#GND1", "1"), ("D6", "1"), ("U3", "1"), ("C7", "2"), ("C3", "2"), ("C18", "2"))

    # ========== MCU: ESP32-C3-WROOM-02 (chân răng cưa, hàn tay được) ==========
    # GPIO tránh chân strapping (2, 8, 9) cho vào/ra. IO8 = đèn RUN (kéo lên), IO9 = nút BOOT.
    # IO18/IO19 = USB D-/D+ (USB-Serial-JTAG: nạp và log, không cần chip USB-UART).
    mx, my = 110, 150
    d.add(Comp("U1", "RF_Module:ESP32-C3-WROOM-02", "ESP32-C3-WROOM-02", "RF_Module:ESP32-C3-WROOM-02", mx, my, pins=19))
    d.add(Comp("C8", "Device:C", "10uF", fp_c, mx - 10, my - 40, pins=2))
    d.add(Comp("C9", "Device:C", "100nF", fp_c, mx, my - 40, pins=2))
    d.add(Comp("R52", "Device:R", "10k", fp_r, mx - 40, my - 30, pins=2))
    d.add(Comp("C10", "Device:C", "1uF", fp_c, mx - 50, my - 22, pins=2))
    d.add(Comp("R53", "Device:R", "10k", fp_r, mx - 50, my - 6, pins=2))
    d.add(Comp("R54", "Device:R", "10k", fp_r, mx - 60, my + 2, pins=2))
    d.add(Comp("R55", "Device:R", "10k", fp_r, mx - 70, my + 10, pins=2))
    d.add(Comp("SW1", "Switch:SW_Push", "BOOT", "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A", mx - 60, my + 20, pins=2))
    lamp("D30", "R56", "RUN", "1k", mx - 90, my + 30)

    d.connect("+3V3", ("U1", "1"), ("C8", "1"), ("C9", "1"), ("R52", "1"), ("R53", "1"), ("R54", "1"), ("R55", "1"), ("R56", "1"))
    d.connect("GND", ("U1", "9"), ("U1", "19"), ("C8", "2"), ("C9", "2"), ("C10", "2"), ("SW1", "2"))
    d.connect("ESP_EN", ("U1", "2"), ("R52", "2"), ("C10", "1"))
    d.connect("IN_FOOT", ("U1", "3"))     # IO4
    d.connect("IN_NPN", ("U1", "4"))      # IO5
    d.connect("IN_AMP1", ("U1", "5"))     # IO6
    d.connect("IN_AMP2", ("U1", "6"))     # IO7
    d.connect("LED_RUN", ("U1", "7"), ("R54", "2"), ("D30", "1"))  # IO8, đèn sáng khi kéo thấp
    d.connect("RUN_AN", ("R56", "2"), ("D30", "2"))
    d.connect("ESP_BOOT", ("U1", "8"), ("R55", "2"), ("SW1", "1"))  # IO9
    d.connect("OUT_MOS", ("U1", "10"))    # IO10
    d.connect("RS485_RX", ("U1", "11"))   # IO20 / U0RXD
    d.connect("RS485_TX", ("U1", "12"))   # IO21 / U0TXD
    d.connect("USB_DN", ("U1", "13"))     # IO18
    d.connect("USB_DP", ("U1", "14"))     # IO19
    d.connect("RS485_DE", ("U1", "15"))   # IO3
    d.connect("ESP_IO2", ("U1", "16"), ("R53", "2"))  # IO2 strapping: kéo lên
    d.connect("OUT_RLY2", ("U1", "17"))   # IO1
    d.connect("OUT_RLY1", ("U1", "18"))   # IO0

    # ========== USB-C (nạp firmware / log) ==========
    # Chỉ dùng đường dữ liệu: bo luôn cấp 24 V khi nạp. CC1/CC2 5,1 kΩ để host nhận thiết bị.
    ux, uy = 30, 150
    d.add(Comp("J11", "Connector:USB_C_Receptacle_USB2.0_16P", "USB-C", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", ux, uy, pins=17))
    d.add(Comp("R50", "Device:R", "5.1k", fp_r, ux + 30, uy + 26, pins=2))
    d.add(Comp("R51", "Device:R", "5.1k", fp_r, ux + 40, uy + 26, pins=2))
    # VBUS để trống (bo tự cấp nguồn 24 V). Không có chip ESD (không có mã Basic): cổng chỉ dùng
    # để nạp/bảo trì bên trong hộp, không đưa ra mặt tủ.
    d.connect("USB_CC1", ("J11", "A5"), ("R50", "1"))
    d.connect("USB_CC2", ("J11", "B5"), ("R51", "1"))
    d.connect("USB_DP", ("J11", "A6"), ("J11", "B6"))
    d.connect("USB_DN", ("J11", "A7"), ("J11", "B7"))
    d.connect("GND", *[("J11", p) for p in ("A1", "B1", "A12", "B12", "SH")], ("R50", "2"), ("R51", "2"))

    # ========== 4 ĐẦU VÀO CÁCH LY (PC817), CÙNG MỘT MẠCH ==========
    # Kiểu NPN (sink): cảm biến/công tắc kéo SIG về 0 V -> dòng +24V -> R -> LED opto -> SIG.
    # J3 (2P) cho công tắc khô: 1 = SIG, 2 = 0 V. J4/J9/J10 (3P): 1 = +24 V cấp cảm biến, 2 = SIG, 3 = 0 V.
    # Phía MCU: kéo lên 10 kΩ, opto kéo thấp khi có tín hiệu; đèn sáng theo mức thấp.
    dx, dy = 30, 250
    inputs = [
        # jack, pins, sig net, R_led, opto, R_pull, LED, R_lamp, IN net, label
        ("J3", 2, "FOOT_SIG", "R7", "U5", "R9", "D15", "R24", "IN_FOOT", "FOOT"),
        ("J4", 3, "NPN_SIG", "R8", "U6", "R10", "D16", "R25", "IN_NPN", "NPN"),
        ("J9", 3, "AMP1_SIG", "R57", "U9", "R58", "D31", "R59", "IN_AMP1", "AMP1"),
        ("J10", 3, "AMP2_SIG", "R60", "U10", "R61", "D32", "R62", "IN_AMP2", "AMP2"),
    ]
    for i, (jr, npin, sig, r_led, opto, r_pull, led, r_lamp, net_in, label) in enumerate(inputs):
        x = dx + i * 75
        sym = "Fiberboard:Screw_Terminal_01x02" if npin == 2 else "Fiberboard:Screw_Terminal_01x03"
        fp = FP_EDG_2P if npin == 2 else FP_EDG_3P
        d.add(Comp(jr, sym, label, fp, x, dy, pins=npin))
        d.add(Comp(r_led, "Device:R", "10k", fp_r, x + 22, dy - 12, pins=2))
        d.add(Comp(opto, "Fiberboard:PC817", "LTV-817S", fp_opto, x + 38, dy, pins=4))
        d.add(Comp(r_pull, "Device:R", "10k", fp_r, x + 56, dy - 12, pins=2))
        lamp(led, r_lamp, label, "1k", x + 40, dy + 18)
        an = f"{label}_AN"
        d.connect("+24V", (r_led, "1"))
        d.connect(an, (r_led, "2"), (opto, "1"))
        if npin == 2:
            d.connect(sig, (jr, "1"), (opto, "2"))
            d.connect("GND_PWR", (jr, "2"))
        else:
            d.connect("+24V", (jr, "1"))
            d.connect(sig, (jr, "2"), (opto, "2"))
            d.connect("GND_PWR", (jr, "3"))
        d.connect("GND", (opto, "3"))
        d.connect("+3V3", (r_pull, "1"), (r_lamp, "1"))
        d.connect(net_in, (opto, "4"), (r_pull, "2"), (led, "1"))
        d.connect(f"{jr}_AN", (r_lamp, "2"), (led, "2"))

    # ========== RELAY (SRD / HF3FF cuộn 24 V) ==========
    # Cuộn lấy thẳng +24V (không tải buck). MMBT3904 kéo thấp; R47/R48 giữ tắt lúc khởi động.
    rx, ry = 30, 330
    for i, (k, j, q, rb, rpd, dfly, led, rlamp, tag) in enumerate(
        (
            ("K1", "J5", "Q3", "R11", "R47", "D3", "D17", "R26", "RLY1"),
            ("K2", "J6", "Q4", "R12", "R48", "D4", "D18", "R27", "RLY2"),
        )
    ):
        x = rx + i * 120
        d.add(Comp(rb, "Device:R", "1k", fp_r, x, ry, pins=2))
        d.add(Comp(rpd, "Device:R", "10k", fp_r, x + 10, ry + 14, pins=2))
        d.add(Comp(q, "Transistor_BJT:MMBT3904", "MMBT3904", fp_sot, x + 22, ry, pins=3))
        d.add(Comp(dfly, "Device:D", "1N4148W", fp_sod, x + 40, ry - 16, pins=2))
        d.add(Comp(k, "Relay:SANYOU_SRD_Form_C", "HF3FF-024-1ZS", "Relay_THT:Relay_SPDT_SANYOU_SRD_Series_Form_C", x + 60, ry, pins=5))
        d.add(Comp(j, "Fiberboard:Screw_Terminal_01x03", tag, FP_EDG_3P, x + 60, ry + 30, pins=3))
        lamp(led, rlamp, tag, "10k", x + 30, ry + 22)
        d.connect(f"OUT_{tag}", (rb, "1"))
        d.connect(f"{tag}_B", (rb, "2"), (rpd, "1"), (q, "1"))
        d.connect("GND_PWR", (rpd, "2"), (q, "2"))
        d.connect("+24V", (k, "5"), (dfly, "1"), (rlamp, "1"))
        d.connect(f"{tag}_COIL", (k, "2"), (q, "3"), (dfly, "2"), (led, "1"))
        d.connect(f"{j}_AN", (rlamp, "2"), (led, "2"))
        d.connect(f"{tag}_COM", (k, "1"), (j, "1"))
        d.connect(f"{tag}_NO", (k, "3"), (j, "2"))
        d.connect(f"{tag}_NC", (k, "4"), (j, "3"))

    # ========== VAN SOLENOID 24 V (MOSFET phía thấp) ==========
    vx, vy = 300, 330
    d.add(Comp("R13", "Device:R", "10R", fp_r, vx, vy, pins=2))
    d.add(Comp("R14", "Device:R", "10k", fp_r, vx, vy + 16, pins=2))
    d.add(Comp("D5", "Device:D_Schottky", "SS34", fp_sma, vx + 18, vy - 16, pins=2))
    d.add(Comp("Q5", "Transistor_FET:AO3400A", "AO3400A", fp_sot, vx + 18, vy, pins=3))
    d.add(Comp("J7", "Fiberboard:Screw_Terminal_01x02", "SOL", FP_EDG_2P, vx + 40, vy, pins=2))
    lamp("D19", "R28", "VAN", "10k", vx + 18, vy + 20)
    d.connect("OUT_MOS", ("R13", "1"))
    d.connect("MOS_G", ("R13", "2"), ("Q5", "1"), ("R14", "1"))
    d.connect("GND_PWR", ("R14", "2"), ("Q5", "2"))
    d.connect("+24V", ("J7", "1"), ("D5", "1"), ("R28", "1"))
    d.connect("SOL_LO", ("Q5", "3"), ("D5", "2"), ("J7", "2"), ("D19", "1"))
    d.connect("J7_AN", ("R28", "2"), ("D19", "2"))

    # ========== RS485 3,3 V (SIT3485 / MAX3485) ==========
    sx, sy = 400, 330
    d.add(Comp("U7", "Interface_UART:MAX3485", "SP3485EN", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", sx, sy, pins=8))
    d.add(Comp("C11", "Device:C", "100nF", fp_c, sx, sy - 26, pins=2))
    d.add(Comp("R49", "Device:R", "10k", fp_r, sx - 24, sy + 14, pins=2))
    d.add(Comp("R18", "Device:R", "10R", fp_r, sx + 22, sy - 12, pins=2))
    d.add(Comp("R19", "Device:R", "10R", fp_r, sx + 32, sy - 12, pins=2))
    d.add(Comp("R15", "Device:R", "120R", fp_r, sx + 44, sy, pins=2))
    d.add(Comp("D9", "Diode:SM712_SOT23", "PSM712", fp_sot, sx + 44, sy + 18, pins=3))
    d.add(Comp("J8", "Fiberboard:Screw_Terminal_01x03", "RS485", FP_EDG_3P, sx + 64, sy, pins=3))
    lamp("D20", "R29", "485", "1k", sx + 10, sy + 30)
    d.connect("+3V3", ("U7", "8"), ("C11", "1"))
    d.connect("GND", ("U7", "5"), ("C11", "2"), ("R49", "2"), ("D9", "3"), ("J8", "3"), ("D20", "1"))
    d.connect("RS485_RX", ("U7", "1"))
    d.connect("RS485_DE", ("U7", "2"), ("U7", "3"), ("R49", "1"), ("R29", "1"))  # RE#+DE chung, kéo xuống = nghe
    d.connect("RS485_TX", ("U7", "4"))
    d.connect("RS485_A", ("U7", "6"), ("R18", "1"))
    d.connect("RS485_B", ("U7", "7"), ("R19", "1"))
    d.connect("RS485_A_BUS", ("R18", "2"), ("R15", "1"), ("D9", "1"), ("J8", "1"))
    d.connect("RS485_B_BUS", ("R19", "2"), ("R15", "2"), ("D9", "2"), ("J8", "2"))
    d.connect("J8_AN", ("R29", "2"), ("D20", "2"))

    for c in d.comps:
        c.lcsc = lcsc_code(c)

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


# JLCPCB / LCSC: ưu tiên mã Basic (không phí nạp linh kiện). "EXT" = Extended (không có Basic thay).
# Linh kiện chân cắm (domino, relay, đế cầu chì) tự hàn tay: không đưa vào SMT.
LCSC_BY_VALUE: dict[tuple[str, str], tuple[str, str]] = {
    ("Device:R", "10k"): ("C17414", "BASIC"),
    ("Device:R", "1k"): ("C17513", "BASIC"),
    ("Device:R", "5.1k"): ("C27834", "BASIC"),
    ("Device:R", "27k"): ("C17593", "BASIC"),
    ("Device:R", "120R"): ("C17437", "BASIC"),
    ("Device:R", "10R"): ("C17415", "BASIC"),
    ("Device:C", "100nF"): ("C49678", "BASIC"),
    ("Device:C", "100nF 50V"): ("C49678", "BASIC"),
    ("Device:C", "10uF"): ("C15850", "BASIC"),
    ("Device:C", "1uF"): ("C28323", "BASIC"),
    ("Device:C", "22uF"): ("C45783", "BASIC"),
    ("Device:C", "10uF 50V"): ("C13585", "BASIC"),
    ("Device:C", "470uF 35V"): ("C2836436", "EXT"),
    ("Device:C", "220uF 10V"): ("C2833309", "EXT"),
    ("Device:L", "47uH 6045"): ("C36414", "EXT"),
}
LCSC_BY_PART: dict[str, tuple[str, str]] = {
    "SS34": ("C8678", "BASIC"),
    "1N4148W": ("C81598", "BASIC"),
    "MMBT3904": ("C20526", "BASIC"),
    "AO3400A": ("C20917", "BASIC"),
    "AO3401A": ("C15127", "BASIC"),
    "LTV-817S": ("C109227", "BASIC"),
    "SP3485EN": ("C8963", "BASIC"),
    "PSM712": ("C32677", "BASIC"),
    "XL1509-5.0": ("C61063", "BASIC"),
    "AMS1117-3.3": ("C6186", "BASIC"),
    "BOOT": ("C318884", "BASIC"),
    "SMAJ26A": ("C2848697", "EXT"),
    "ESP32-C3-WROOM-02": ("C2934560", "EXT"),
    "USB-C": ("C165948", "EXT"),
}
LED_LCSC = ("C84256", "BASIC")  # NCD0805R1, đỏ 0805


def lcsc_code(c: Comp) -> str:
    if c.ref.startswith("#") or not c.footprint:
        return ""
    if c.lib_id == "Device:LED":
        return LED_LCSC[0]
    hit = LCSC_BY_VALUE.get((c.lib_id, c.value)) or LCSC_BY_PART.get(c.value)
    return hit[0] if hit else ""


def lcsc_class(code: str) -> str:
    for tbl in (list(LCSC_BY_VALUE.values()), list(LCSC_BY_PART.values()), [LED_LCSC]):
        for cc, cls in tbl:
            if cc == code:
                return cls
    return ""


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
    if net.startswith("+") or net in {"+3V3", "+5V", "+5V_RLY1", "+5V_RLY2", "+24V", "+5V_SW"}:
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
