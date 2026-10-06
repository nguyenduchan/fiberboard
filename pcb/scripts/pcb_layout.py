"""Zone-based PCB placement: each functional block lives in its own silkscreen box + KiCad group."""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field

# PLC enclosure 179×100×48 mm (Shopee): PCB 172×98 mm; one front row (power L → signal R).
BOARD_W = 172.0
BOARD_H = 98.0
DIN_RAIL_INSET = 3.0
FRONT_IO_SPLIT = 62.0
BOT_CONN_DEPTH = 41.0
POWER_STAGE_INTERIOR_H = 18.0
POWER_ZONE_W = 48.0
EDGE_MARGIN = 2.0
ZONE_MARGIN = 0.8
ITEM_GAP = 0.4
TEXT_SIZE = 0.9
PIN_TEXT_SIZE = 0.8

_XI0 = DIN_RAIL_INSET
_XI1 = BOARD_W - DIN_RAIL_INSET
_Y_BOT_IO2 = BOARD_H - EDGE_MARGIN
_Y_BOT_IO1 = _Y_BOT_IO2 - BOT_CONN_DEPTH
_Y_IN1 = _Y_BOT_IO1 - 1.5
_Y_STAGE0 = _Y_IN1 - POWER_STAGE_INTERIOR_H
_Y_IN0 = EDGE_MARGIN + 0.5
_Y_SPLIT_A = _Y_IN0 + 22.0
_Y_SPLIT_B = _Y_SPLIT_A + 8.0
_MCU_X0 = _XI0 + POWER_ZONE_W
_MCU_X1 = _XI0 + 72.0


@dataclass
class Zone:
    name: str
    x0: float
    y0: float
    x1: float
    y1: float
    edge: str  # board edge the zone's connectors face: top/bottom/left/right/none
    refs: list[str]


ZONES = [
    # --- Front face: single bottom row (~168 mm connectors + margins fits 172 mm board) ---
    Zone(
        "FRONT_IO",
        _XI0,
        _Y_BOT_IO1,
        _XI1,
        _Y_BOT_IO2,
        "bottom",
        [
            "J1",
            "J5",
            "J6",
            "J7",
            "F1T",
            "F1R",
            "F2T",
            "F2R",
            "J3",
            "J4",
            "J8",
            "J9",
        ],
    ),
    # --- Interior above connector row ---
    Zone(
        "POWER",
        _XI0,
        _Y_IN0,
        _XI0 + POWER_ZONE_W,
        _Y_STAGE0,
        "none",
        [
            "F1", "D7", "Q12", "R17", "C15", "C4", "NT1", "C14",
            "C16", "C17", "U2", "D8", "L1", "R38", "R36", "R37",
            "C2", "C5", "C7", "U3", "C3", "C18",
        ],
    ),
    Zone(
        "FIBER_DECAP",
        FRONT_IO_SPLIT,
        _Y_IN0,
        _XI1,
        _Y_SPLIT_A,
        "none",
        ["C12", "C13"],
    ),
    Zone("RS485", _MCU_X0, _Y_SPLIT_A, _MCU_X0 + 22, _Y_STAGE0, "none", ["U7", "R15"]),
    Zone("MCU", _MCU_X0, _Y_IN0, _MCU_X1, _Y_STAGE0, "none", ["U1"]),
    Zone(
        "INPUTS",
        _MCU_X1,
        _Y_SPLIT_A,
        _XI1,
        _Y_STAGE0,
        "none",
        ["R7", "R8", "U5", "U6", "R9", "R10"],
    ),
    Zone("UI", _MCU_X1, _Y_IN0, _XI1, _Y_SPLIT_A, "none", ["D6", "R16"]),
    Zone(
        "POWER_STAGE",
        _XI0,
        _Y_STAGE0,
        _XI1,
        _Y_IN1,
        "none",
        ["K1", "Q3", "D3", "R11", "K2", "Q4", "D4", "R12", "Q5", "D5", "R13", "R14"],
    ),
]

# Screw terminals: wire entry is on the footprint's +Y side -> rotate to face the board edge
EDGE_ROT = {"top": 180, "bottom": 0, "left": 270, "right": 90, "none": 0}
FIXED_ROT = {"U1": 90}

# User-facing I/O guidance only: ref -> (title, {pad: label})
IO_LABELS: dict[str, tuple[str, dict[str, str]]] = {
    "J1": ("VIN 9-24VDC", {"1": "+", "2": "GND"}),
    "F1": ("", {}),
    "D7": ("", {}),
    "Q12": ("", {}),
    "F1T": ("FIBER1 TX", {"4": "PWM"}),
    "F1R": ("FIBER1 RX", {"1": "DIG"}),
    "F2T": ("FIBER2 TX", {"4": "PWM"}),
    "F2R": ("FIBER2 RX", {"1": "DIG"}),
    "J3": ("FOOT SW IN", {"1": "+", "2": "-"}),
    "J4": ("NPN SENSOR IN", {"1": "V+", "2": "SIG", "3": "GND"}),
    "J8": ("RS485", {"1": "A", "2": "B", "3": "GND"}),
    "J9": ("OLED I2C", {"1": "3V3", "2": "GND", "3": "SDA", "4": "SCL"}),
    "D6": ("STATUS", {}),
    "J5": ("RELAY1 OUT", {"1": "COM", "2": "NO", "3": "NC"}),
    "J6": ("RELAY2 OUT", {"1": "COM", "2": "NO", "3": "NC"}),
    "J7": ("SOLENOID OUT", {"1": "+24V", "2": "SOL-"}),
}


def uid() -> str:
    return str(uuid.uuid4())


def rot_pt(x: float, y: float, angle: float) -> tuple[float, float]:
    """KiCad RotatePoint: positive angle = CCW on screen (Y down)."""
    a = math.radians(angle)
    c, s = math.cos(a), math.sin(a)
    return x * c + y * s, -x * s + y * c


def _top_items(mod_text: str) -> list[str]:
    """Top-level child s-expressions of a (footprint ...) block."""
    start = mod_text.find("(footprint")
    i = mod_text.find("(", start + 1)
    items = []
    depth = 0
    item_start = None
    while i < len(mod_text):
        ch = mod_text[i]
        if ch == '"':
            j = i + 1
            while j < len(mod_text) and mod_text[j] != '"':
                j += 2 if mod_text[j] == "\\" else 1
            i = j + 1
            continue
        if ch == "(":
            if depth == 0:
                item_start = i
            depth += 1
        elif ch == ")":
            if depth == 0:
                break
            depth -= 1
            if depth == 0 and item_start is not None:
                items.append(mod_text[item_start : i + 1])
        i += 1
    return items


_NUM = r"(-?[\d.]+)"


def footprint_geometry(mod_text: str) -> tuple[list[tuple[float, float]], dict[str, tuple[float, float]]]:
    """Return (outline points for bbox, pad_num -> local pad center)."""
    crtyd: list[tuple[float, float]] = []
    other: list[tuple[float, float]] = []
    pads: dict[str, tuple[float, float]] = {}
    for item in _top_items(mod_text):
        if item.startswith("(pad"):
            m_num = re.match(r'\(pad "([^"]*)"', item)
            m_at = re.search(rf"\(at {_NUM} {_NUM}", item)
            m_sz = re.search(rf"\(size {_NUM} {_NUM}\)", item)
            if not m_at:
                continue
            px, py = float(m_at.group(1)), float(m_at.group(2))
            if m_num and m_num.group(1) and m_num.group(1) not in pads:
                pads[m_num.group(1)] = (px, py)
            r = max(float(m_sz.group(1)), float(m_sz.group(2))) / 2 if m_sz else 0.5
            other += [(px - r, py - r), (px + r, py + r)]
            continue
        if not item.startswith(("(fp_line", "(fp_rect", "(fp_circle", "(fp_arc", "(fp_poly")):
            continue
        pts = [(float(a), float(b)) for a, b in re.findall(rf"\((?:start|end|mid|xy) {_NUM} {_NUM}\)", item)]
        if item.startswith("(fp_circle"):
            c = re.search(rf"\(center {_NUM} {_NUM}\)", item)
            e = re.search(rf"\(end {_NUM} {_NUM}\)", item)
            if c and e:
                cx, cy = float(c.group(1)), float(c.group(2))
                r = math.hypot(float(e.group(1)) - cx, float(e.group(2)) - cy)
                pts = [(cx - r, cy - r), (cx + r, cy + r)]
        if '(layer "F.CrtYd")' in item:
            crtyd += pts
        elif '(layer "F.SilkS")' in item or '(layer "F.Fab")' in item:
            other += pts
    return (crtyd or other), pads


def rotated_bbox(points: list[tuple[float, float]], angle: float) -> tuple[float, float, float, float]:
    rp = [rot_pt(x, y, angle) for x, y in points] or [(0.0, 0.0)]
    xs = [p[0] for p in rp]
    ys = [p[1] for p in rp]
    return min(xs), min(ys), max(xs), max(ys)


@dataclass
class Placed:
    ref: str
    x: float
    y: float
    rot: float
    bbox: tuple[float, float, float, float]  # absolute board coords
    pads: dict[str, tuple[float, float]] = field(default_factory=dict)  # absolute


def _label_reserve(ref: str, edge: str) -> tuple[float, float]:
    """(pre_u, post_v) reserve in the zone-local frame for I/O labels."""
    if ref not in IO_LABELS:
        return 0.0, 0.0
    title, pins = IO_LABELS[ref]
    if edge in ("left", "right"):
        pin_w = max((len(t) for t in pins.values()), default=0) * PIN_TEXT_SIZE * 0.9 + 1.5
        return 2.6, pin_w
    return 0.0, (2.6 if pins else 0.0) + 2.6


def layout_zone(zone: Zone, geoms: dict[str, tuple[list, dict]]) -> list[Placed]:
    edge = zone.edge
    side = edge in ("left", "right")
    zw = (zone.y1 - zone.y0 if side else zone.x1 - zone.x0) - 2 * ZONE_MARGIN
    zh = (zone.x1 - zone.x0 if side else zone.y1 - zone.y0) - 2 * ZONE_MARGIN

    items = []
    for ref in zone.refs:
        if ref not in geoms:
            continue
        pts, pads = geoms[ref]
        rot = FIXED_ROT.get(ref, EDGE_ROT[edge] if ref in _EDGE_CONNECTORS else 0)
        bb = rotated_bbox(pts, rot)
        fw, fh = bb[2] - bb[0], bb[3] - bb[1]
        lw, lh = (fh, fw) if side else (fw, fh)
        pre_u, post_v = _label_reserve(ref, edge)
        items.append((ref, rot, bb, pads, lw, lh, pre_u, post_v))

    # Shelf packing in local frame (v=0 is the board-edge side of the zone)
    shelves: list[list] = []
    u = v = shelf_h = 0.0
    cur: list = []
    for it in items:
        ref, rot, bb, pads, lw, lh, pre_u, post_v = it
        tw, th = lw + pre_u, lh + post_v
        if cur and u + tw > zw:
            shelves.append((v, shelf_h, cur))
            v += shelf_h + ITEM_GAP
            u, shelf_h, cur = 0.0, 0.0, []
        cur.append((u, it))
        u += tw + ITEM_GAP
        shelf_h = max(shelf_h, th)
    if cur:
        shelves.append((v, shelf_h, cur))
    used_h = shelves[-1][0] + shelves[-1][1] if shelves else 0.0
    if used_h > zh + 0.01:
        print(f"WARN zone {zone.name} overflow: needs {used_h:.1f} mm, has {zh:.1f} mm")
    v_off = (zh - used_h) / 2 if edge == "none" else 0.0

    placed = []
    for sv, sh, row in shelves:
        row_w = row[-1][0] + row[-1][1][4] + row[-1][1][6]
        u_off = (zw - row_w) / 2
        for lu, (ref, rot, bb, pads, lw, lh, pre_u, post_v) in row:
            lu = lu + u_off + pre_u
            lv = sv + v_off
            fw, fh = bb[2] - bb[0], bb[3] - bb[1]
            if edge in ("top", "none"):
                rx = zone.x0 + ZONE_MARGIN + lu
                ry = zone.y0 + ZONE_MARGIN + lv
            elif edge == "bottom":
                rx = zone.x0 + ZONE_MARGIN + lu
                ry = zone.y1 - ZONE_MARGIN - lv - fh
            elif edge == "left":
                rx = zone.x0 + ZONE_MARGIN + lv
                ry = zone.y0 + ZONE_MARGIN + lu
            else:  # right
                rx = zone.x1 - ZONE_MARGIN - lv - fw
                ry = zone.y0 + ZONE_MARGIN + lu
            ox, oy = round(rx - bb[0], 3), round(ry - bb[1], 3)
            abs_pads = {}
            for n, (px, py) in pads.items():
                qx, qy = rot_pt(px, py, rot)
                abs_pads[n] = (ox + qx, oy + qy)
            placed.append(Placed(ref, ox, oy, rot, (rx, ry, rx + fw, ry + fh), abs_pads))
    return placed


_EDGE_CONNECTORS: set[str] = set()


def gr_text(txt: str, x: float, y: float, size: float, justify: str | None = None) -> tuple[str, str]:
    u = uid()
    just = f"\n\t\t\t(justify {justify})" if justify else ""
    return u, (
        f'\t(gr_text "{txt}"\n'
        f"\t\t(at {round(x, 3)} {round(y, 3)} 0)\n"
        f'\t\t(layer "F.SilkS")\n'
        f'\t\t(uuid "{u}")\n'
        f"\t\t(effects\n"
        f"\t\t\t(font\n"
        f"\t\t\t\t(size {size} {size})\n"
        f"\t\t\t\t(thickness {round(size * 0.15, 3)})\n"
        f"\t\t\t){just}\n"
        f"\t\t)\n"
        f"\t)"
    )


def gr_rect(x0: float, y0: float, x1: float, y1: float, layer: str = "F.SilkS", width: float = 0.2) -> tuple[str, str]:
    u = uid()
    return u, (
        f"\t(gr_rect\n"
        f"\t\t(start {x0} {y0})\n"
        f"\t\t(end {x1} {y1})\n"
        f"\t\t(stroke\n"
        f"\t\t\t(width {width})\n"
        f"\t\t\t(type default)\n"
        f"\t\t)\n"
        f"\t\t(fill no)\n"
        f'\t\t(layer "{layer}")\n'
        f'\t\t(uuid "{u}")\n'
        f"\t)"
    )


def io_texts(p: Placed, edge: str) -> list[tuple[str, str]]:
    if p.ref not in IO_LABELS:
        return []
    title, pins = IO_LABELS[p.ref]
    x0, y0, x1, y1 = p.bbox
    cx = (x0 + x1) / 2
    out = []
    if edge in ("left", "right"):
        for n, lbl in pins.items():
            if n not in p.pads:
                continue
            py = p.pads[n][1]
            if edge == "left":
                out.append(gr_text(lbl, x1 + 0.8, py, PIN_TEXT_SIZE, "left"))
            else:
                out.append(gr_text(lbl, x0 - 0.8, py, PIN_TEXT_SIZE, "right"))
        if edge == "left":
            out.append(gr_text(title, x0, y0 - 1.3, TEXT_SIZE, "left"))
        else:
            out.append(gr_text(title, x1, y0 - 1.3, TEXT_SIZE, "right"))
        return out
    sign = -1 if edge == "bottom" else 1
    base = y0 if edge == "bottom" else y1
    line = 1.3
    if pins:
        for n, lbl in pins.items():
            if n in p.pads:
                out.append(gr_text(lbl, p.pads[n][0], base + sign * line, PIN_TEXT_SIZE))
        line += 2.4
    out.append(gr_text(title, cx, base + sign * line, TEXT_SIZE))
    return out


def postprocess_footprint(sexpr: str, rot: float) -> str:
    """Rotate pad/text angles with the footprint and move all footprint texts off the silkscreen."""
    lines = sexpr.split("\n")
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^\t\t\((pad|property|fp_text) ", line)
        if not m:
            out.append(line)
            i += 1
            continue
        block = [line]
        depth = line.count("(") - line.count(")")
        i += 1
        while i < len(lines) and depth > 0:
            block.append(lines[i])
            depth += lines[i].count("(") - lines[i].count(")")
            i += 1
        text = "\n".join(block)
        if rot:
            def _rot_at(mm):
                ang = float(mm.group(3)) if mm.group(3) else 0.0
                return f"(at {mm.group(1)} {mm.group(2)} {round((ang + rot) % 360, 3):g})"
            text = re.sub(rf"\(at {_NUM} {_NUM}(?: {_NUM})?\)", _rot_at, text, count=1)
        if m.group(1) != "pad":
            text = text.replace('(layer "F.SilkS")', '(layer "F.Fab")')
        out.append(text)
    return "\n".join(out)


def build_layout(refs_with_fp: dict[str, str], load_mod) -> tuple[list[Placed], list[str], list[str]]:
    """Return (placements, board graphics sexprs, group sexprs)."""
    _EDGE_CONNECTORS.clear()
    geoms = {}
    for ref, fp in refs_with_fp.items():
        mod = load_mod(fp)
        geoms[ref] = footprint_geometry(mod)
        if (
            fp.startswith("TerminalBlock_")
            or fp.startswith("Connector_PinHeader_")
            or fp.startswith("Fiberboard:AFBR_")
        ):
            _EDGE_CONNECTORS.add(ref)

    zoned = {r for z in ZONES for r in z.refs}
    missing = sorted(set(refs_with_fp) - zoned)
    if missing:
        print("WARN refs without zone:", missing)

    placements: list[Placed] = []
    graphics: list[str] = []
    zone_members: dict[str, list[str]] = {}

    # DIN-rail keepout (silk): no parts in left/right strips
    for x0, x1, label in (
        (0, DIN_RAIL_INSET, "DIN"),
        (BOARD_W - DIN_RAIL_INSET, BOARD_W, "DIN"),
    ):
        ru, rs = gr_rect(x0, 0, x1, BOARD_H, layer="Cmts.User", width=0.12)
        graphics.append(rs)
        tu, ts = gr_text(label, (x0 + x1) / 2, BOARD_H / 2, 1.2)
        graphics.append(ts)
        zone_members.setdefault("KEEPOUT", []).extend([ru, tu])

    for z in ZONES:
        placed = layout_zone(z, geoms)
        placements += placed
        members = []
        ru, rs = gr_rect(z.x0, z.y0, z.x1, z.y1)
        graphics.append(rs)
        members.append(ru)
        for p in placed:
            for tu, ts in io_texts(p, z.edge):
                graphics.append(ts)
                members.append(tu)
        zone_members[z.name] = members

    # ESP32 USB end (pads 19/38 side), guidance for the programming cable
    u1 = next((p for p in placements if p.ref == "U1"), None)
    if u1 and "19" in u1.pads and "38" in u1.pads:
        ux = (u1.pads["19"][0] + u1.pads["38"][0]) / 2
        uy = (u1.pads["19"][1] + u1.pads["38"][1]) / 2
        dx, dy = rot_pt(0, -5.0, u1.rot)
        tu, ts = gr_text("USB", ux + dx, uy + dy, TEXT_SIZE)
        graphics.append(ts)
        zone_members["MCU"].append(tu)

    return placements, graphics, zone_members


def group_sexpr(name: str, members: list[str]) -> str:
    quoted = " ".join(f'"{m}"' for m in members)
    return f'\t(group "{name}"\n\t\t(uuid "{uid()}")\n\t\t(members {quoted})\n\t)'


def ground_pour_polygons() -> tuple[list[list[tuple[float, float]]], list[list[tuple[float, float]]]]:
    """GND_PWR / GND pours: power left + bottom-left I/O; logic upper/right."""
    m = 1.0
    xi = DIN_RAIL_INSET
    pw = POWER_ZONE_W
    split = FRONT_IO_SPLIT
    gnd_pwr = [
        [(m, m), (xi + pw, m), (xi + pw, _Y_SPLIT_A), (m, _Y_SPLIT_A)],
        [(m, _Y_STAGE0), (split, _Y_STAGE0), (split, _Y_BOT_IO2), (m, _Y_BOT_IO2)],
    ]
    gnd = [
        [(split, m), (_XI1, m), (_XI1, _Y_BOT_IO1), (split, _Y_BOT_IO1)],
        [(xi + pw, m), (split, m), (split, _Y_STAGE0), (xi + pw, _Y_STAGE0)],
        [(m, _Y_SPLIT_A), (_XI1, _Y_SPLIT_A), (_XI1, _Y_STAGE0), (m, _Y_STAGE0)],
    ]
    return gnd_pwr, gnd
