"""PCB-faithful KiCad symbols: pin numbers/pitch/geometry match footprints."""

from __future__ import annotations

from fiber_circuit import FIBER_PCB_PARTS


def _pin(num: str, name: str, ptype: str, x: float, y: float, rot: int, length: float = 2.54) -> str:
    return f'''\t\t\t(pin {ptype} line
\t\t\t\t(at {x} {y} {rot})
\t\t\t\t(length {length})
\t\t\t\t(name "{name}"
\t\t\t\t\t(effects (font (size 1.27 1.27)))
\t\t\t\t)
\t\t\t\t(number "{num}"
\t\t\t\t\t(effects (font (size 1.27 1.27)))
\t\t\t\t)
\t\t\t)'''


def _sym_header(name: str, ref: str, footprint: str, descr: str, keywords: str) -> str:
    short = name.split(":")[-1]
    return f'''\t(symbol "{name}"
\t\t(pin_names
\t\t\t(offset 1.016)
\t\t)
\t\t(exclude_from_sim no)
\t\t(in_bom yes)
\t\t(on_board yes)
\t\t(property "Reference" "{ref}"
\t\t\t(at 0 0 0)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(property "Value" "{short}"
\t\t\t(at 0 0 0)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(property "Footprint" "{footprint}"
\t\t\t(at 0 0 0)
\t\t\t(hide yes)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(property "Datasheet" ""
\t\t\t(at 0 0 0)
\t\t\t(hide yes)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(property "Description" "{descr}"
\t\t\t(at 0 0 0)
\t\t\t(hide yes)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(property "ki_keywords" "{keywords}"
\t\t\t(at 0 0 0)
\t\t\t(hide yes)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
'''


def esp32_devkitc_socket(prefix: str = "") -> str:
    """38-pin dual header, 2.54mm pitch, 25.4mm row spacing — matches footprint 1:1."""
    name = f"{prefix}ESP32_DevKitC_Socket" if prefix else "ESP32_DevKitC_Socket"
    # DevKitC pinout, USB at bottom (same as footprint silk "USB")
    left_names = [
        "3V3", "EN", "SVP", "SVN", "IO34", "IO35", "IO32", "IO33", "IO25",
        "IO26", "IO27", "IO14", "GND", "IO12", "IO13", "SD2", "SD3", "CMD", "5V",
    ]
    right_names = [
        "GND", "IO23", "IO22", "TXD0", "RXD0", "IO21", "GND", "IO19", "IO18",
        "IO5", "IO17", "IO16", "IO4", "IO0", "IO2", "IO15", "SD1", "SD0", "CLK",
    ]
    left_types = [
        "power_out", "input", "input", "input", "input", "input",
        "bidirectional", "bidirectional", "bidirectional", "bidirectional",
        "bidirectional", "bidirectional", "power_in", "bidirectional",
        "bidirectional", "bidirectional", "bidirectional", "bidirectional", "power_in",
    ]
    right_types = [
        "power_in", "bidirectional", "bidirectional", "output", "input",
        "bidirectional", "power_in", "bidirectional", "bidirectional",
        "bidirectional", "bidirectional", "bidirectional", "bidirectional",
        "bidirectional", "bidirectional", "bidirectional", "bidirectional",
        "bidirectional", "bidirectional",
    ]

    pins = []
    # Footprint: pad N at (-12.7, -(N-1)*2.54); symbol pin tip outside body
    for i, (nm, tp) in enumerate(zip(left_names, left_types)):
        y = -i * 2.54
        pins.append(_pin(str(i + 1), nm, tp, -15.24, y, 0))
    for i, (nm, tp) in enumerate(zip(right_names, right_types)):
        y = -i * 2.54
        pins.append(_pin(str(20 + i), nm, tp, 15.24, y, 180))

    body_top = 2.54
    body_bot = -18 * 2.54 - 1.27  # -46.99
    return f'''{_sym_header(name, "U", "Fiberboard:ESP32_DevKitC_Socket",
                         "ESP32-DevKitC socket, pin geometry matches PCB footprint",
                         "ESP32 DevKit socket PCB")}
\t\t(symbol "{name.split(":")[-1]}_0_1"
\t\t\t(rectangle
\t\t\t\t(start -12.7 {body_top})
\t\t\t\t(end 12.7 {body_bot})
\t\t\t\t(stroke (width 0.254) (type default))
\t\t\t\t(fill (type background))
\t\t\t)
\t\t\t(polyline
\t\t\t\t(pts (xy -3.81 {body_bot + 2.54}) (xy 3.81 {body_bot + 2.54}) (xy 3.81 {body_bot + 0.5}) (xy -3.81 {body_bot + 0.5}) (xy -3.81 {body_bot + 2.54}))
\t\t\t\t(stroke (width 0.15) (type default))
\t\t\t\t(fill (type none))
\t\t\t)
\t\t\t(text "USB"
\t\t\t\t(at 0 {body_bot + 1.5} 0)
\t\t\t\t(effects (font (size 1.27 1.27)))
\t\t\t)
\t\t)
\t\t(symbol "{name.split(":")[-1]}_1_1"
{chr(10).join(pins)}
\t\t)
\t)'''


def fiber_clamp_2ch(prefix: str = "") -> str:
    """Pads match Fiber_Clamp_2CH footprint XY 1:1 (mm)."""
    name = f"{prefix}Fiber_Clamp_2CH" if prefix else "Fiber_Clamp_2CH"
    # footprint pads: 1(-8,0) 2(-4,0) 3(4,0) 4(8,0) 5(0,-3.5)
    pins = [
        _pin("1", "F1_A", "passive", -8, 2.54, 270, 2.54),
        _pin("2", "F1_K", "passive", -4, 2.54, 270, 2.54),
        _pin("3", "F2_A", "passive", 4, 2.54, 270, 2.54),
        _pin("4", "F2_K", "passive", 8, 2.54, 270, 2.54),
        _pin("5", "GND", "passive", 0, -6.04, 90, 2.54),
    ]
    return f'''{_sym_header(name, "J", "Fiberboard:Fiber_Clamp_2CH",
                         "2ch fiber clamp, pad XY matches PCB", "fiber clamp")}
\t\t(symbol "{name.split(":")[-1]}_0_1"
\t\t\t(rectangle
\t\t\t\t(start -12 6)
\t\t\t\t(end 12 -6)
\t\t\t\t(stroke (width 0.254) (type default))
\t\t\t\t(fill (type background))
\t\t\t)
\t\t\t(text "FIBER1" (at -6 4 0) (effects (font (size 1.016 1.016))))
\t\t\t(text "FIBER2" (at 6 4 0) (effects (font (size 1.016 1.016))))
\t\t)
\t\t(symbol "{name.split(":")[-1]}_1_1"
{chr(10).join(pins)}
\t\t)
\t)'''


def fiber_clamp_1ch(prefix: str = "") -> str:
    """Single-channel fiber clamp; pads 1/2/3 at x=-2.54/0/2.54 match footprint."""
    name = f"{prefix}Fiber_Clamp_1CH" if prefix else "Fiber_Clamp_1CH"
    pins = [
        _pin("1", "LED_A", "passive", -2.54, 2.54, 270, 2.54),
        _pin("2", "LED_K", "passive", 0, 2.54, 270, 2.54),
        _pin("3", "GND", "passive", 2.54, 2.54, 270, 2.54),
    ]
    return f'''{_sym_header(name, "J", "Fiberboard:Fiber_Clamp_1CH",
                         "1ch fiber clamp, pad XY matches PCB", "fiber clamp")}
\t\t(symbol "{name.split(":")[-1]}_0_1"
\t\t\t(rectangle
\t\t\t\t(start -5.08 0)
\t\t\t\t(end 5.08 -5.08)
\t\t\t\t(stroke (width 0.254) (type default))
\t\t\t\t(fill (type background))
\t\t\t)
\t\t)
\t\t(symbol "{name.split(":")[-1]}_1_1"
{chr(10).join(pins)}
\t\t)
\t)'''


def terminal_block(n: int, pitch: float = 5.08, prefix: str = "") -> str:
    """Horizontal screw terminal, pin pitch matches Phoenix MKDS footprint."""
    name = f"{prefix}Screw_Terminal_01x{n:02d}" if prefix else f"Screw_Terminal_01x{n:02d}"
    fp = {
        2: "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal",
        3: "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-3-5.08_1x03_P5.08mm_Horizontal",
        4: "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    }.get(n, "")
    if n == 4:
        pitch = 2.54
    width = (n - 1) * pitch
    pins = []
    for i in range(n):
        x = i * pitch
        pins.append(_pin(str(i + 1), f"P{i+1}", "passive", x, 2.54, 270, 2.54))
    return f'''{_sym_header(name, "J", fp, f"{n}-pin terminal, pitch {pitch}mm matches PCB", "terminal")}
\t\t(symbol "{name.split(":")[-1]}_0_1"
\t\t\t(rectangle
\t\t\t\t(start -2.54 0)
\t\t\t\t(end {width + 2.54} -5.08)
\t\t\t\t(stroke (width 0.254) (type default))
\t\t\t\t(fill (type background))
\t\t\t)
\t\t)
\t\t(symbol "{name.split(":")[-1]}_1_1"
{chr(10).join(pins)}
\t\t)
\t)'''


def relay_g5le1(prefix: str = "") -> str:
    """Omron G5LE-1 pin XY matches Relay_SPDT_Omron-G5LE-1 footprint (mm)."""
    name = f"{prefix}G5LE-1" if prefix else "G5LE-1"
    # pads: 1(0,0) 2(-6,2) 3(-6,14.2) 4(6,14.2) 5(6,2)
    # Omron: 1=Coil, 2=Coil, 3=NO, 4=COM, 5=NC (common KiCad mapping)
    pins = [
        _pin("1", "COIL+", "passive", 0, -2.54, 90, 2.54),
        _pin("2", "COIL-", "passive", -6, -0.54, 90, 2.54),
        _pin("3", "NO", "passive", -6, 16.74, 270, 2.54),
        _pin("4", "COM", "passive", 6, 16.74, 270, 2.54),
        _pin("5", "NC", "passive", 6, -0.54, 90, 2.54),
    ]
    return f'''{_sym_header(name, "K", "Relay_THT:Relay_SPDT_Omron-G5LE-1",
                         "G5LE-1 SPDT, pin positions match PCB footprint", "relay G5LE")}
\t\t(symbol "{name.split(":")[-1]}_0_1"
\t\t\t(rectangle
\t\t\t\t(start -8.35 -2.65)
\t\t\t\t(end 8.35 20.05)
\t\t\t\t(stroke (width 0.254) (type default))
\t\t\t\t(fill (type background))
\t\t\t)
\t\t\t(text "G5LE-1" (at 0 8.5 0) (effects (font (size 1.27 1.27))))
\t\t)
\t\t(symbol "{name.split(":")[-1]}_1_1"
{chr(10).join(pins)}
\t\t)
\t)'''


def opto_dip6(prefix: str = "") -> str:
    """4N25-style DIP-6, pad XY matches Package_DIP:DIP-6_W7.62mm."""
    name = f"{prefix}Opto_DIP6" if prefix else "Opto_DIP6"
    # pads: 1(0,0) 2(0,2.54) 3(0,5.08) 4(7.62,5.08) 5(7.62,2.54) 6(7.62,0)
    pins = [
        _pin("1", "A", "passive", -2.54, 0, 0, 2.54),
        _pin("2", "C", "passive", -2.54, 2.54, 0, 2.54),
        _pin("3", "NC", "no_connect", -2.54, 5.08, 0, 2.54),
        _pin("4", "E", "passive", 10.16, 5.08, 180, 2.54),
        _pin("5", "C", "passive", 10.16, 2.54, 180, 2.54),
        _pin("6", "B", "passive", 10.16, 0, 180, 2.54),
    ]
    return f'''{_sym_header(name, "U", "Package_DIP:DIP-6_W7.62mm",
                         "DIP-6 optocoupler, pin pitch/spacing matches PCB", "opto 4N25 DIP6")}
\t\t(symbol "{name.split(":")[-1]}_0_1"
\t\t\t(rectangle
\t\t\t\t(start 0 -1.27)
\t\t\t\t(end 7.62 6.35)
\t\t\t\t(stroke (width 0.254) (type default))
\t\t\t\t(fill (type background))
\t\t\t)
\t\t\t(polyline
\t\t\t\t(pts (xy -0.5 -0.5) (xy 0.5 0.5))
\t\t\t\t(stroke (width 0.15) (type default))
\t\t\t\t(fill (type none))
\t\t\t)
\t\t)
\t\t(symbol "{name.split(":")[-1]}_1_1"
{chr(10).join(pins)}
\t\t)
\t)'''


def soic8(prefix: str = "") -> str:
    """SOIC-8 pin pitch 1.27mm matches Package_SO:SOIC-8_3.9x4.9mm_P1.27mm."""
    name = f"{prefix}SOIC8" if prefix else "SOIC8"
    # Schematic uses same relative pitch; pin tips outside
    # pads y: -1.905,-0.635,0.635,1.905 — use same
    left_y = [-1.905, -0.635, 0.635, 1.905]
    names_l = ["1", "2", "3", "4"]
    names_r = ["8", "7", "6", "5"]  # pin 8 at top-right when pin1 bottom-left in SOIC standard
    # Standard SOIC: pin1 bottom-left in KiCad footprint at y=-1.905
    pins = []
    for i, y in enumerate(left_y):
        pins.append(_pin(str(i + 1), f"P{i+1}", "passive", -5.08, y, 0, 2.54))
    # right side pin8 at y=-1.905, pin5 at y=1.905
    right = [(8, -1.905), (7, -0.635), (6, 0.635), (5, 1.905)]
    for num, y in right:
        pins.append(_pin(str(num), f"P{num}", "passive", 5.08, y, 180, 2.54))
    return f'''{_sym_header(name, "U", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                         "SOIC-8 outline/pitch matches PCB footprint", "SOIC8")}
\t\t(symbol "{name.split(":")[-1]}_0_1"
\t\t\t(rectangle
\t\t\t\t(start -2.54 -2.54)
\t\t\t\t(end 2.54 2.54)
\t\t\t\t(stroke (width 0.254) (type default))
\t\t\t\t(fill (type background))
\t\t\t)
\t\t\t(polyline
\t\t\t\t(pts (xy -2.54 -1.27) (xy -1.27 -2.54))
\t\t\t\t(stroke (width 0.15) (type default))
\t\t\t\t(fill (type none))
\t\t\t)
\t\t)
\t\t(symbol "{name.split(":")[-1]}_1_1"
{chr(10).join(pins)}
\t\t)
\t)'''


def pc817_so4(prefix: str = "") -> str:
    name = f"{prefix}PC817" if prefix else "PC817"
    pins = [
        _pin("1", "A", "passive", -5.08, 2.54, 0, 2.54),
        _pin("2", "K", "passive", -5.08, -2.54, 0, 2.54),
        _pin("3", "E", "passive", 5.08, -2.54, 180, 2.54),
        _pin("4", "C", "passive", 5.08, 2.54, 180, 2.54),
    ]
    return f'''{_sym_header(name, "U", "Fiberboard:PC817_SO4",
                         "PC817 SO-4 SMD optocoupler", "opto PC817")}
\t\t(symbol "{name.split(":")[-1]}_0_1"
\t\t\t(rectangle
\t\t\t\t(start -2.54 -2.54)
\t\t\t\t(end 2.54 2.54)
\t\t\t\t(stroke (width 0.254) (type default))
\t\t\t\t(fill (type background))
\t\t\t)
\t\t)
\t\t(symbol "{name.split(":")[-1]}_1_1"
{chr(10).join(pins)}
\t\t)
\t)'''


def afbr_1624z(prefix: str = "") -> str:
    name = f"{prefix}AFBR_1624Z" if prefix else "AFBR_1624Z"
    pins = [
        _pin("1", "VCC", "power_in", 5.08, 2.54, 180, 2.54),
        _pin("3", "GND", "power_in", 0, 2.54, 180, 2.54),
        _pin("4", "DATA_IN", "input", -5.08, 2.54, 0, 2.54),
        _pin("5", "MNT", "passive", -5.08, -2.54, 0, 2.54),
        _pin("8", "MNT", "passive", 5.08, -2.54, 180, 2.54),
    ]
    return f'''{_sym_header(name, "U", "Fiberboard:AFBR_1624Z_VL",
                         "Broadcom Versatile Link POF TX 650nm", "AFBR POF")}
\t\t(symbol "{name.split(":")[-1]}_0_1"
\t\t\t(rectangle
\t\t\t\t(start -3.81 -5.08)
\t\t\t\t(end 3.81 5.08)
\t\t\t\t(stroke (width 0.254) (type default))
\t\t\t\t(fill (type background))
\t\t\t)
\t\t\t(polyline
\t\t\t\t(pts (xy 0 -5.08) (xy 0 -7.62))
\t\t\t\t(stroke (width 0.254) (type default))
\t\t\t\t(fill (type none))
\t\t\t)
\t\t\t(text "POF" (at 0 -8.89 0) (effects (font (size 1.016 1.016))))
\t\t)
\t\t(symbol "{name.split(":")[-1]}_1_1"
{chr(10).join(pins)}
\t\t)
\t)'''


def afbr_2624z(prefix: str = "") -> str:
    name = f"{prefix}AFBR_2624Z" if prefix else "AFBR_2624Z"
    pins = [
        _pin("1", "DATA_OUT", "output", 5.08, 2.54, 180, 2.54),
        _pin("2", "GND", "power_in", 2.54, 2.54, 180, 2.54),
        _pin("3", "VCC", "power_in", 0, 2.54, 180, 2.54),
        _pin("4", "GND", "power_in", -5.08, 2.54, 0, 2.54),
        _pin("5", "MNT", "passive", -5.08, -2.54, 0, 2.54),
        _pin("8", "MNT", "passive", 5.08, -2.54, 180, 2.54),
    ]
    return f'''{_sym_header(name, "U", "Fiberboard:AFBR_2624Z_VL",
                         "Broadcom Versatile Link POF RX TTL", "AFBR POF")}
\t\t(symbol "{name.split(":")[-1]}_0_1"
\t\t\t(rectangle
\t\t\t\t(start -5.08 -5.08)
\t\t\t\t(end 5.08 5.08)
\t\t\t\t(stroke (width 0.254) (type default))
\t\t\t\t(fill (type background))
\t\t\t)
\t\t\t(polyline
\t\t\t\t(pts (xy 0 -5.08) (xy 0 -7.62))
\t\t\t\t(stroke (width 0.254) (type default))
\t\t\t\t(fill (type none))
\t\t\t)
\t\t\t(text "POF" (at 0 -8.89 0) (effects (font (size 1.016 1.016))))
\t\t)
\t\t(symbol "{name.split(":")[-1]}_1_1"
{chr(10).join(pins)}
\t\t)
\t)'''


def net_tie_2(prefix: str = "") -> str:
    """Two-pin net tie; geometry matches connectivity.PIN_GEOM Fiberboard:NetTie_2."""
    name = f"{prefix}NetTie_2" if prefix else "NetTie_2"
    pins = [
        _pin("1", "GND_PWR", "passive", -5.08, 0, 0, 2.54),
        _pin("2", "GND", "passive", 5.08, 0, 180, 2.54),
    ]
    return f'''{_sym_header(name, "NT", "NetTie:NetTie-2_SMD_Pad2.0mm",
                         "Star: GND_PWR to GND signal", "NetTie")}
\t\t(symbol "{name.split(":")[-1]}_0_1"
\t\t\t(polyline
\t\t\t\t(pts (xy -1.27 0) (xy 1.27 0))
\t\t\t\t(stroke (width 0.254) (type default))
\t\t\t\t(fill (type none))
\t\t\t)
\t\t)
\t\t(symbol "{name.split(":")[-1]}_1_1"
{chr(10).join(pins)}
\t\t)
\t)'''


def sot23(prefix: str = "") -> str:
    """SOT-23 pin geometry matches Package_TO_SOT_SMD:SOT-23 (scaled readable)."""
    name = f"{prefix}SOT23" if prefix else "SOT23"
    # pads: 1(-0.9375,-0.95) 2(-0.9375,0.95) 3(0.9375,0) — scale x2 for sch clarity but keep ratio
    s = 2.0
    pins = [
        _pin("1", "1", "passive", -0.9375 * s - 2.54, -0.95 * s, 0, 2.54),
        _pin("2", "2", "passive", -0.9375 * s - 2.54, 0.95 * s, 0, 2.54),
        _pin("3", "3", "passive", 0.9375 * s + 2.54, 0, 180, 2.54),
    ]
    return f'''{_sym_header(name, "Q", "Package_TO_SOT_SMD:SOT-23",
                         "SOT-23 pin arrangement matches PCB", "SOT23")}
\t\t(symbol "{name.split(":")[-1]}_0_1"
\t\t\t(rectangle
\t\t\t\t(start {-1.5 * s} {-1.5 * s})
\t\t\t\t(end {1.5 * s} {1.5 * s})
\t\t\t\t(stroke (width 0.254) (type default))
\t\t\t\t(fill (type background))
\t\t\t)
\t\t)
\t\t(symbol "{name.split(":")[-1]}_1_1"
{chr(10).join(pins)}
\t\t)
\t)'''


def all_symbols_for_lib() -> str:
    parts = [
        esp32_devkitc_socket(),
        fiber_clamp_1ch(),
        fiber_clamp_2ch(),
        terminal_block(2),
        terminal_block(3),
        terminal_block(4),
        relay_g5le1(),
        opto_dip6(),
        soic8(),
        sot23(),
        net_tie_2(),
    ]
    return "\n".join(parts)


def all_symbols_for_schematic_embed() -> str:
    """Symbols embedded in .kicad_sch use Lib:Name."""
    p = "Fiberboard:"
    parts = [
        esp32_devkitc_socket(p),
        pc817_so4(p),
        afbr_1624z(p),
        afbr_2624z(p),
        terminal_block(2, prefix=p),
        terminal_block(3, prefix=p),
        terminal_block(4, prefix=p),
        relay_g5le1(p),
        opto_dip6(p),
        soic8(p),
        sot23(p),
        net_tie_2(p),
    ]
    return "\n".join(parts)


# PCB placement table (mm) — schematic uses same XY * SCALE + OFFSET
PCB_PLACEMENTS = [
    # ref, lib_id, value, footprint, pcb_x, pcb_y, rot, pin_count
    ("J1", "Fiberboard:Screw_Terminal_01x02", "VIN", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal", 15, 15, 0, 2),
    ("U2", "Regulator_Switching:XL1509-5.0", "XL1509-5.0", "Package_TO_SOT_SMD:TO-263-5_TabPin3", 40, 18, 0, 5),
    ("L1", "Device:L", "47uH", "Inductor_SMD:L_1210_3225Metric", 55, 18, 0, 2),
    ("U3", "Regulator_Linear:AMS1117-3.3", "AMS1117-3.3", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", 70, 18, 0, 3),
    ("C1", "Device:C", "100uF", "Capacitor_SMD:C_1206_3216Metric", 28, 28, 0, 2),
    ("C2", "Device:C", "100uF", "Capacitor_SMD:C_1206_3216Metric", 55, 28, 0, 2),
    ("C3", "Device:C", "22uF", "Capacitor_SMD:C_0805_2012Metric", 75, 28, 0, 2),
    ("U1", "Fiberboard:ESP32_DevKitC_Socket", "ESP32-DevKitC", "Fiberboard:ESP32_DevKitC_Socket", 45, 60, 0, 38),
    # Fiber optic front-end (TX PWM + RC + LM358 + LM393) — see FIBER_PCB_PARTS
    ("U5", "Fiberboard:Opto_DIP6", "4N25", "Package_DIP:DIP-6_W7.62mm", 20, 120, 0, 6),
    ("U6", "Fiberboard:Opto_DIP6", "4N25", "Package_DIP:DIP-6_W7.62mm", 40, 120, 0, 6),
    ("J3", "Fiberboard:Screw_Terminal_01x02", "FOOT", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal", 15, 135, 0, 2),
    ("J4", "Fiberboard:Screw_Terminal_01x03", "NPN", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-3-5.08_1x03_P5.08mm_Horizontal", 40, 135, 0, 3),
    ("K1", "Fiberboard:G5LE-1", "G5LE-14-DC5", "Relay_THT:Relay_SPDT_Omron-G5LE-1", 75, 125, 0, 5),
    ("K2", "Fiberboard:G5LE-1", "G5LE-14-DC5", "Relay_THT:Relay_SPDT_Omron-G5LE-1", 100, 125, 0, 5),
    ("J5", "Fiberboard:Screw_Terminal_01x03", "RLY1", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-3-5.08_1x03_P5.08mm_Horizontal", 75, 145, 0, 3),
    ("J6", "Fiberboard:Screw_Terminal_01x03", "RLY2", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-3-5.08_1x03_P5.08mm_Horizontal", 100, 145, 0, 3),
    ("Q3", "Fiberboard:SOT23", "2N3904", "Package_TO_SOT_SMD:SOT-23", 65, 115, 0, 3),
    ("Q4", "Fiberboard:SOT23", "2N3904", "Package_TO_SOT_SMD:SOT-23", 90, 115, 0, 3),
    ("Q5", "Fiberboard:SOT23", "AO3400A", "Package_TO_SOT_SMD:SOT-23", 20, 155, 0, 3),
    ("D5", "Device:D", "SS34", "Diode_SMD:D_SMA", 30, 155, 0, 2),
    ("J7", "Fiberboard:Screw_Terminal_01x02", "SOL", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal", 15, 168, 0, 2),
    ("U7", "Interface_UART:MAX485E", "MAX485E", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", 55, 160, 0, 8),
    ("J8", "Fiberboard:Screw_Terminal_01x03", "RS485", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-3-5.08_1x03_P5.08mm_Horizontal", 75, 168, 0, 3),
    ("J9", "Fiberboard:Screw_Terminal_01x04", "OLED", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", 110, 168, 0, 4),
    ("D6", "Device:LED", "STATUS", "LED_SMD:LED_0805_2012Metric", 120, 160, 0, 2),
    ("J10", "Fiberboard:Screw_Terminal_01x02", "BTN", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal", 110, 180, 0, 2),
]
PCB_PLACEMENTS.extend(FIBER_PCB_PARTS)

# passives row on PCB
for i, ref in enumerate(
    ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11", "R12", "R13", "R14", "R15", "R16"]
):
    PCB_PLACEMENTS.append(
        (ref, "Device:R", "R", "Resistor_SMD:R_0805_2012Metric", 10 + (i % 8) * 5, 165 + (i // 8) * 5, 0, 2)
    )
for i, ref in enumerate(["D3", "D4"]):
    PCB_PLACEMENTS.append(
        (ref, "Device:D", "1N4148", "Diode_SMD:D_SOD-123", 10 + i * 5, 175, 0, 2)
    )
