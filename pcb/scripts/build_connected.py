"""Replace build_schematic / enhance PCB nets in generate_kicad_project.py via import hooks."""

from __future__ import annotations

import re
import uuid
from collections import defaultdict

from connectivity import (
    Design,
    build_logic_design,
    find_comp,
    label_shape,
    pin_abs,
)


def uid() -> str:
    return str(uuid.uuid4())


# Unused ESP32-DevKitC socket pins (left floating / not routed on this logic board)
_ESP32_NC = {
    "3",
    "4",
    "5",
    "6",
    "13",
    "16",
    "17",
    "18",
    "23",
    "24",
    "27",
    "28",
    "29",
    "33",
    "34",
    "36",
    "37",
    "38",
}


def emit_connected_schematic(
    *,
    project: str,
    sheet_uuid: str,
    lib_blocks: list[str],
    place_symbol,
    global_label,
    text_box,
    wire,
) -> str:
    design = build_logic_design()
    parts: list[str] = []
    labels: list[str] = []
    wires: list[str] = []
    texts = [
        text_box("FIBERBOARD AIO — FULLY NET-CONNECTED SCHEMATIC (rev A3)", 20, 12),
        text_box(
            "Global labels on pin tips = electrical connectivity (no cross-board wires)",
            20,
            18,
        ),
        text_box("POWER / 24V IN PROTECT", 18, 20),
        text_box("J1->F1->L2->RV1/D7->Q12->C4 | buck 5V | LDO 3.3V", 18, 24),
        text_box("FIBER CH1", 195, 28),
        text_box("FIBER CH2", 375, 28),
        text_box("DIGITAL IN", 25, 205),
        text_box("RELAYS / MOSFET / RS485", 25, 265),
    ]

    # Place every component (multi-unit = multiple place with same ref)
    for c in design.comps:
        shown = c.value
        show_value = False
        if c.lib_id == "Device:R" and not c.value.startswith("MOV"):
            shown = f"R {c.value}"
            show_value = True
        elif c.lib_id == "Device:C":
            shown = f"C {c.value}"
            show_value = True
        parts.append(
            place_symbol(
                c.lib_id,
                c.ref,
                shown,
                c.x,
                c.y,
                c.footprint,
                c.rot,
                unit=c.unit,
                pin_count=c.pins,
                in_bom=not c.ref.startswith("#"),
                show_value=show_value,
            )
        )

    # Connect ONLY via global labels exactly on pin tips.
    # Do not draw wires between clusters — Manhattan segments cross and KiCad
    # shorts unrelated nets at intersections.
    occupied: dict[tuple[float, float], str] = {}
    for net, pins in design.nets.items():
        shape = label_shape(net)
        for ref, pin in pins:
            c = find_comp(design, ref, pin)
            if not c:
                continue
            x, y = pin_abs(c, pin)
            key = (round(x, 4), round(y, 4))
            prev = occupied.get(key)
            if prev and prev != net:
                # Two different nets claim the same tip — skip duplicate label
                # (usually dual-unit power pin placed twice). Keep first net.
                continue
            occupied[key] = net
            labels.append(global_label(net, x, y, 0, shape))
            wires.append(
                f'\t(junction\n'
                f'\t\t(at {x} {y})\n'
                f'\t\t(diameter 0)\n'
                f'\t\t(color 0 0 0 0)\n'
                f'\t\t(uuid "{uid()}")\n'
                f'\t)'
            )

    # Explicit no-connects for unused pins (cleans ERC)
    nc_pins: list[tuple[str, str]] = []
    u1 = find_comp(design, "U1", "1")
    if u1:
        for p in _ESP32_NC:
            nc_pins.append(("U1", p))
    for ref, pin in nc_pins:
        c = find_comp(design, ref, pin)
        if not c:
            continue
        x, y = pin_abs(c, pin)
        wires.append(
            f'\t(no_connect\n'
            f'\t\t(at {x} {y})\n'
            f'\t\t(uuid "{uid()}")\n'
            f'\t)'
        )

    body = "\n".join(lib_blocks)
    nl = "\n"
    return (
        "(kicad_sch\n"
        "\t(version 20250114)\n"
        '\t(generator "eeschema")\n'
        '\t(generator_version "9.0")\n'
        f'\t(uuid "{sheet_uuid}")\n'
        '\t(paper "A1")\n'
        "\t(title_block\n"
        '\t\t(title "Fiberboard AIO Logic — Connected")\n'
        '\t\t(date "2026-10-06")\n'
        '\t\t(rev "A3")\n'
        '\t\t(company "Fiberboard")\n'
        '\t\t(comment 1 "All pins net-labeled; wires join local clusters")\n'
        '\t\t(comment 2 "Fiber PWM TX + RC + LM358 ADC + LM393 DIG; relays; RS485")\n'
        "\t)\n"
        "\t(lib_symbols\n"
        f"{body}\n"
        "\t)\n"
        f"{nl.join(texts)}\n"
        f"{nl.join(labels)}\n"
        f"{nl.join(wires)}\n"
        f"{nl.join(parts)}\n"
        "\t(sheet_instances\n"
        '\t\t(path "/"\n'
        '\t\t\t(page "1")\n'
        "\t\t)\n"
        "\t)\n"
        "\t(embedded_fonts no)\n"
        ")\n"
    )


def pad_net_table(design: Design) -> dict[tuple[str, str], str]:
    """(ref, pin) -> net name"""
    m = {}
    for net, pins in design.nets.items():
        for ref, pin in pins:
            m[(ref, pin)] = net
    return m


def inject_nets_into_footprint(
    mod_text: str,
    ref: str,
    pad_nets: dict[tuple[str, str], str],
    net_ids: dict[str, int] | None = None,
) -> str:
    """Add KiCad 10 `(net "name")` inside each pad (before pad's final `)`)."""
    lines = mod_text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r'^(\s*)\(pad "([^"]+)"', line)
        if not m:
            out.append(line)
            i += 1
            continue
        indent, pad_num = m.group(1), m.group(2)
        pad_lines = [line]
        depth = line.count("(") - line.count(")")
        i += 1
        while i < len(lines) and depth > 0:
            pad_lines.append(lines[i])
            depth += lines[i].count("(") - lines[i].count(")")
            i += 1
        block = "\n".join(pad_lines)
        net = pad_nets.get((ref, pad_num))
        if net and "(net " not in block:
            rpos = block.rfind(")")
            block = block[:rpos] + f'\n{indent}\t(net "{net}")\n{indent}' + block[rpos:]
        out.append(block)
    return "\n".join(out)


def pcb_net_declarations(net_ids: dict[str, int]) -> str:
    # KiCad 10 boards use named nets on pads/tracks; no top-level net table required.
    return ""


def simple_tracks(
    design: Design,
    pcb_xy: dict[str, tuple[float, float]],
    net_ids: dict[str, int] | None = None,
) -> str:
    """
    Very simple Manhattan tracks between first PCB parts on each net.
    Uses component origins as proxy (enough for ratsnest + starter routing).
    """
    chunks = []
    for net, pins in design.nets.items():
        refs = []
        for ref, _pin in pins:
            if ref.startswith("#"):
                continue
            if ref in pcb_xy and ref not in refs:
                refs.append(ref)
        if len(refs) < 2:
            continue
        if net not in {
            "+3V3",
            "+5V",
            "+24V",
            "GND",
            "FIBER1_PWM",
            "FIBER2_PWM",
            "FIBER1_ADC",
            "FIBER2_ADC",
            "OUT_RLY1",
            "OUT_RLY2",
            "OUT_MOS",
            "RS485_A",
            "RS485_B",
        }:
            if not (
                net.startswith("F1_")
                or net.startswith("F2_")
                or net.startswith("RLY")
                or net.startswith("MOS")
                or net.startswith("FOOT")
                or net.startswith("NPN")
                or net.startswith("SOL")
                or net.startswith("STAT")
                or net.startswith("RS485")
                or net.startswith("I2C")
                or net.startswith("IN_")
                or net.startswith("FIBER")
            ):
                continue
        width = 0.8 if net in {"+3V3", "+5V", "+24V", "GND"} else 0.35
        a = pcb_xy[refs[0]]
        for ref in refs[1:4]:
            b = pcb_xy[ref]
            mid = (b[0], a[1])
            for x1, y1, x2, y2 in [
                (a[0], a[1], mid[0], mid[1]),
                (mid[0], mid[1], b[0], b[1]),
            ]:
                if abs(x1 - x2) < 0.01 and abs(y1 - y2) < 0.01:
                    continue
                chunks.append(
                    f'\t(segment\n'
                    f'\t\t(start {x1} {y1})\n'
                    f'\t\t(end {x2} {y2})\n'
                    f'\t\t(width {width})\n'
                    f'\t\t(layer "F.Cu")\n'
                    f'\t\t(net "{net}")\n'
                    f'\t\t(uuid "{uid()}")\n'
                    f'\t)'
                )
            a = b
    return "\n".join(chunks)
