"""Zone-based PCB placement: each functional block lives in its own silkscreen box + KiCad group."""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field

from assembly_groups import (
    ASSEMBLY_TITLES,
    CONNECTOR_ANCHORS,
    RLY_PWR_REFS,
    SHARED_LAYOUT_REFS,
    STACK_REFS,
    assembly_group,
)

# Hộp PLC 145×90×40 (145T-1D): giắc trên cạnh dài 145 mm, không phải hai đầu ngắn.
# Lòng thân ~125×90. PCB 118×84: hàng giắc dọc cạnh dài, hai dải trên/dưới.
# Sâu hộp 40 mm: đế + DevKitC cắm chồng có thể chạm nắp — kiểm tra khi lắp.
BOARD_W = 118.0
BOARD_H = 84.0
DIN_RAIL_INSET = 1.5
# Dải giắc: AFBR courtyard ~16.6 mm theo hướng cổng POF.
IO_ROW_DEPTH = 17.6
BOT_CONN_EDGE_GAP = 0.45
BOT_CONN_DEPTH = IO_ROW_DEPTH
BOT_LABEL_ABOVE_CONN = 0.0
BOT_ROW_DEPTH = IO_ROW_DEPTH
COL_GAP = 0.8
COL_INSET = 0.12
PACK_COL_INSET = 0.06
# Bề ngang cột = F.CrtYd (+ nhỏ cho tai nhựa); khe COL_GAP giữa các khối kề nhau.
PLASTIC_EXTRA_W = {"J": 0.35, "AFBR": 0.25}
PLASTIC_STACK_RELAY_W = 10.5
MIN_IO_COL_W = 5.5
INTERIOR_COL_GAP = 0.7
EDGE_MARGIN = 1.0
ZONE_MARGIN = 0.45
ITEM_GAP = 0.35
ITEM_GAP_POWER = 0.4
TEXT_SIZE = 0.85
PIN_TEXT_SIZE = 0.7

_XI0 = DIN_RAIL_INSET
_XI1 = BOARD_W - DIN_RAIL_INSET
_Y_TOP_IO1 = EDGE_MARGIN
_Y_TOP_IO2 = _Y_TOP_IO1 + IO_ROW_DEPTH
_Y_BOT_IO2 = BOARD_H - EDGE_MARGIN
_Y_BOT_IO1 = _Y_BOT_IO2 - IO_ROW_DEPTH
# Giữ tên cũ cho silk/pour đáy.
_Y_IN0 = _Y_TOP_IO2 + 0.45
_Y_STAGE0 = _Y_BOT_IO1 - 0.45
_INTERIOR_H = _Y_STAGE0 - _Y_IN0
# Cạnh dài trên: mọi ngõ vào, kể cả phát/thu quang.
# Cạnh dài dưới: mọi ngõ ra, kể cả RS485.
TOP_IO_REFS = ["J1", "J3", "J4", "F1T", "F1R", "F2T", "F2R"]
BOT_IO_REFS = ["J5", "J6", "J7", "J2", "J8"]
TOP_IO_LEFT = ["J1", "J3", "J4"]
TOP_IO_RIGHT = ["F1T", "F1R", "F2T", "F2R"]
BOT_IO_LEFT = ["J5", "J6", "J7"]
BOT_IO_RIGHT = ["J2", "J8"]
# Bề ngang thân cắm 2EDG5.08 đực (Shopee) ≥ footprint socket trên bo.
EDG_PLUG_BODY_W_2P = 12.0
EDG_PLUG_BODY_W_3P = 15.0
PLUG_INTERIOR_DEPTH = 8.0
# Versatile Link: cổng POF ở local −Y. rot 0 hướng lên mép trên; rot 180 hướng xuống mép dưới.
FRONT_IO_AFBR = frozenset({"F1T", "F1R", "F2T", "F2R"})
# DevKit nằm ngang (rot 90, ~51 × 31 mm). Dịch lên để cột J8 (cạnh dưới) còn chỗ.
CONNECTOR_ZONE_ABOVE_JACK = 0.35
MCU_ZONE_X1 = _XI1
MCU_ZONE_X0 = MCU_ZONE_X1 - 56.0
MCU_ZONE_Y0 = _Y_IN0 + 4.2
MCU_ZONE_Y1 = MCU_ZONE_Y0 + 32.6
# Nguồn bên trái, từ dưới cụm J3/J4 tới sát thân giắc ra (thân 2EDG không chiếm hết dải mép).
PWR_X0 = _XI0
PWR_X1 = MCU_ZONE_X0 - INTERIOR_COL_GAP
PWR_Y0 = _Y_IN0 + 1.4
PWR_Y1 = BOARD_H - 13.8
LOGIC_X0 = MCU_ZONE_X0
POWER_ZONE_W = PWR_X1 - PWR_X0


@dataclass
class Zone:
    name: str
    x0: float
    y0: float
    x1: float
    y1: float
    edge: str  # board edge the zone's connectors face: top/bottom/left/right/none
    refs: list[str]
    item_gap: float = ITEM_GAP
    zone_margin: float = ZONE_MARGIN
    align_top: bool = True
    pack_by_ref_order: bool = False


ZONES = [
    Zone(
        "TOP_IO",
        _XI0,
        _Y_TOP_IO1,
        _XI1,
        _Y_TOP_IO2,
        "top",
        TOP_IO_REFS,
    ),
    Zone(
        "BOT_IO",
        _XI0,
        _Y_BOT_IO1,
        _XI1,
        _Y_BOT_IO2,
        "bottom",
        BOT_IO_REFS,
    ),
    # Nguồn + relay + van: một khối bên trái, linh kiện lớn chung một hàng.
    Zone(
        "PWR_24V_PROTECT_IN",
        PWR_X0,
        PWR_Y0,
        PWR_X1,
        PWR_Y1,
        "none",
        [
            "F1", "L2", "Q12", "RV1", "D7", "C19", "C15", "R17",
            "C4", "C14", "NT1", "D11", "C23", "FB3",
            "U2", "L1", "D8", "C2", "C22", "U3", "C16", "C17", "C7", "C3",
            "FB2", "FB1", "R38", "R36", "R37", "C5", "C18", "C21",
            *RLY_PWR_REFS,
            "K1", "R11", "Q3", "D3",
            "K2", "R12", "Q4", "D4",
            "F3", "Q5", "D5", "R13", "R14",
        ],
        item_gap=ITEM_GAP_POWER,
        zone_margin=0.35,
        align_top=True,
    ),
    Zone(
        "MCU_SIGNAL",
        MCU_ZONE_X0,
        MCU_ZONE_Y0,
        MCU_ZONE_X1,
        MCU_ZONE_Y1,
        "none",
        ["U1"],
        item_gap=0.3,
        zone_margin=0.35,
        pack_by_ref_order=True,
    ),
]

# Silk labels for interior zone boxes (F.SilkS, UTF-8)
ZONE_TITLES: dict[str, str] = {
    "PWR_24V_PROTECT_IN": "Lọc 24V IN",
    "PWR_24V_PROTECT_BULK": "Bulk / GND*",
    "PWR_24V_OUT_J5": "J5 relay",
    "PWR_24V_OUT_J6": "J6 relay",
    "PWR_24V_OUT_J7": "J7 van",
    "PWR_BUCK": "Buck 5V / 3V3",
    "MCU_SIGNAL": "MCU (ESP32)",
}

# KiCad groups: sub-zones map to the same group name as the parent block.
GROUP_ALIAS: dict[str, str] = {
    "PWR_24V_PROTECT_IN": "PWR_24V_PROTECT",
    "PWR_24V_PROTECT_BULK": "PWR_24V_PROTECT",
    "PWR_24V_OUT_J5": "PWR_24V_OUT",
    "PWR_24V_OUT_J6": "PWR_24V_OUT",
    "PWR_24V_OUT_J7": "PWR_24V_OUT",
}


def zone_group(zone_name: str) -> str:
    return GROUP_ALIAS.get(zone_name, zone_name)

OUTPUT_STACK_REFS = STACK_REFS
LAYOUT_FIXED_REFS: frozenset[str] = frozenset()

# Screw terminals: wire entry is on the footprint's +Y side -> rotate to face the board edge
EDGE_ROT = {"top": 180, "bottom": 0, "left": 270, "right": 90, "none": 0}
# U1 nằm ngang cho bo thấp. Cầu chì nằm ngang (cao ~10 mm).
FIXED_ROT = {"U1": 90, "F1": 0, "F2": 0, "F3": 0}


def _io_footprint_rot(ref: str, edge: str) -> float:
    if ref in FRONT_IO_AFBR:
        return 0.0 if edge == "top" else 180.0
    return EDGE_ROT[edge]

# User-facing I/O guidance (F.SilkS, tiếng Việt có dấu): ref -> (chức năng, {pad: nhãn chân})
IO_LABELS: dict[str, tuple[str, dict[str, str]]] = {
    "J1": ("Nguồn", {"1": "+", "2": "GND"}),
    "F1": ("", {}),
    "D7": ("", {}),
    "Q12": ("", {}),
    "F1T": ("Q1 phát", {"4": "PWM"}),
    "F1R": ("Q1 thu", {"1": "TTL"}),
    "F2T": ("Q2 phát", {"4": "PWM"}),
    "F2R": ("Q2 thu", {"1": "TTL"}),
    "J3": ("Chân", {"1": "A", "2": "K"}),
    "J4": ("NPN", {"1": "V+", "2": "SIG", "3": "GND"}),
    "J8": ("RS485 cắm", {"1": "A", "2": "B", "3": "GND"}),
    "J2": ("Keyboard", {"1": "+24", "2": "GND"}),
    "D6": ("Đèn báo", {}),
    "J5": ("Relay 1", {"1": "COM", "2": "NO", "3": "NC"}),
    "J6": ("Relay 2", {"1": "COM", "2": "NO", "3": "NC"}),
    "J7": ("Van", {"1": "+24V", "2": "SOL−"}),
}


def uid() -> str:
    return str(uuid.uuid4())


def silk_escape(txt: str) -> str:
    return txt.replace("\\", "\\\\").replace('"', '\\"')


def _silk_text_width(txt: str, size: float) -> float:
    """Approximate horizontal extent for bottom-edge silk (TrueType / UTF-8)."""
    return max(len(txt), 1) * size * 0.52


@dataclass
class IoColumn:
    ref: str
    x0: float
    x1: float
    cx: float


def _fit_font_size(txt: str, max_w: float, start: float, floor: float = 0.55) -> float:
    size = start
    while size >= floor and _silk_text_width(txt, size) > max_w:
        size -= 0.05
    return max(size, floor)


def _place_one_footprint(
    ref: str,
    geoms: dict,
    rx: float,
    ry: float,
    rot: float,
) -> Placed:
    pts, pads = geoms[ref]
    bb = rotated_bbox(pts, rot)
    fw, fh = bb[2] - bb[0], bb[3] - bb[1]
    ox, oy = round(rx - bb[0], 3), round(ry - bb[1], 3)
    abs_pads = {}
    for n, (px, py) in pads.items():
        qx, qy = rot_pt(px, py, rot)
        abs_pads[n] = (ox + qx, oy + qy)
    return Placed(ref, ox, oy, rot, (rx, ry, rx + fw, ry + fh), abs_pads)


def _plug_body_min_w(ref: str) -> float:
    """Min column width so adjacent 2EDG field plugs do not collide."""
    if ref in ("J4", "J5", "J6", "J8"):
        return EDG_PLUG_BODY_W_3P
    if ref in ("J1", "J2", "J3", "J7"):
        return EDG_PLUG_BODY_W_2P
    return 0.0


def _column_width(ref: str, geoms: dict, rot: float) -> float:
    pts, _ = geoms[ref]
    bb = rotated_bbox(pts, rot)
    fw = bb[2] - bb[0]
    if ref in FRONT_IO_AFBR:
        extra = PLASTIC_EXTRA_W["AFBR"]
    elif ref.startswith("J"):
        extra = PLASTIC_EXTRA_W["J"]
    else:
        extra = 0.5
    body_w = fw + extra
    body_w = max(body_w, _plug_body_min_w(ref))
    if ref in ("J5", "J6", "J7"):
        body_w = max(body_w, PLASTIC_STACK_RELAY_W)
    title, pins = IO_LABELS.get(ref, ("", {}))
    tw = _silk_text_width(title, TEXT_SIZE) if title else 0.0
    pw = max((_silk_text_width(l, PIN_TEXT_SIZE) for l in pins.values()), default=0.0)
    return max(body_w, tw, pw, MIN_IO_COL_W) + 2 * COL_INSET


def _column_width_pack(ref: str, geoms: dict, rot: float) -> float:
    """Pack spacing: socket + thân cắm (không tính silk — nhãn co trong ô)."""
    pts, _ = geoms[ref]
    bb = rotated_bbox(pts, rot)
    fw = bb[2] - bb[0]
    if ref in FRONT_IO_AFBR:
        extra = PLASTIC_EXTRA_W["AFBR"]
    elif ref.startswith("J"):
        extra = PLASTIC_EXTRA_W["J"]
    else:
        extra = 0.5
    body_w = max(fw + extra, _plug_body_min_w(ref))
    if ref in ("J5", "J6", "J7"):
        body_w = max(body_w, PLASTIC_STACK_RELAY_W)
    return max(body_w, MIN_IO_COL_W) + 2 * PACK_COL_INSET


def _pack_io_columns(refs: list[str], x0: float, x1: float, geoms: dict, edge: str) -> list[tuple[str, float, float, float]]:
    """Return [(ref, col_x0, col_x1, col_cx), ...] filling [x0,x1]."""
    if not refs:
        return []
    avail = x1 - x0 - 2 * ZONE_MARGIN
    raw = [_column_width(r, geoms, _io_footprint_rot(r, edge)) for r in refs]
    n_gap = max(len(refs) - 1, 0)
    body_sum = sum(raw)
    if n_gap:
        gap_use = min(COL_GAP, max(0.0, (avail - body_sum) / n_gap))
    else:
        gap_use = 0.0
    row_w = body_sum + gap_use * n_gap
    if row_w > avail + 0.05:
        print(
            f"WARN I/O row tight: {row_w:.1f} mm in {avail:.1f} mm "
            f"({refs[0]}..{refs[-1]}, gap {gap_use:.2f} mm)"
        )
    x = x0 + ZONE_MARGIN + max(0.0, (avail - row_w) / 2)
    out: list[tuple[str, float, float, float]] = []
    for ref, w in zip(refs, raw):
        cx0, cx1 = x, x + w
        out.append((ref, cx0, cx1, (cx0 + cx1) / 2))
        x = cx1 + gap_use
    return out


def _pack_io_columns_from_right(
    refs: list[str],
    x0: float,
    x1: float,
    geoms: dict,
    edge: str = "bottom",
    stick_right: bool = False,
) -> list[tuple[str, float, float, float]]:
    """Pack columns anchored at x1."""
    if not refs:
        return []
    avail = x1 - x0 - 2 * ZONE_MARGIN
    raw = [_column_width_pack(r, geoms, _io_footprint_rot(r, edge)) for r in refs]
    n_gap = max(len(refs) - 1, 0)
    body_sum = sum(raw)
    if n_gap:
        gap_use = min(COL_GAP, max(0.0, (avail - body_sum) / n_gap))
    else:
        gap_use = 0.0
    row_w = body_sum + gap_use * n_gap
    if row_w > avail + 0.05:
        print(
            f"WARN I/O row tight: {row_w:.1f} mm in {avail:.1f} mm "
            f"({refs[0]}..{refs[-1]}, gap {gap_use:.2f} mm)"
        )
    slack = 0.0 if stick_right else max(0.0, (avail - row_w) / 2)
    x_right = x1 - ZONE_MARGIN - slack
    out_rev: list[tuple[str, float, float, float]] = []
    for ref, w in zip(reversed(refs), reversed(raw)):
        cx1 = x_right
        cx0 = cx1 - w
        out_rev.append((ref, cx0, cx1, (cx0 + cx1) / 2))
        x_right = cx0 - gap_use
    out_rev.reverse()
    return out_rev


def layout_edge_io(zone: Zone, geoms: dict) -> tuple[list[Placed], list[IoColumn]]:
    """One row of jacks on the top or bottom edge.

    Screw terminals sit on the left (above the power block). Fiber or RS485
    sits on the right, above or below the ESP32, so their parts do not land
    in the power column.
    """
    if zone.name == "TOP_IO":
        col_specs = _pack_io_columns(TOP_IO_LEFT, zone.x0, MCU_ZONE_X0 - 0.4, geoms, zone.edge)
        col_specs += _pack_io_columns_from_right(
            TOP_IO_RIGHT, MCU_ZONE_X0, zone.x1, geoms, zone.edge, stick_right=True
        )
    elif zone.name == "BOT_IO":
        col_specs = _pack_io_columns(BOT_IO_LEFT, zone.x0, MCU_ZONE_X0 - 0.4, geoms, zone.edge)
        col_specs += _pack_io_columns_from_right(
            BOT_IO_RIGHT, MCU_ZONE_X0, zone.x1, geoms, zone.edge, stick_right=True
        )
    else:
        col_specs = _pack_io_columns(list(zone.refs), zone.x0, zone.x1, geoms, zone.edge)
    placed: list[Placed] = []
    columns: list[IoColumn] = []
    for ref, x0, x1, cx in col_specs:
        if ref not in geoms:
            continue
        rot = _io_footprint_rot(ref, zone.edge)
        pts, _ = geoms[ref]
        bb = rotated_bbox(pts, rot)
        fw, fh = bb[2] - bb[0], bb[3] - bb[1]
        rx = cx - fw / 2
        rx = max(x0 + COL_INSET, min(rx, x1 - COL_INSET - fw))
        if zone.edge == "bottom":
            ry = (zone.y1 - BOT_CONN_EDGE_GAP) - fh
        else:
            ry = zone.y0 + BOT_CONN_EDGE_GAP
        placed.append(_place_one_footprint(ref, geoms, rx, ry, rot))
        columns.append(IoColumn(ref, x0, x1, cx))
    return placed, columns


def _resolve_pin_label_x(
    labels: list[tuple[str, float, float]],
    col_x0: float,
    col_x1: float,
) -> list[tuple[str, float, float]]:
    """labels: (text, desired_cx, width); return (text, cx, size) with no overlap in column."""
    inner_l = col_x0 + COL_INSET
    inner_r = col_x1 - COL_INSET
    items: list[tuple[str, float, float, float]] = []
    for txt, want_cx, w in labels:
        cx = max(inner_l + w / 2, min(want_cx, inner_r - w / 2))
        items.append((txt, cx, w, PIN_TEXT_SIZE))
    items.sort(key=lambda t: t[1])
    for i in range(1, len(items)):
        txt, cx, w, sz = items[i]
        _, pcx, pw, _ = items[i - 1]
        need = pcx + (pw + w) / 2 + 0.12
        if cx < need:
            cx = min(need, inner_r - w / 2)
        items[i] = (txt, cx, w, sz)
    for i in range(len(items) - 2, -1, -1):
        txt, cx, w, sz = items[i]
        _, ncx, nw, _ = items[i + 1]
        need = ncx - (nw + w) / 2 - 0.12
        if cx > need:
            cx = max(inner_l + w / 2, need)
        items[i] = (txt, cx, w, sz)
    return [(t, cx, sz) for t, cx, w, sz in items]


def front_io_silk(
    columns: list[IoColumn],
    placed: dict[str, Placed],
    y_cell_top: float,
    y_cell_bot: float,
    edge: str,
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for col in columns:
        p = placed.get(col.ref)
        if not p:
            continue
        ru, rs = gr_rect(col.x0, y_cell_top, col.x1, y_cell_bot, width=0.12)
        out.append((ru, rs))
        title, pins = IO_LABELS.get(col.ref, ("", {}))
        x0, y0, x1, y1 = p.bbox
        max_w = (col.x1 - col.x0) - 2 * COL_INSET
        # Nhãn nằm phía trong bo (không tràn ra ngoài Edge.Cuts).
        if edge == "top":
            y_title = y1 + 0.55
            y_pin = y1 + 1.7
        else:
            y_title = y0 - 0.85
            y_pin = y0 - 2.05
        if title:
            tsz = _fit_font_size(title, max_w, TEXT_SIZE)
            tw = _silk_text_width(title, tsz)
            out.append(gr_text(title, col.cx - tw / 2, y_title, tsz, truetype=True))
        pin_rows: list[tuple[str, float, float]] = []
        for n, lbl in pins.items():
            if n not in p.pads:
                continue
            px, _py = p.pads[n]
            w = _silk_text_width(lbl, PIN_TEXT_SIZE)
            pin_rows.append((lbl, px, w))
        resolved = _resolve_pin_label_x(pin_rows, col.x0, col.x1)
        for lbl, cx, sz in resolved:
            lw = _silk_text_width(lbl, sz)
            out.append(gr_text(lbl, cx - lw / 2, y_pin, sz, truetype=True))
    return out


def front_io_plug_keepouts(
    columns: list[IoColumn],
    placed: dict[str, Placed],
    zone: Zone,
) -> list[tuple[str, str]]:
    """Cmts.User: vùng thân cắm 2EDG đực hướng vào trong bo."""
    out: list[tuple[str, str]] = []
    y_edge = zone.y1 - BOT_CONN_EDGE_GAP
    for col in columns:
        if col.ref not in placed:
            continue
        if not col.ref.startswith("J"):
            continue
        p = placed[col.ref]
        y_top = min(p.bbox[1], y_edge - PLUG_INTERIOR_DEPTH)
        ru, rs = gr_rect(col.x0, y_top, col.x1, y_edge, layer="Cmts.User", width=0.10)
        out.append((ru, rs))
    return out


def front_io_column_guides(
    columns: list[IoColumn],
    placed: dict[str, Placed],
    stack_placed: list[Placed],
) -> list[tuple[str, str]]:
    """Vertical cell borders from output stacks down through connector band."""
    out: list[tuple[str, str]] = []
    stack_by_col: dict[str, float] = {}
    for col in columns:
        if col.ref not in ("J5", "J6", "J7"):
            continue
        top_y = placed[col.ref].bbox[1] if col.ref in placed else _Y_BOT_IO1
        for sp in stack_placed:
            if sp.bbox[1] < top_y:
                top_y = sp.bbox[1]
        stack_by_col[col.ref] = top_y - 0.3
    y_bot = _Y_BOT_IO2
    for col in columns:
        y_top = stack_by_col.get(col.ref, _Y_BOT_IO1)
        for x in (col.x0, col.x1):
            u, s = gr_rect(x - 0.04, y_top, x + 0.04, y_bot, width=0.08)
            out.append((u, s))
    return out


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
    if edge == "bottom":
        return 0.0, 0.0
    return 0.0, (2.6 if pins else 0.0) + 2.6


def layout_zone(zone: Zone, geoms: dict[str, tuple[list, dict]]) -> list[Placed]:
    edge = zone.edge
    side = edge in ("left", "right")
    zm = zone.zone_margin
    ig = zone.item_gap
    zw = (zone.y1 - zone.y0 if side else zone.x1 - zone.x0) - 2 * zm
    zh = (zone.x1 - zone.x0 if side else zone.y1 - zone.y0) - 2 * zm

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
        items.append((ref, rot, bb, pads, lw, lh, pre_u, post_v, lw * lh))

    if not zone.pack_by_ref_order:
        items.sort(key=lambda t: t[8], reverse=True)

    # Shelf packing in local frame (v=0 is the board-edge side of the zone)
    shelves: list[list] = []
    u = v = shelf_h = 0.0
    cur: list = []
    for it in items:
        ref, rot, bb, pads, lw, lh, pre_u, post_v, _area = it
        tw, th = lw + pre_u, lh + post_v
        if cur and u + tw > zw:
            shelves.append((v, shelf_h, cur))
            v += shelf_h + ig
            u, shelf_h, cur = 0.0, 0.0, []
        cur.append((u, it))
        u += tw + ig
        shelf_h = max(shelf_h, th)
    if cur:
        shelves.append((v, shelf_h, cur))
    used_h = shelves[-1][0] + shelves[-1][1] if shelves else 0.0
    if used_h > zh + 0.01:
        print(f"WARN zone {zone.name} overflow: needs {used_h:.1f} mm, has {zh:.1f} mm")
    if edge == "none" and zone.align_top:
        v_off = 0.0
    elif edge == "none":
        v_off = max(0.0, (zh - used_h) / 2)
    else:
        v_off = 0.0

    placed = []
    for sv, sh, row in shelves:
        row_w = row[-1][0] + row[-1][1][4] + row[-1][1][6]
        u_off = max(0.0, (zw - row_w) / 2)
        for lu, (ref, rot, bb, pads, lw, lh, pre_u, post_v, _area) in row:
            lu = lu + u_off + pre_u
            lv = sv + v_off
            fw, fh = bb[2] - bb[0], bb[3] - bb[1]
            if edge in ("top", "none"):
                rx = zone.x0 + zm + lu
                ry = zone.y0 + zm + lv
            elif edge == "bottom":
                rx = zone.x0 + zm + lu
                ry = zone.y1 - zm - lv - fh
            elif edge == "left":
                rx = zone.x0 + zm + lv
                ry = zone.y0 + zm + lu
            else:  # right
                rx = zone.x1 - zm - lv - fw
                ry = zone.y0 + zm + lu
            ox, oy = round(rx - bb[0], 3), round(ry - bb[1], 3)
            abs_pads = {}
            for n, (px, py) in pads.items():
                qx, qy = rot_pt(px, py, rot)
                abs_pads[n] = (ox + qx, oy + qy)
            placed.append(Placed(ref, ox, oy, rot, (rx, ry, rx + fw, ry + fh), abs_pads))
    return placed


CONNECTOR_ZONE_LABELS: dict[str, str] = {
    "J3": "J3 chân",
    "J4": "J4 NPN",
    "J8": "J8 RS485",
    "F1T": "Q1 quang T",
    "F2T": "Q2 quang T",
}


def _part_spans(refs: list[str], geoms: dict) -> tuple[float, float, int]:
    """(max width, sum of heights, count) in the footprint's placed rotation."""
    widths: list[float] = []
    heights: list[float] = []
    for ref in refs:
        if ref not in geoms:
            continue
        pts, _pads = geoms[ref]
        bb = rotated_bbox(pts, FIXED_ROT.get(ref, 0.0))
        widths.append(bb[2] - bb[0])
        heights.append(bb[3] - bb[1])
    if not widths:
        return 0.0, 0.0, 0
    return max(widths), sum(heights), len(widths)


def layout_connector_zones(
    columns: list[IoColumn],
    anchors: dict[str, Placed],
    geoms: dict,
    stacks: dict[str, list[str]],
    blockers: list[Placed] | None = None,
) -> tuple[list[Placed], list[Zone]]:
    """One rectangle per jack, grown inward from that jack until a placed part."""
    by_col = {c.ref: c for c in columns}
    placed: list[Placed] = []
    zones_out: list[Zone] = []
    blockers = blockers or []
    for j_ref, stack in stacks.items():
        col = by_col.get(j_ref)
        anchor = anchors.get(j_ref)
        if not col or not anchor or not stack:
            continue
        on_top = anchor.bbox[3] < BOARD_H / 2
        max_w, sum_h, n = _part_spans(stack, geoms)
        gap = 0.35 + 0.04 * n
        route_h = 0.6 + 0.08 * n
        route_w = 0.7 + 0.06 * n
        need_h = sum_h + gap * max(n - 1, 0) + 0.4 + route_h
        col_w = (col.x1 - col.x0) - 0.15
        need_w = min(col_w, max(max_w + route_w, max_w + 1.2))
        # Hai linh kiện nhỏ một hàng nếu cột đủ rộng.
        if n >= 4 and col_w > max_w * 2.1:
            need_w = col_w
        cx = col.cx
        x0 = max(col.x0 + 0.08, cx - need_w / 2)
        x1 = min(col.x1 - 0.08, x0 + need_w)
        x0 = max(col.x0 + 0.08, x1 - need_w)
        if on_top:
            y0 = anchor.bbox[3] + CONNECTOR_ZONE_ABOVE_JACK
            y1 = min(_Y_STAGE0, y0 + need_h)
            for b in blockers:
                if b.bbox[2] <= x0 or b.bbox[0] >= x1:
                    continue
                if b.bbox[1] > y0:
                    y1 = min(y1, b.bbox[1] - 0.3)
            edge = "top"
        else:
            y1 = anchor.bbox[1] - CONNECTOR_ZONE_ABOVE_JACK
            y0 = max(_Y_IN0, y1 - need_h)
            for b in blockers:
                if b.bbox[2] <= x0 or b.bbox[0] >= x1:
                    continue
                if b.bbox[3] < y1:
                    y0 = max(y0, b.bbox[3] + 0.3)
            edge = "bottom"
        if y1 - y0 < 2.5:
            print(f"WARN CONN_{j_ref} no room ({y1 - y0:.1f} mm)")
            continue
        z = Zone(
            f"CONN_{j_ref}",
            x0,
            y0,
            x1,
            y1,
            edge,
            stack,
            item_gap=gap,
            zone_margin=0.2,
            pack_by_ref_order=True,
        )
        zones_out.append(z)
        placed.extend(layout_zone(z, geoms))
    return placed, zones_out


def _raw_union(refs: list[str], by_ref: dict[str, Placed]) -> tuple[float, float, float, float] | None:
    boxes = [by_ref[r].bbox for r in refs if r in by_ref]
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _route_pad(n: int, w: float, h: float) -> tuple[float, float]:
    """Clearance outside a part cluster so traces can escape.

    Grows with part count and with the cluster's courtyard area. A tall
    cluster gets extra width (vertical runs); a wide cluster gets extra height.
    """
    pad = 1.45 + 0.26 * math.sqrt(max(n, 1))
    pad += min(0.7, (w * h) / 900.0)
    pad = min(pad, 3.4)
    px = py = pad
    if h > w * 1.65:
        px += min(1.8, 0.16 * n + 0.4)
    elif w > h * 1.65:
        py += min(1.5, 0.10 * n + 0.35)
    return px, py


def _expanded_border(
    raw: tuple[float, float, float, float], n: int
) -> tuple[float, float, float, float]:
    w, h = raw[2] - raw[0], raw[3] - raw[1]
    px, py = _route_pad(n, w, h)
    m = DIN_RAIL_INSET + 0.25
    return (
        max(m, raw[0] - px),
        max(0.4, raw[1] - py),
        min(BOARD_W - m, raw[2] + px),
        min(BOARD_H - EDGE_MARGIN, raw[3] + py),
    )


def _separate_borders(
    borders: dict[str, tuple[float, float, float, float]],
    floors: dict[str, tuple[float, float, float, float]],
    gap: float = 0.4,
) -> dict[str, tuple[float, float, float, float]]:
    """Pull overlapping group rectangles apart without crossing the part cluster."""
    names = list(borders)
    out = dict(borders)
    for _ in range(6):
        for i, na in enumerate(names):
            for nb in names[i + 1 :]:
                a = out[na]
                b = out[nb]
                ox = min(a[2], b[2]) - max(a[0], b[0])
                oy = min(a[3], b[3]) - max(a[1], b[1])
                if ox <= gap or oy <= gap:
                    continue
                fa, fb = floors[na], floors[nb]
                if ox < oy:
                    if (a[0] + a[2]) <= (b[0] + b[2]):
                        split = (max(a[0], b[0]) + min(a[2], b[2])) / 2
                        a = (a[0], a[1], max(fa[2] + 0.35, split - gap / 2), a[3])
                        b = (min(fb[0] - 0.35, split + gap / 2), b[1], b[2], b[3])
                    else:
                        split = (max(b[0], a[0]) + min(b[2], a[2])) / 2
                        b = (b[0], b[1], max(fb[2] + 0.35, split - gap / 2), b[3])
                        a = (min(fa[0] - 0.35, split + gap / 2), a[1], a[2], a[3])
                else:
                    if (a[1] + a[3]) <= (b[1] + b[3]):
                        split = (max(a[1], b[1]) + min(a[3], b[3])) / 2
                        a = (a[0], a[1], a[2], max(fa[3] + 0.35, split - gap / 2))
                        b = (b[0], min(fb[1] - 0.35, split + gap / 2), b[2], b[3])
                    else:
                        split = (max(b[1], a[1]) + min(b[3], a[3])) / 2
                        b = (b[0], b[1], b[2], max(fb[3] + 0.35, split - gap / 2))
                        a = (a[0], min(fa[1] - 0.35, split + gap / 2), a[2], a[3])
                out[na], out[nb] = a, b
    return out


def assembly_zone_graphics(
    placements: list[Placed],
) -> list[str]:
    """Silk box per assembly group: part cluster plus routing margin (not a fixed column)."""
    by_ref = {p.ref: p for p in placements}
    groups: dict[str, list[str]] = {}
    for p in placements:
        groups.setdefault(assembly_group(p.ref), []).append(p.ref)
    borders: dict[str, tuple[float, float, float, float]] = {}
    floors: dict[str, tuple[float, float, float, float]] = {}
    for g, refs in groups.items():
        raw = _raw_union(refs, by_ref)
        if not raw:
            continue
        borders[g] = _expanded_border(raw, len(refs))
        w, h = raw[2] - raw[0], raw[3] - raw[1]
        fx, fy = _route_pad(1, w, h)
        fx, fy = min(fx, 0.55), min(fy, 0.55)
        floors[g] = (raw[0] - fx, raw[1] - fy, raw[2] + fx, raw[3] + fy)
    borders = _separate_borders(borders, floors)
    graphics: list[str] = []
    for g, bb in borders.items():
        title = ASSEMBLY_TITLES.get(g, g)
        _, rs = gr_rect(*bb, width=0.12)
        graphics.append(rs)
        max_w = max(4.0, bb[2] - bb[0] - 1.0)
        tsz = _fit_font_size(title, max_w, 0.75, 0.48)
        tw = _silk_text_width(title, tsz)
        tx = (bb[0] + bb[2]) / 2 - tw / 2
        ty = bb[1] + 0.55
        _, ts = gr_text(title, tx, ty, tsz, truetype=True)
        graphics.append(ts)
    return graphics


_EDGE_CONNECTORS: set[str] = set()


def gr_text(
    txt: str,
    x: float,
    y: float,
    size: float,
    justify: str | None = None,
    *,
    truetype: bool = False,
) -> tuple[str, str]:
    u = uid()
    just = f"\n\t\t\t(justify {justify})" if justify else ""
    face_line = "\t\t\t\t(face truetype)\n" if truetype else ""
    return u, (
        f'\t(gr_text "{silk_escape(txt)}"\n'
        f"\t\t(at {round(x, 3)} {round(y, 3)} 0)\n"
        f'\t\t(layer "F.SilkS")\n'
        f'\t\t(uuid "{u}")\n'
        f"\t\t(effects\n"
        f"\t\t\t(font\n"
        f"{face_line}"
        f"\t\t\t\t(size {size} {size})\n"
        f"\t\t\t\t(thickness {round(size * 0.15, 3)})\n"
        f"\t\t\t){just}\n"
        f"\t\t)\n"
        f"\t)"
    )


def _zone_title_graphics(zone: Zone) -> list[tuple[str, str]]:
    """Zone label at top-inside of rectangle (no justify center — KiCad compatibility)."""
    title = ZONE_TITLES.get(zone.name)
    if not title:
        return []
    cx = (zone.x0 + zone.x1) / 2
    cy = zone.y1 - 1.4
    max_w = zone.x1 - zone.x0 - 2.0
    tsz = _fit_font_size(title, max_w, 0.85, 0.55)
    tw = _silk_text_width(title, tsz)
    return [gr_text(title, cx - tw / 2, cy, tsz, truetype=True)]


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
    if edge == "bottom":
        y_edge = _Y_BOT_IO2 - BOT_EDGE_CLEAR
        y_title = y_edge - 1.05
        y_pins = y_edge - 4.0
        if title:
            tw = _silk_text_width(title, TEXT_SIZE)
            out.append(gr_text(title, cx - tw / 2, y_title, TEXT_SIZE, truetype=True))
        for n, lbl in pins.items():
            if n in p.pads:
                px = p.pads[n][0]
                pw = _silk_text_width(lbl, PIN_TEXT_SIZE)
                out.append(gr_text(lbl, px - pw / 2, y_pins, PIN_TEXT_SIZE, truetype=True))
        return out
    sign = 1
    base = y1
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


def esp32_antenna_silk(u1: Placed) -> list[tuple[str, str]]:
    """Nhãn silk cạnh vùng ăng-ten (hình 18×6.5 nằm trên footprint đế)."""
    label = "Ăng-ten 18×6.5"
    size = 0.7
    lx, ly = 0.0, 6.7
    rx, ry = rot_pt(lx, ly, u1.rot)
    tw = _silk_text_width(label, size)
    return [gr_text(label, u1.x + rx - tw / 2, u1.y + ry, size, truetype=True)]


def build_layout(refs_with_fp: dict[str, str], load_mod) -> tuple[list[Placed], list[str], list[str]]:
    """Return (placements, board graphics sexprs, group sexprs)."""
    _EDGE_CONNECTORS.clear()
    geoms = {}
    for ref, fp in refs_with_fp.items():
        mod = load_mod(fp)
        geoms[ref] = footprint_geometry(mod)
        if (
            fp.startswith("TerminalBlock_")
            or fp.startswith("Fiberboard:Terminal_2EDG")
            or fp.startswith("Connector_PinHeader_")
            or fp.startswith("Fiberboard:AFBR_")
        ):
            _EDGE_CONNECTORS.add(ref)

    zoned = (
        {r for z in ZONES for r in z.refs}
        | STACK_REFS
        | LAYOUT_FIXED_REFS
        | SHARED_LAYOUT_REFS
    )
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

    edge_placed: dict[str, Placed] = {}
    edge_columns: list[IoColumn] = []
    for z in ZONES:
        if z.name in ("TOP_IO", "BOT_IO"):
            placed, columns = layout_edge_io(z, geoms)
            edge_placed.update({p.ref: p for p in placed})
            edge_columns.extend(columns)
            members = []
            ru, rs = gr_rect(z.x0, z.y0, z.x1, z.y1)
            graphics.append(rs)
            members.append(ru)
            for tu, ts in front_io_silk(columns, {p.ref: p for p in placed}, z.y0, z.y1, z.edge):
                graphics.append(ts)
                members.append(tu)
        else:
            placed = layout_zone(z, geoms)
            members = []
            for p in placed:
                for tu, ts in io_texts(p, z.edge):
                    graphics.append(ts)
                    members.append(tu)
        placements += placed
        gname = zone_group(z.name)
        zone_members.setdefault(gname, [])
        zone_members[gname].extend(members)

    conn_placed, _conn_zones = layout_connector_zones(
        edge_columns, edge_placed, geoms, CONNECTOR_ANCHORS, blockers=placements
    )
    placements += conn_placed

    graphics.extend(assembly_zone_graphics(placements))

    # ESP32 USB end (pads 19/38 side), guidance for the programming cable
    u1 = next((p for p in placements if p.ref == "U1"), None)
    if u1:
        for tu, ts in esp32_antenna_silk(u1):
            graphics.append(ts)
            zone_members.setdefault("MCU_SIGNAL", []).append(tu)
    if u1 and "19" in u1.pads and "38" in u1.pads:
        ux = (u1.pads["19"][0] + u1.pads["38"][0]) / 2
        uy = (u1.pads["19"][1] + u1.pads["38"][1]) / 2
        dx, dy = rot_pt(0, -5.0, u1.rot)
        tu, ts = gr_text("USB", ux + dx, uy + dy, TEXT_SIZE)
        graphics.append(ts)
        zone_members.setdefault("MCU_SIGNAL", []).append(tu)

    return placements, graphics, zone_members


def group_sexpr(name: str, members: list[str]) -> str:
    quoted = " ".join(f'"{m}"' for m in members)
    return f'\t(group "{name}"\n\t\t(uuid "{uid()}")\n\t\t(members {quoted})\n\t)'


def ground_pour_polygons() -> tuple[list[list[tuple[float, float]]], list[list[tuple[float, float]]]]:
    """GND_PWR trái (nguồn, relay); GND phải (MCU và giắc tín hiệu)."""
    m = 0.8
    split = MCU_ZONE_X0
    gnd_pwr = [
        [(m, m), (split, m), (split, BOARD_H - m), (m, BOARD_H - m)],
    ]
    gnd = [
        [(split, m), (BOARD_W - m, m), (BOARD_W - m, BOARD_H - m), (split, BOARD_H - m)],
    ]
    return gnd_pwr, gnd
