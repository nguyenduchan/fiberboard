#!/usr/bin/env python3
"""Generate KiCad 10 project: Fiberboard All-In-One Logic (no stepper)."""

from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_connected import (  # noqa: E402
    emit_connected_schematic,
    inject_nets_into_footprint,
    pad_net_table,
)
from connectivity import build_logic_design  # noqa: E402
from assembly_groups import assembly_group  # noqa: E402
from pcb_layout import (  # noqa: E402
    BOARD_H,
    BOARD_W,
    DIN_RAIL_INSET,
    ZONES,
    build_layout,
    ground_pour_polygons,
    group_sexpr,
    postprocess_footprint,
    zone_group,
)
from symbols_pcb_matched import (  # noqa: E402
    all_symbols_for_lib,
    all_symbols_for_schematic_embed,
)

KICAD = Path(r"C:\Users\duchan.nguyen\AppData\Local\Programs\KiCad\10.0\share\kicad")
SYM_DIR = KICAD / "symbols"
FP_DIR = KICAD / "footprints"
PROJECT = "fiberboard-logic"
SHEET_UUID = str(uuid.uuid4())
# Schematic mirrors PCB XY (mm): sch = OFFSET + pcb * SCALE
SCH_SCALE = 2.0
SCH_OX = 40.0
SCH_OY = 35.0


def uid() -> str:
    return str(uuid.uuid4())


def _extract_raw_symbol(text: str, name: str) -> str:
    needle = f'(symbol "{name}"'
    start = text.find(needle)
    if start < 0:
        raise KeyError(name)
    i = start
    depth = 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    raise RuntimeError(f"Unbalanced symbol {name}")


def _resolve_symbol_root(text: str, name: str, _seen: set[str] | None = None) -> tuple[str, str]:
    """Follow extends until a symbol that contains pins. Returns (root_name, root_block)."""
    seen = _seen or set()
    if name in seen:
        raise RuntimeError(f"extends cycle at {name}")
    seen.add(name)
    block = _extract_raw_symbol(text, name)
    if "(pin " in block:
        return name, block
    m = re.search(r'\(extends "([^"]+)"\)', block)
    if m:
        return _resolve_symbol_root(text, m.group(1), seen)
    raise KeyError(f"No pins found in symbol chain for {name}")


def extract_symbol(lib_path: Path, name: str) -> list[str]:
    """Return a self-contained lib_symbol block (extends fully flattened).

    KiCad sch upgrade can drop `(extends ...)` without copying parent pins,
    leaving pinless aliases (AO3400A, LM358, MAX485E, ...). Flattening here
    makes connectivity reliable.
    """
    text = lib_path.read_text(encoding="utf-8")
    lib = lib_path.stem
    derived = _extract_raw_symbol(text, name)

    try:
        root_name, root_block = _resolve_symbol_root(text, name)
    except KeyError:
        # XL1509-5.0 may be a thin alias; fall back to any XL1509-* with pins
        if name.startswith("XL1509"):
            for cand in re.findall(r'\(symbol "(XL1509[^"]+)"', text):
                if "(pin " in _extract_raw_symbol(text, cand):
                    root_name, root_block = cand, _extract_raw_symbol(text, cand)
                    break
            else:
                raise
        else:
            raise

    flat = root_block.replace(f'(symbol "{root_name}"', f'(symbol "{lib}:{name}"', 1)
    flat = re.sub(rf'\(symbol "{re.escape(root_name)}_', f'(symbol "{name}_', flat)
    # Prefer derived Value / footprint / datasheet when present on the alias
    for prop in ("Value", "Footprint", "Datasheet", "Description", "ki_keywords", "ki_fp_filters"):
        pm = re.search(
            rf'\(property "{prop}" "([^"]*)"([\s\S]*?\n\t\t\)\n)',
            derived,
        )
        if not pm:
            continue
        new_prop = f'(property "{prop}" "{pm.group(1)}"{pm.group(2)}'
        flat, n = re.subn(
            rf'\(property "{prop}" "[^"]*"([\s\S]*?\n\t\t\)\n)',
            new_prop,
            flat,
            count=1,
        )
        if n == 0:
            flat = flat.replace(
                f'(symbol "{lib}:{name}"\n',
                f'(symbol "{lib}:{name}"\n\t\t{new_prop}',
                1,
            )
    return [flat]


def extract_footprint(pretty: str, mod: str) -> str:
    path = FP_DIR / f"{pretty}.pretty" / f"{mod}.kicad_mod"
    return path.read_text(encoding="utf-8")


def place_symbol(
    lib_id: str,
    ref: str,
    value: str,
    x: float,
    y: float,
    footprint: str = "",
    rotation: int = 0,
    unit: int = 1,
    dnp: bool = False,
    in_bom: bool = True,
    pin_count: int = 8,
    pin_numbers: list[str] | None = None,
) -> str:
    if pin_numbers is None:
        # ESP32 has pins 1..38 contiguous; most parts 1..N
        if "ESP32" in lib_id:
            pin_numbers = [str(i) for i in range(1, 39)]
        else:
            pin_numbers = [str(i) for i in range(1, pin_count + 1)]
    pins = [f'\t\t(pin "{n}"\n\t\t\t(uuid "{uid()}")\n\t\t)' for n in pin_numbers]
    pin_block = "\n".join(pins)
    return f'''\t(symbol
\t\t(lib_id "{lib_id}")
\t\t(at {x} {y} {rotation})
\t\t(unit {unit})
\t\t(exclude_from_sim no)
\t\t(in_bom {"yes" if in_bom else "no"})
\t\t(on_board yes)
\t\t(dnp {"yes" if dnp else "no"})
\t\t(uuid "{uid()}")
\t\t(property "Reference" "{ref}"
\t\t\t(at {x} {y - 2.54} 0)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t)
\t\t)
\t\t(property "Value" "{value}"
\t\t\t(at {x} {y + 2.54} 0)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t)
\t\t)
\t\t(property "Footprint" "{footprint}"
\t\t\t(at {x} {y} 0)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t\t(hide yes)
\t\t\t)
\t\t)
\t\t(property "Datasheet" ""
\t\t\t(at {x} {y} 0)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t\t(hide yes)
\t\t\t)
\t\t)
\t\t(property "Description" ""
\t\t\t(at {x} {y} 0)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t\t(hide yes)
\t\t\t)
\t\t)
{pin_block}
\t\t(instances
\t\t\t(project "{PROJECT}"
\t\t\t\t(path "/{SHEET_UUID}"
\t\t\t\t\t(reference "{ref}")
\t\t\t\t\t(unit {unit})
\t\t\t\t)
\t\t\t)
\t\t)
\t)'''


def global_label(name: str, x: float, y: float, rotation: int = 0, shape: str = "input") -> str:
    return f'''\t(global_label "{name}"
\t\t(shape {shape})
\t\t(at {x} {y} {rotation})
\t\t(effects
\t\t\t(font
\t\t\t\t(size 1.27 1.27)
\t\t\t)
\t\t\t(justify left)
\t\t)
\t\t(uuid "{uid()}")
\t)'''


def text_box(txt: str, x: float, y: float) -> str:
    return f'''\t(text "{txt}"
\t\t(exclude_from_sim no)
\t\t(at {x} {y} 0)
\t\t(effects
\t\t\t(font
\t\t\t\t(size 2.54 2.54)
\t\t\t\t(bold yes)
\t\t\t)
\t\t\t(justify left bottom)
\t\t)
\t\t(uuid "{uid()}")
\t)'''


def wire(x1, y1, x2, y2) -> str:
    return f'''\t(wire
\t\t(pts
\t\t\t(xy {x1} {y1}) (xy {x2} {y2})
\t\t)
\t\t(stroke
\t\t\t(width 0)
\t\t\t(type default)
\t\t)
\t\t(uuid "{uid()}")
\t)'''


def make_esp32_socket_footprint() -> str:
    """ESP32-DevKitC dual female header socket, 2.54mm pitch, 25.4mm row spacing."""
    pads_l = []
    pads_r = []
    # 19 pins each side, pin1 at top-left
    for i in range(19):
        y = -i * 2.54
        n_l = i + 1
        n_r = 20 + i
        pads_l.append(
            f'''\t(pad "{n_l}" thru_hole circle
\t\t(at -12.7 {y} 0)
\t\t(size 1.7 1.7)
\t\t(drill 1.0)
\t\t(layers "*.Cu" "*.Mask")
\t\t(remove_unused_layers no)
\t\t(uuid "{uid()}")
\t)'''
        )
        pads_r.append(
            f'''\t(pad "{n_r}" thru_hole circle
\t\t(at 12.7 {y} 0)
\t\t(size 1.7 1.7)
\t\t(drill 1.0)
\t\t(layers "*.Cu" "*.Mask")
\t\t(remove_unused_layers no)
\t\t(uuid "{uid()}")
\t)'''
        )
    # DevKitC V4 (Espressif): bo 54.4×27.9 mm. Chân 1 (3V3) ở đầu ăng-ten, USB ở −Y.
    # 5.9 mm từ mép ăng-ten tới tâm chân 1; 45.72 mm giữa chân 1 và chân 19; phần còn lại tới mép USB.
    # WROOM-32: ăng-ten PCB 18×6.5 mm nằm ở mép đó (không tính vào courtyard đế).
    ant_y1 = 5.9
    ant_y0 = ant_y1 - 6.5
    silk = f'''\t(fp_rect
\t\t(start -15.5 2.5)
\t\t(end 15.5 -48.26)
\t\t(stroke
\t\t\t(width 0.15)
\t\t\t(type default)
\t\t)
\t\t(fill none)
\t\t(layer "F.SilkS")
\t\t(uuid "{uid()}")
\t)
\t(fp_rect
\t\t(start -15.5 2.5)
\t\t(end 15.5 -48.26)
\t\t(stroke
\t\t\t(width 0.05)
\t\t\t(type default)
\t\t)
\t\t(fill none)
\t\t(layer "F.CrtYd")
\t\t(uuid "{uid()}")
\t)
\t(fp_rect
\t\t(start -9.0 {ant_y0})
\t\t(end 9.0 {ant_y1})
\t\t(stroke
\t\t\t(width 0.2)
\t\t\t(type default)
\t\t)
\t\t(fill none)
\t\t(layer "F.SilkS")
\t\t(uuid "{uid()}")
\t)
\t(fp_line
\t\t(start -9.0 {ant_y0})
\t\t(end 9.0 {ant_y1})
\t\t(stroke (width 0.12) (type default))
\t\t(layer "F.SilkS")
\t\t(uuid "{uid()}")
\t)
\t(fp_line
\t\t(start 9.0 {ant_y0})
\t\t(end -9.0 {ant_y1})
\t\t(stroke (width 0.12) (type default))
\t\t(layer "F.SilkS")
\t\t(uuid "{uid()}")
\t)
\t(fp_text user "Ăng-ten 18×6.5" (at 0 {(ant_y0 + ant_y1) / 2:.2f} 0) (layer "F.Fab") (uuid "{uid()}")
\t\t(effects (font (size 0.7 0.7) (thickness 0.1)))
\t)
\t(fp_text reference "U1" (at 0 4.5 0) (layer "F.SilkS") (uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(fp_text value "ESP32-DevKitC-Socket" (at 0 -50.5 0) (layer "F.Fab") (uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(fp_text user "USB" (at 0 -46.5 0) (layer "F.SilkS") (uuid "{uid()}")
\t\t(effects (font (size 0.8 0.8) (thickness 0.12)))
\t)'''
    return f'''(footprint "ESP32_DevKitC_Socket"
\t(version 20241229)
\t(generator "fiberboard_gen")
\t(generator_version "1.0")
\t(layer "F.Cu")
\t(descr "Female pin socket for ESP32-DevKitC-32E, 2x19, row spacing 25.4 mm")
\t(tags "esp32 socket header")
\t(property "Reference" "U1"
\t\t(at 0 5.5 0)
\t\t(layer "F.SilkS")
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(property "Value" "ESP32_DevKitC_Socket"
\t\t(at 0 -51.5 0)
\t\t(layer "F.Fab")
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(property "Datasheet" ""
\t\t(at 0 0 0)
\t\t(layer "F.Fab")
\t\t(hide yes)
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(property "Description" "ESP32 DevKitC plug-in socket"
\t\t(at 0 0 0)
\t\t(layer "F.Fab")
\t\t(hide yes)
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(attr through_hole)
{silk}
{chr(10).join(pads_l)}
{chr(10).join(pads_r)}
\t(embedded_fonts no)
)
'''


def make_esp32_socket_symbol() -> str:
    """Simplified ESP32-DevKitC socket symbol with used pins."""
    # Left column pins (DevKitC typical top->bottom): document mapping in properties
    left = [
        ("1", "3V3", "power_out", -15.24, 25.4),
        ("2", "EN", "input", -15.24, 22.86),
        ("6", "IO34", "input", -15.24, 17.78),
        ("7", "IO35", "input", -15.24, 15.24),
        ("8", "IO32", "bidirectional", -15.24, 12.7),
        ("9", "IO33", "bidirectional", -15.24, 10.16),
        ("10", "IO25", "bidirectional", -15.24, 7.62),
        ("11", "IO26", "bidirectional", -15.24, 5.08),
        ("12", "IO27", "bidirectional", -15.24, 2.54),
        ("13", "IO14", "bidirectional", -15.24, 0),
        ("14", "GND", "power_in", -15.24, -2.54),
        ("15", "IO13", "bidirectional", -15.24, -5.08),
        ("19", "5V", "power_in", -15.24, -12.7),
    ]
    right = [
        ("20", "GND", "power_in", 15.24, 25.4),
        ("21", "IO23", "bidirectional", 15.24, 22.86),
        ("22", "IO22", "bidirectional", 15.24, 20.32),
        ("23", "TXD0", "output", 15.24, 17.78),
        ("24", "RXD0", "input", 15.24, 15.24),
        ("25", "IO21", "bidirectional", 15.24, 12.7),
        ("26", "GND", "power_in", 15.24, 10.16),
        ("27", "IO19", "bidirectional", 15.24, 7.62),
        ("28", "IO18", "bidirectional", 15.24, 5.08),
        ("29", "IO5", "bidirectional", 15.24, 2.54),
        ("30", "IO17", "bidirectional", 15.24, 0),
        ("31", "IO16", "bidirectional", 15.24, -2.54),
        ("32", "IO4", "bidirectional", 15.24, -5.08),
        ("33", "IO0", "bidirectional", 15.24, -7.62),
        ("34", "IO2", "bidirectional", 15.24, -10.16),
        ("35", "IO15", "bidirectional", 15.24, -12.7),
    ]

    def pin_sexpr(num, name, ptype, x, y):
        rot = 0 if x < 0 else 180
        return f'''\t\t\t(pin {ptype} line
\t\t\t\t(at {x} {y} {rot})
\t\t\t\t(length 2.54)
\t\t\t\t(name "{name}"
\t\t\t\t\t(effects (font (size 1.27 1.27)))
\t\t\t\t)
\t\t\t\t(number "{num}"
\t\t\t\t\t(effects (font (size 1.27 1.27)))
\t\t\t\t)
\t\t\t)'''

    pins = "\n".join(pin_sexpr(*p) for p in left + right)
    return f'''\t(symbol "Fiberboard:ESP32_DevKitC_Socket"
\t\t(exclude_from_sim no)
\t\t(in_bom yes)
\t\t(on_board yes)
\t\t(property "Reference" "U"
\t\t\t(at -12.7 29.21 0)
\t\t\t(effects (font (size 1.27 1.27)) (justify left))
\t\t)
\t\t(property "Value" "ESP32_DevKitC_Socket"
\t\t\t(at 0 29.21 0)
\t\t\t(effects (font (size 1.27 1.27)) (justify left))
\t\t)
\t\t(property "Footprint" "Fiberboard:ESP32_DevKitC_Socket"
\t\t\t(at 0 0 0)
\t\t\t(hide yes)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(property "Datasheet" ""
\t\t\t(at 0 0 0)
\t\t\t(hide yes)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(property "Description" "ESP32-DevKitC module on female pin socket"
\t\t\t(at 0 0 0)
\t\t\t(hide yes)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(property "ki_keywords" "ESP32 DevKit socket"
\t\t\t(at 0 0 0)
\t\t\t(hide yes)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(symbol "ESP32_DevKitC_Socket_0_1"
\t\t\t(rectangle
\t\t\t\t(start -12.7 27.94)
\t\t\t\t(end 12.7 -15.24)
\t\t\t\t(stroke (width 0.254) (type default))
\t\t\t\t(fill (type background))
\t\t\t)
\t\t)
\t\t(symbol "ESP32_DevKitC_Socket_1_1"
{pins}
\t\t)
\t)'''


def make_fiber_clamp_footprint() -> str:
    return f'''(footprint "Fiber_Clamp_2CH"
\t(version 20241229)
\t(generator "fiberboard_gen")
\t(layer "F.Cu")
\t(descr "Plastic fiber clamp seats for 2 optical channels + LED/PT pads")
\t(tags "fiber optic clamp")
\t(property "Reference" "J"
\t\t(at 0 8 0)
\t\t(layer "F.SilkS")
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(property "Value" "Fiber_Clamp_2CH"
\t\t(at 0 -10 0)
\t\t(layer "F.Fab")
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(attr through_hole)
\t(fp_rect (start -12 6) (end 12 -6)
\t\t(stroke (width 0.15) (type default)) (fill none) (layer "F.SilkS") (uuid "{uid()}"))
\t(fp_text user "FIBER1" (at -6 4.5 0) (layer "F.SilkS") (uuid "{uid()}")
\t\t(effects (font (size 0.8 0.8) (thickness 0.12))))
\t(fp_text user "FIBER2" (at 6 4.5 0) (layer "F.SilkS") (uuid "{uid()}")
\t\t(effects (font (size 0.8 0.8) (thickness 0.12))))
\t(pad "1" thru_hole circle (at -8 0) (size 1.7 1.7) (drill 1.0) (layers "*.Cu" "*.Mask") (uuid "{uid()}"))
\t(pad "2" thru_hole circle (at -4 0) (size 1.7 1.7) (drill 1.0) (layers "*.Cu" "*.Mask") (uuid "{uid()}"))
\t(pad "3" thru_hole circle (at 4 0) (size 1.7 1.7) (drill 1.0) (layers "*.Cu" "*.Mask") (uuid "{uid()}"))
\t(pad "4" thru_hole circle (at 8 0) (size 1.7 1.7) (drill 1.0) (layers "*.Cu" "*.Mask") (uuid "{uid()}"))
\t(pad "5" thru_hole circle (at 0 -3.5) (size 1.7 1.7) (drill 1.0) (layers "*.Cu" "*.Mask") (uuid "{uid()}"))
\t(embedded_fonts no)
)
'''


def _vl_th_pad(num: str, x: float, y: float) -> str:
    """Versatile Link horizontal: 2.54 mm pitch, 7.62 mm rows, 1.02 mm drill (datasheet)."""
    return (
        f'\t(pad "{num}" thru_hole circle (at {x} {y}) (size 1.85 1.85) (drill 1.02)\n'
        f'\t\t(layers "*.Cu" "*.Mask") (uuid "{uid()}"))'
    )


def make_afbr_1624z_footprint() -> str:
    """AFBR-1624Z TX — Broadcom Versatile Link DIP (pin 2 absent), fiber port -Y."""
    # Row near fiber (y=-3.81): pins 4,3,·,1 left→right | Row y=+3.81: pins 5,8
    pads = "\n".join(
        [
            _vl_th_pad("1", 3.81, -3.81),
            _vl_th_pad("3", -1.27, -3.81),
            _vl_th_pad("4", -3.81, -3.81),
            _vl_th_pad("5", -3.81, 3.81),
            _vl_th_pad("8", 3.81, 3.81),
        ]
    )
    return f'''(footprint "AFBR_1624Z_VL"
\t(version 20241229)
\t(generator "fiberboard_gen")
\t(layer "F.Cu")
\t(descr "AFBR-1624Z Versatile Link horizontal POF TX, 1mm fiber, Avago/Broadcom layout")
\t(tags "AFBR POF fiber optic VersatileLink")
\t(property "Reference" "U"
\t\t(at 0 11 0)
\t\t(layer "F.Fab")
\t\t(hide yes)
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(property "Value" "AFBR-1624Z"
\t\t(at 0 -11 0)
\t\t(layer "F.Fab")
\t\t(hide yes)
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(property "Datasheet" "https://docs.broadcom.com/doc/AV02-4369EN"
\t\t(at 0 0 0)
\t\t(layer "F.Fab")
\t\t(hide yes)
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(attr through_hole)
\t(fp_rect (start -6.1 -10.4) (end 6.1 5.6)
\t\t(stroke (width 0.12) (type default)) (fill none) (layer "F.Fab") (uuid "{uid()}"))
\t(fp_rect (start -6.4 -10.7) (end 6.4 5.9)
\t\t(stroke (width 0.1) (type default)) (fill none) (layer "F.CrtYd") (uuid "{uid()}"))
\t(fp_rect (start -6.2 -10.5) (end 6.2 5.7)
\t\t(stroke (width 0.12) (type default)) (fill none) (layer "F.SilkS") (uuid "{uid()}"))
\t(fp_circle (center 0 -9.2) (end 1.2 -9.2)
\t\t(stroke (width 0.15) (type default)) (fill none) (layer "F.SilkS") (uuid "{uid()}"))
\t(fp_text user "POF 1mm" (at 0 -9.2 0) (layer "F.SilkS") (uuid "{uid()}")
\t\t(effects (font (size 0.65 0.65) (thickness 0.1))))
{pads}
\t(embedded_fonts no)
)
'''


def make_afbr_2624z_footprint() -> str:
    """AFBR-2624Z RX — Versatile Link DIP 4+2 mount pins, fiber port -Y."""
    pads = "\n".join(
        [
            _vl_th_pad("1", 3.81, -3.81),
            _vl_th_pad("2", 1.27, -3.81),
            _vl_th_pad("3", -1.27, -3.81),
            _vl_th_pad("4", -3.81, -3.81),
            _vl_th_pad("5", -3.81, 3.81),
            _vl_th_pad("8", 3.81, 3.81),
        ]
    )
    return f'''(footprint "AFBR_2624Z_VL"
\t(version 20241229)
\t(generator "fiberboard_gen")
\t(layer "F.Cu")
\t(descr "AFBR-2624Z Versatile Link horizontal POF RX, 1mm fiber, Avago/Broadcom layout")
\t(tags "AFBR POF fiber optic VersatileLink")
\t(property "Reference" "U"
\t\t(at 0 11 0)
\t\t(layer "F.Fab")
\t\t(hide yes)
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(property "Value" "AFBR-2624Z"
\t\t(at 0 -11 0)
\t\t(layer "F.Fab")
\t\t(hide yes)
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(property "Datasheet" "https://docs.broadcom.com/doc/AV02-4369EN"
\t\t(at 0 0 0)
\t\t(layer "F.Fab")
\t\t(hide yes)
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(attr through_hole)
\t(fp_rect (start -6.1 -10.4) (end 6.1 5.6)
\t\t(stroke (width 0.12) (type default)) (fill none) (layer "F.Fab") (uuid "{uid()}"))
\t(fp_rect (start -6.4 -10.7) (end 6.4 5.9)
\t\t(stroke (width 0.1) (type default)) (fill none) (layer "F.CrtYd") (uuid "{uid()}"))
\t(fp_rect (start -6.2 -10.5) (end 6.2 5.7)
\t\t(stroke (width 0.12) (type default)) (fill none) (layer "F.SilkS") (uuid "{uid()}"))
\t(fp_circle (center 0 -9.2) (end 1.2 -9.2)
\t\t(stroke (width 0.15) (type default)) (fill none) (layer "F.SilkS") (uuid "{uid()}"))
\t(fp_text user "POF 1mm" (at 0 -9.2 0) (layer "F.SilkS") (uuid "{uid()}")
\t\t(effects (font (size 0.65 0.65) (thickness 0.1))))
{pads}
\t(embedded_fonts no)
)
'''


def make_pc817_so4_footprint() -> str:
    """PC817 / SO-4 SMD optocoupler (typical 4.4 x 3.9 mm body, 2.54 mm pitch)."""
    return f'''(footprint "PC817_SO4"
\t(version 20241229)
\t(generator "fiberboard_gen")
\t(layer "F.Cu")
\t(descr "PC817 SO-4 SMD optocoupler")
\t(tags "opto SOIC4")
\t(property "Reference" "U"
\t\t(at 0 0 0)
\t\t(layer "F.Fab")
\t\t(hide yes)
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(property "Value" "PC817"
\t\t(at 0 0 0)
\t\t(layer "F.Fab")
\t\t(hide yes)
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(attr smd)
\t(fp_rect (start -2.2 -1.95) (end 2.2 1.95)
\t\t(stroke (width 0.12) (type default)) (fill none) (layer "F.Fab") (uuid "{uid()}"))
\t(fp_rect (start -2.45 -2.2) (end 2.45 2.2)
\t\t(stroke (width 0.1) (type default)) (fill none) (layer "F.CrtYd") (uuid "{uid()}"))
\t(pad "1" smd rect (at -1.905 1.27) (size 1.2 0.8) (layers "F.Cu" "F.Paste" "F.Mask") (uuid "{uid()}"))
\t(pad "2" smd rect (at -1.905 -1.27) (size 1.2 0.8) (layers "F.Cu" "F.Paste" "F.Mask") (uuid "{uid()}"))
\t(pad "3" smd rect (at 1.905 -1.27) (size 1.2 0.8) (layers "F.Cu" "F.Paste" "F.Mask") (uuid "{uid()}"))
\t(pad "4" smd rect (at 1.905 1.27) (size 1.2 0.8) (layers "F.Cu" "F.Paste" "F.Mask") (uuid "{uid()}"))
\t(embedded_fonts no)
)
'''


def make_g6ku_2f_smd_footprint() -> str:
    """Omron G6KU-2F SMD signal relay — pad pattern per datasheet outline (verify before fab)."""
    return f'''(footprint "G6KU-2F_SMD"
\t(version 20241229)
\t(generator "fiberboard_gen")
\t(layer "F.Cu")
\t(descr "Omron G6KU-2F SMD SPDT relay")
\t(tags "relay SMD G6K")
\t(property "Reference" "K"
\t\t(at 0 0 0)
\t\t(layer "F.Fab")
\t\t(hide yes)
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(property "Value" "G6KU-2F-Y"
\t\t(at 0 0 0)
\t\t(layer "F.Fab")
\t\t(hide yes)
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(attr smd)
\t(fp_rect (start -5.5 -3.6) (end 5.5 3.6)
\t\t(stroke (width 0.12) (type default)) (fill none) (layer "F.Fab") (uuid "{uid()}"))
\t(fp_rect (start -5.75 -3.85) (end 5.75 3.85)
\t\t(stroke (width 0.1) (type default)) (fill none) (layer "F.CrtYd") (uuid "{uid()}"))
\t(pad "1" smd rect (at -4.75 2.54) (size 1.5 0.9) (layers "F.Cu" "F.Paste" "F.Mask") (uuid "{uid()}"))
\t(pad "2" smd rect (at -4.75 0) (size 1.5 0.9) (layers "F.Cu" "F.Paste" "F.Mask") (uuid "{uid()}"))
\t(pad "3" smd rect (at -4.75 -2.54) (size 1.5 0.9) (layers "F.Cu" "F.Paste" "F.Mask") (uuid "{uid()}"))
\t(pad "4" smd rect (at 4.75 -2.54) (size 1.5 0.9) (layers "F.Cu" "F.Paste" "F.Mask") (uuid "{uid()}"))
\t(pad "5" smd rect (at 4.75 2.54) (size 1.5 0.9) (layers "F.Cu" "F.Paste" "F.Mask") (uuid "{uid()}"))
\t(embedded_fonts no)
)
'''


def make_fiber_clamp_1ch_footprint() -> str:
    return f'''(footprint "Fiber_Clamp_1CH"
\t(version 20241229)
\t(generator "fiberboard_gen")
\t(layer "F.Cu")
\t(descr "Plastic fiber clamp seat, 1 optical channel + LED/GND pads")
\t(tags "fiber optic clamp")
\t(property "Reference" "J"
\t\t(at 0 5.5 0)
\t\t(layer "F.Fab")
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(property "Value" "Fiber_Clamp_1CH"
\t\t(at 0 -5.5 0)
\t\t(layer "F.Fab")
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(attr through_hole)
\t(fp_rect (start -5 4) (end 5 -4)
\t\t(stroke (width 0.15) (type default)) (fill none) (layer "F.SilkS") (uuid "{uid()}"))
\t(fp_rect (start -5.25 4.25) (end 5.25 -4.25)
\t\t(stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd") (uuid "{uid()}"))
\t(pad "1" thru_hole rect (at -2.54 0) (size 1.7 1.7) (drill 1.0) (layers "*.Cu" "*.Mask") (uuid "{uid()}"))
\t(pad "2" thru_hole circle (at 0 0) (size 1.7 1.7) (drill 1.0) (layers "*.Cu" "*.Mask") (uuid "{uid()}"))
\t(pad "3" thru_hole circle (at 2.54 0) (size 1.7 1.7) (drill 1.0) (layers "*.Cu" "*.Mask") (uuid "{uid()}"))
\t(embedded_fonts no)
)
'''


def pcb_to_sch(x: float, y: float) -> tuple[float, float]:
    return SCH_OX + x * SCH_SCALE, SCH_OY + y * SCH_SCALE


def build_schematic() -> str:
    """Fully net-connected schematic: labels on pin tips + local wires."""
    symbols_needed = [
        (SYM_DIR / "Device.kicad_sym", "R"),
        (SYM_DIR / "Device.kicad_sym", "C"),
        (SYM_DIR / "Device.kicad_sym", "LED"),
        (SYM_DIR / "Device.kicad_sym", "D"),
        (SYM_DIR / "Device.kicad_sym", "L"),
        (SYM_DIR / "Device.kicad_sym", "Fuse"),
        (SYM_DIR / "Device.kicad_sym", "D_TVS"),
        (SYM_DIR / "Transistor_FET.kicad_sym", "Q_PMOS_GSD"),
        (SYM_DIR / "Transistor_FET.kicad_sym", "AO3400A"),
        (SYM_DIR / "Transistor_BJT.kicad_sym", "2N3904"),
        (SYM_DIR / "Interface_UART.kicad_sym", "MAX485E"),
        (SYM_DIR / "Regulator_Linear.kicad_sym", "AMS1117-3.3"),
        (SYM_DIR / "Regulator_Switching.kicad_sym", "XL1509-5.0"),
        (SYM_DIR / "power.kicad_sym", "GND"),
        (SYM_DIR / "power.kicad_sym", "+3V3"),
        (SYM_DIR / "power.kicad_sym", "+5V"),
        (SYM_DIR / "power.kicad_sym", "+24V"),
        (SYM_DIR / "power.kicad_sym", "PWR_FLAG"),
    ]

    lib_blocks = [all_symbols_for_schematic_embed()]
    for path_, name in symbols_needed:
        try:
            lib_blocks.extend(extract_symbol(path_, name))
        except Exception as exc:
            print(f"WARN skip {name}: {exc}")

    return emit_connected_schematic(
        project=PROJECT,
        sheet_uuid=SHEET_UUID,
        lib_blocks=lib_blocks,
        place_symbol=place_symbol,
        global_label=global_label,
        text_box=text_box,
        wire=wire,
    )


def _load_mod_body(fp: str) -> str:
    lib, name = fp.split(":", 1)
    if lib == "Fiberboard":
        return (ROOT / "libraries" / "Fiberboard.pretty" / f"{name}.kicad_mod").read_text(encoding="utf-8")
    return extract_footprint(lib, name)


def _place_footprint_sexpr(fp: str, ref: str, value: str, x: float, y: float, rot: float = 0) -> str:
    """Embed a library .kicad_mod as a board footprint at x,y."""
    raw = _load_mod_body(fp)
    # Drop outer (footprint "name" ... ) wrapper content; rebuild header for board
    # Remove leading (footprint "...") and trailing )
    inner = raw.strip()
    if not inner.startswith("(footprint"):
        raise ValueError(fp)
    # Find first newline after opening footprint line
    first_nl = inner.find("\n")
    body = inner[first_nl + 1 :]
    if body.endswith(")"):
        body = body[: body.rfind(")")].rstrip()

    # Strip library-only header keys that conflict when reordering
    skip_keys = {"version", "generator", "generator_version"}
    lines = body.splitlines()
    kept = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^\t\(([A-Za-z0-9_]+)", line)
        if m and m.group(1) in skip_keys:
            # skip this atom (may be multi-line — assume single-line for these keys)
            i += 1
            continue
        kept.append(line)
        i += 1
    body = "\n".join(kept)

    # Remove existing top-level (layer ...) (at ...) (uuid ...) (path ...) if present near head
    body = re.sub(r"^\t\(layer \"[^\"]+\"\)\n", "", body, count=1)
    body = re.sub(r"^\t\(uuid \"[^\"]+\"\)\n", "", body, count=1)
    body = re.sub(r"^\t\(at [^\n]+\)\n", "", body, count=1)

    # Update Reference property value
    body = re.sub(
        r'\(property "Reference" "[^"]*"',
        f'(property "Reference" "{ref}"',
        body,
        count=1,
    )
    body = re.sub(
        r'\(fp_text reference "[^"]*"',
        f'(fp_text reference "{ref}"',
        body,
        count=1,
    )
    # Update Value property if present
    if '(property "Value"' in body:
        body = re.sub(
            r'\(property "Value" "[^"]*"',
            f'(property "Value" "{value}"',
            body,
            count=1,
        )

    # Insert path/sheet after Description-ish properties: before (attr or first fp_/pad
    path_block = (
        f'\t(path "/{SHEET_UUID}")\n'
        f'\t(sheetname "/")\n'
        f'\t(sheetfile "{PROJECT}.kicad_sch")\n'
    )
    if "(path " not in body:
        m_attr = re.search(r"^\t+\(attr ", body, flags=re.M)
        m_fp = re.search(r"^\t+\(fp_", body, flags=re.M)
        m_pad = re.search(r"^\t+\(pad ", body, flags=re.M)
        idx = None
        for m in (m_attr, m_fp, m_pad):
            if m:
                idx = m.start() if idx is None else min(idx, m.start())
        if idx is not None:
            body = body[:idx] + path_block + body[idx:]
        else:
            body = path_block + body

    # Re-indent library body (1 tab) to board footprint body (2 tabs)
    body_lines = []
    for line in body.splitlines():
        if line.startswith("\t"):
            body_lines.append("\t" + line)
        elif line.strip():
            body_lines.append("\t\t" + line)
        else:
            body_lines.append(line)
    body = "\n".join(body_lines)

    return (
        f'\t(footprint "{fp}"\n'
        f'\t\t(layer "F.Cu")\n'
        f'\t\t(uuid "{uid()}")\n'
        f"\t\t(at {x} {y} {rot})\n"
        f"{body}\n"
        f"\t)"
    )


def _pour_zone(net_name: str, layer: str, pts: list[tuple[float, float]]) -> str:
    poly = " ".join(f"(xy {x} {y})" for x, y in pts)
    return f"""\t(zone
\t\t(net 0)
\t\t(net_name "{net_name}")
\t\t(layer "{layer}")
\t\t(uuid "{uid()}")
\t\t(hatch edge 0.5)
\t\t(connect_pads
\t\t\t(clearance 0.5)
\t\t)
\t\t(min_thickness 0.25)
\t\t(fill yes
\t\t\t(thermal_gap 0.5)
\t\t\t(thermal_bridge_width 0.5)
\t\t)
\t\t(polygon
\t\t\t(pts
\t\t\t\t{poly}
\t\t\t)
\t\t)
\t)"""


def copper_pour_zones(board_w: float, board_h: float) -> str:
    """Split GND pours: GND_PWR (input + power stage) vs GND (logic); meet only at NT1/C4."""
    gnd_pwr_polys, gnd_polys = ground_pour_polygons()
    out: list[str] = []
    for layer in ("F.Cu", "B.Cu"):
        for pts in gnd_pwr_polys:
            out.append(_pour_zone("GND_PWR", layer, pts))
        for pts in gnd_polys:
            out.append(_pour_zone("GND", layer, pts))
    return "\n".join(out)


def build_pcb() -> str:
    """Create PCB with footprints, pad nets from schematic connectivity, starter tracks."""
    design = build_logic_design()
    pad_nets = pad_net_table(design)

    comps = {}
    for c in design.comps:
        if c.ref.startswith("#") or not c.footprint or c.ref in comps:
            continue
        comps[c.ref] = c

    placements, graphics, zone_members = build_layout(
        {ref: c.footprint for ref, c in comps.items()}, _load_mod_body
    )

    footprints = []
    fp_group_members: dict[str, list[str]] = {}
    for p in placements:
        c = comps[p.ref]
        try:
            sexpr = _place_footprint_sexpr(c.footprint, p.ref, c.value, p.x, p.y, p.rot)
            sexpr = postprocess_footprint(sexpr, p.rot)
            sexpr = inject_nets_into_footprint(sexpr, p.ref, pad_nets)
            fp_uuid = re.search(r'^\t\t\(uuid "([^"]+)"\)', sexpr, re.M).group(1)
            fp_group_members.setdefault(assembly_group(p.ref), []).append(fp_uuid)
            footprints.append(sexpr)
        except Exception as exc:
            print(f"WARN footprint {p.ref} {c.footprint}: {exc}")

    # KiCad groups: footprint UUIDs only (no silk/gr_rect — those break the PCB editor).
    groups = [
        group_sexpr(name, members)
        for name, members in sorted(fp_group_members.items())
        if members
    ]
    net_decl = ""
    tracks = "\n".join(graphics + groups)

    w, h = BOARD_W, BOARD_H
    edge = f'''\t(gr_rect
\t\t(start 0 0)
\t\t(end {w} {h})
\t\t(stroke
\t\t\t(width 0.15)
\t\t\t(type default)
\t\t)
\t\t(fill none)
\t\t(layer "Edge.Cuts")
\t\t(uuid "{uid()}")
\t)'''

    zone = copper_pour_zones(w, h)

    return f'''(kicad_pcb
\t(version 20241229)
\t(generator "pcbnew")
\t(generator_version "9.0")
\t(general
\t\t(thickness 1.6)
\t\t(legacy_teardrops no)
\t)
\t(paper "A4")
\t(title_block
\t\t(title "Fiberboard AIO Logic PCB")
\t\t(date "2026-10-06")
\t\t(rev "A2")
\t\t(company "Fiberboard")
\t)
\t(layers
\t\t(0 "F.Cu" signal)
\t\t(2 "B.Cu" signal)
\t\t(9 "F.Adhes" user "F.Adhesive")
\t\t(11 "B.Adhes" user "B.Adhesive")
\t\t(13 "F.Paste" user)
\t\t(15 "B.Paste" user)
\t\t(5 "F.SilkS" user "F.Silkscreen")
\t\t(7 "B.SilkS" user "B.Silkscreen")
\t\t(1 "F.Mask" user)
\t\t(3 "B.Mask" user)
\t\t(17 "Dwgs.User" user "User.Drawings")
\t\t(19 "Cmts.User" user "User.Comments")
\t\t(21 "Eco1.User" user "User.Eco1")
\t\t(23 "Eco2.User" user "User.Eco2")
\t\t(25 "Edge.Cuts" user)
\t\t(27 "Margin" user)
\t\t(31 "F.CrtYd" user "F.Courtyard")
\t\t(29 "B.CrtYd" user "B.Courtyard")
\t\t(35 "F.Fab" user)
\t\t(33 "B.Fab" user)
\t)
\t(setup
\t\t(pad_to_mask_clearance 0.05)
\t\t(allow_soldermask_bridges_in_footprints no)
\t\t(tenting front back)
\t)
{net_decl}
{edge}
{chr(10).join(footprints)}
{tracks}
{zone}
\t(embedded_fonts no)
)
'''


def build_pro() -> str:
    pro = {
        "board": {
            "design_settings": {
                "defaults": {},
                "diff_pair_dimensions": [],
                "drc_exclusions": [],
                "rules": {
                    "min_clearance": 0.2,
                    "min_track_width": 0.25,
                    "min_via_diameter": 0.6,
                    "min_via_drill": 0.3,
                },
                "track_widths": [0.0, 0.25, 0.4, 0.8, 1.5],
                "via_dimensions": [{"diameter": 0.6, "drill": 0.3}],
            }
        },
        "boards": [],
        "cvpcb": {"equivalence_files": []},
        "libraries": {
            "pinned_footprint_libs": ["Fiberboard"],
            "pinned_symbol_libs": ["Fiberboard"],
        },
        "meta": {"filename": f"{PROJECT}.kicad_pro", "version": 1},
        "net_settings": {
            "classes": [
                {
                    "bus_width": 12,
                    "clearance": 0.2,
                    "diff_pair_gap": 0.25,
                    "diff_pair_via_gap": 0.25,
                    "diff_pair_width": 0.2,
                    "line_style": 0,
                    "microvia_diameter": 0.3,
                    "microvia_drill": 0.1,
                    "name": "Default",
                    "pcb_color": "rgba(0, 0, 0, 0.000)",
                    "schematic_color": "rgba(0, 0, 0, 0.000)",
                    "track_width": 0.25,
                    "via_diameter": 0.6,
                    "via_drill": 0.3,
                    "wire_width": 6,
                },
                {
                    "bus_width": 12,
                    "clearance": 0.3,
                    "diff_pair_gap": 0.25,
                    "diff_pair_via_gap": 0.25,
                    "diff_pair_width": 0.2,
                    "line_style": 0,
                    "microvia_diameter": 0.3,
                    "microvia_drill": 0.1,
                    "name": "Power",
                    "pcb_color": "rgba(0, 0, 0, 0.000)",
                    "schematic_color": "rgba(0, 0, 0, 0.000)",
                    "track_width": 0.8,
                    "via_diameter": 0.8,
                    "via_drill": 0.4,
                    "wire_width": 6,
                },
            ],
            "meta": {"version": 3},
        },
        "pcbnew": {"page_layout_descr_file": ""},
        "schematic": {
            "annotate_start_num": 0,
            "drawing": {
                "dashed_lines_dash_length_ratio": 12.0,
                "dashed_lines_gap_length_ratio": 3.0,
                "default_line_thickness": 6.0,
                "default_text_size": 50.0,
                "field_names": [],
                "intersheets_ref_own_page": False,
                "intersheets_ref_prefix": "",
                "intersheets_ref_short": False,
                "intersheets_ref_show": False,
                "intersheets_ref_suffix": "",
                "junction_size_choice": 3,
                "label_size_ratio": 0.375,
                "operating_point_overlay_i_precision": 3,
                "operating_point_overlay_i_range": "~A",
                "operating_point_overlay_v_precision": 3,
                "operating_point_overlay_v_range": "~V",
                "overbar_offset_ratio": 1.23,
                "pin_symbol_size": 25.0,
                "text_offset_ratio": 0.15,
            },
            "legacy_lib_dir": "",
            "legacy_lib_list": [],
            "meta": {"version": 1},
            "net_format_name": "",
            "page_layout_descr_file": "",
            "plot_directory": "",
            "spice_current_sheet_as_root": False,
            "spice_external_command": "spice \"%I\"",
            "spice_model_current_sheet_as_root": True,
            "spice_save_all_currents": False,
            "spice_save_all_dissipations": False,
            "spice_save_all_voltages": False,
            "subsheet_field_names": [],
            "version": 1,
        },
        "sheets": [["", "Root"]],
        "text_variables": {},
    }
    return json.dumps(pro, indent=2)


def write_lib_tables():
    sym = f'''(sym_lib_table
  (version 7)
  (lib (name "Fiberboard")(type "KiCad")(uri "${{KIPRJMOD}}/libraries/Fiberboard.kicad_sym")(options "")(descr "Fiberboard local symbols"))
)
'''
    fp = f'''(fp_lib_table
  (version 7)
  (lib (name "Fiberboard")(type "KiCad")(uri "${{KIPRJMOD}}/libraries/Fiberboard.pretty")(options "")(descr "Fiberboard local footprints"))
)
'''
    (ROOT / "sym-lib-table").write_text(sym, encoding="utf-8")
    (ROOT / "fp-lib-table").write_text(fp, encoding="utf-8")


def write_local_symbol_lib():
    content = f'''(kicad_symbol_lib
\t(version 20241209)
\t(generator "fiberboard_gen")
\t(generator_version "1.0")
{all_symbols_for_lib()}
)
'''
    (ROOT / "libraries" / "Fiberboard.kicad_sym").write_text(content, encoding="utf-8")


def main():
    (ROOT / "libraries" / "Fiberboard.pretty").mkdir(parents=True, exist_ok=True)
    (ROOT / "libraries" / "Fiberboard.pretty" / "ESP32_DevKitC_Socket.kicad_mod").write_text(
        make_esp32_socket_footprint(), encoding="utf-8"
    )
    (ROOT / "libraries" / "Fiberboard.pretty" / "Fiber_Clamp_2CH.kicad_mod").write_text(
        make_fiber_clamp_footprint(), encoding="utf-8"
    )
    (ROOT / "libraries" / "Fiberboard.pretty" / "Fiber_Clamp_1CH.kicad_mod").write_text(
        make_fiber_clamp_1ch_footprint(), encoding="utf-8"
    )
    (ROOT / "libraries" / "Fiberboard.pretty" / "AFBR_1624Z_VL.kicad_mod").write_text(
        make_afbr_1624z_footprint(), encoding="utf-8"
    )
    (ROOT / "libraries" / "Fiberboard.pretty" / "AFBR_2624Z_VL.kicad_mod").write_text(
        make_afbr_2624z_footprint(), encoding="utf-8"
    )
    (ROOT / "libraries" / "Fiberboard.pretty" / "PC817_SO4.kicad_mod").write_text(
        make_pc817_so4_footprint(), encoding="utf-8"
    )
    (ROOT / "libraries" / "Fiberboard.pretty" / "G6KU-2F_SMD.kicad_mod").write_text(
        make_g6ku_2f_smd_footprint(), encoding="utf-8"
    )
    write_local_symbol_lib()
    write_lib_tables()

    sch = build_schematic()
    (ROOT / f"{PROJECT}.kicad_sch").write_text(sch, encoding="utf-8")
    (ROOT / f"{PROJECT}.kicad_pro").write_text(build_pro(), encoding="utf-8")
    pcb = build_pcb()
    (ROOT / f"{PROJECT}.kicad_pcb").write_text(pcb, encoding="utf-8")

    # DESIGN_NOTES.txt and PWR_24V_PROTECT_BUCK_GUIDE.txt are maintained in repo (not overwritten here).
    pcb_path = ROOT / f"{PROJECT}.kicad_pcb"
    if pcb_path.exists() and "(segment" not in pcb_path.read_text(encoding="utf-8"):
        print(
            "NOTE: PCB has footprints only (no copper). KiCad DRC will report unconnected until you route."
        )
    print(f"Generated project in {ROOT}")


if __name__ == "__main__":
    main()
