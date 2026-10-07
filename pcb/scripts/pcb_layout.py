"""Zone-based PCB placement: each functional block lives in its own silkscreen box + KiCad group."""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field

from assembly_groups import (
    ASSEMBLY_TITLES,
    CONNECTOR_ANCHORS,
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
ITEM_GAP_POWER = 1.05
ITEM_GAP_PROTECT = 1.55
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
# Cạnh trên, trái: nguồn vào J1, chân, NPN. Quang bên phải.
# Cạnh dưới, trái → phải: relay 1, relay 2, van, 24 V ra (J2), RS485.
# Phần rộng còn lại đổ vào group đông linh kiện (relay, van, RS485, opto).
TOP_IO_REFS = ["J1", "J3", "J4", "F1T", "F1R", "F2T", "F2R"]
BOT_IO_REFS = ["J5", "J6", "J7", "J2", "J8"]
TOP_IO_LEFT = ["J1", "J3", "J4"]
TOP_IO_RIGHT = ["F1T", "F1R", "F2T", "F2R"]
BOT_IO_LEFT: list[str] = []
BOT_IO_RIGHT = ["J5", "J6", "J7", "J2", "J8"]
# Bề ngang thân cắm 2EDG5.08 đực (Shopee) ≥ footprint socket trên bo.
EDG_PLUG_BODY_W_2P = 12.0
EDG_PLUG_BODY_W_3P = 15.0
PLUG_INTERIOR_DEPTH = 8.0
# Versatile Link: cổng POF ở local −Y. rot 0 hướng lên mép trên; rot 180 hướng xuống mép dưới.
FRONT_IO_AFBR = frozenset({"F1T", "F1R", "F2T", "F2R"})
# DevKit nằm ngang (rot 90). Đường bao module 54.4×27.9 mm, ăng-ten ở +X, không vào dải ray.
CONNECTOR_ZONE_ABOVE_JACK = 0.35
MCU_ZONE_X1 = _XI1
MCU_ZONE_X0 = MCU_ZONE_X1 - 56.0
MCU_ZONE_Y0 = _Y_IN0 + 4.2
MCU_ZONE_Y1 = MCU_ZONE_Y0 + 32.6
# Hai cột nguồn, trái → phải: bảo vệ 24 V rồi buck. Tụ/trở cùng hàng với nút chúng lọc.
PWR_X0 = _XI0
PWR_X1 = MCU_ZONE_X0 - INTERIOR_COL_GAP
PWR_Y0 = _Y_IN0 + 1.4
PWR_Y1 = BOARD_H - 4.2
LOGIC_X0 = MCU_ZONE_X0
POWER_ZONE_W = PWR_X1 - PWR_X0
PROTECT_X1 = 32.0
BUCK_X0 = 32.8
# J1 → F1/L2 → C19/C15 ‖ D7/RV1 → Q12/R17 → C4/C14 → sao mass.
PROTECT_REFS = [
    "F1", "L2", "C19", "C15", "D7", "RV1",
    "Q12", "R17", "C4", "C14", "NT1", "D11", "C23", "FB3",
]
# C16/C17 sát Vin, D8/L1/R38–R37 sát SW và FB, C2/C5 sát ra buck, C7/U3/C3 sát LDO.
BUCK_REFS = [
    "C16", "C17", "U2", "D8", "L1", "R38", "R36", "R37",
    "C2", "C5", "FB2", "C22", "C7", "U3", "C3", "C18", "FB1", "C21",
]
# Mỗi relay một cụm đủ mạch trong cột của cọc. Hàng sát giắc: cuộn + tụ + TVS.
J5_CLUSTER_REFS = ["K1", "C24", "D12", "D3", "Q3", "R11", "FB4", "C25", "D17", "R26"]
J6_CLUSTER_REFS = ["K2", "C26", "D26", "D4", "Q4", "R12", "FB5", "C27", "D18", "R27"]
RELAY_AT_JACK_REFS: frozenset[str] = frozenset(J5_CLUSTER_REFS + J6_CLUSTER_REFS)
# Đèn debug nguồn, đặt cạnh tụ của đúng rail (không chiếm hàng mới).
POWER_DEBUG_REFS: frozenset[str] = frozenset({"D27", "R39", "D25", "R34", "D6", "R16"})
# MOSFET van nằm giữa cọc J7. Nhãn silk "MOS" vì ref/value chip đang ẩn.
J7_CLUSTER_REFS = ["Q5", "D5", "R13", "R14", "D19", "R28"]
VALVE_AT_JACK_REFS: frozenset[str] = frozenset(J7_CLUSTER_REFS)


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
    # Cột trái, ngay dưới J1. C19/C15 cùng hàng TVS/MOV; C14 sát C4; R17 sát Q12.
    Zone(
        "PWR_24V_PROTECT",
        PWR_X0,
        PWR_Y0,
        PROTECT_X1,
        PWR_Y0 + 37.2,
        "none",
        PROTECT_REFS,
        item_gap=0.85,
        zone_margin=0.4,
        align_top=True,
        pack_by_ref_order=True,
    ),
    # Cột phải của khối nguồn, sát rail +24V vừa bảo vệ. Vòng buck không kéo xuống góc.
    Zone(
        "PWR_BUCK",
        BUCK_X0,
        PWR_Y0,
        PWR_X1,
        PWR_Y0 + 35.5,
        "none",
        BUCK_REFS,
        item_gap=0.5,
        zone_margin=0.35,
        align_top=True,
        pack_by_ref_order=True,
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

# Nhãn chữ nằm trên F.Fab: thấy trong KiCad, không vào mực in F.SilkS khi gia công.
ZONE_TITLES: dict[str, str] = {
    "PWR_24V_PROTECT": "Bảo vệ 24V",
    "PWR_BUCK": "Buck 5V / 3V3",
    "MCU_SIGNAL": "MCU",
}

# KiCad groups follow the zone name. Relay/van belong to the terminal groups.
GROUP_ALIAS: dict[str, str] = {}


def zone_group(zone_name: str) -> str:
    return GROUP_ALIAS.get(zone_name, zone_name)

OUTPUT_STACK_REFS = STACK_REFS
LAYOUT_FIXED_REFS: frozenset[str] = frozenset()
# Dải trống dưới ESP32, phía mass logic (x > ranh GND_PWR). Không đè ăng-ten (đầu +X của U1)
# và không vào thân cắm J2. TVS/điện trở A/B vẫn ở cột J8.
# R20/R21 và trở nối tiếp GPIO nằm giữa hai hàng chân đế, không ở dải dưới module.
MCU_SPREAD_REFS: frozenset[str] = frozenset({"U7", "R20", "R21", "R40", "R41", "R42", "R43", "R44", "R45"})
ESP32_POCKET_REFS: frozenset[str] = frozenset({"R20", "R21", "R40", "R41", "R42", "R43", "R44", "R45"})
# R22 hạn dòng D13. Không đặt cạnh đèn — cột J1 rộng nên hai 0805 trông như hai LED.
J1_SERIES_REFS: frozenset[str] = frozenset({"R22"})
# Phần rộng thừa của hàng giắc đổ vào group đông linh kiện. 0 = giữ bề ngang đầu cắm.
COL_EXTRA_WEIGHT: dict[str, float] = {
    "J3": 2.0,
    "J4": 2.0,
    "J5": 6.0,
    "J6": 6.0,
    "J7": 2.0,
    "J8": 2.0,
}
COL_GAP_USE = 1.05

# Screw terminals: wire entry is on the footprint's +Y side -> rotate to face the board edge
EDGE_ROT = {"top": 180, "bottom": 0, "left": 270, "right": 90, "none": 0}
# U1 nằm ngang cho bo thấp. Cầu chì nằm ngang (cao ~10 mm).
FIXED_ROT = {"U1": 90, "F1": 0}


def _io_footprint_rot(ref: str, edge: str) -> float:
    if ref in FRONT_IO_AFBR:
        return 0.0 if edge == "top" else 180.0
    return EDGE_ROT[edge]

# Nhãn giắc (tiếng Việt): ref -> (chức năng, {pad: nhãn chân}). Vẽ trên F.Fab, không in lên bo.
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


def _widen_busy_columns(refs: list[str], raw: list[float], avail: float) -> tuple[list[float], float]:
    """Give leftover row width to jacks whose groups hold many parts."""
    n_gap = max(len(refs) - 1, 0)
    gap = COL_GAP_USE if n_gap else 0.0
    slack = avail - sum(raw) - gap * n_gap
    weights = [COL_EXTRA_WEIGHT.get(r, 0.0) for r in refs]
    wsum = sum(weights)
    if slack > 0.4 and wsum > 0:
        raw = [w + slack * wt / wsum for w, wt in zip(raw, weights)]
    elif n_gap and slack < 0:
        gap = max(0.15, (avail - sum(raw)) / n_gap)
        if sum(raw) + gap * n_gap > avail + 0.05:
            print(
                f"WARN I/O row tight: {sum(raw) + gap * n_gap:.1f} mm in {avail:.1f} mm "
                f"({refs[0]}..{refs[-1]})"
            )
    return raw, gap


def _pack_io_columns(refs: list[str], x0: float, x1: float, geoms: dict, edge: str) -> list[tuple[str, float, float, float]]:
    """Return [(ref, col_x0, col_x1, col_cx), ...] filling [x0,x1]."""
    if not refs:
        return []
    avail = x1 - x0 - 2 * ZONE_MARGIN
    raw = [_column_width(r, geoms, _io_footprint_rot(r, edge)) for r in refs]
    raw, gap_use = _widen_busy_columns(refs, raw, avail)
    x = x0 + ZONE_MARGIN
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
    """Pack columns anchored at x1. Busy groups absorb the spare width."""
    if not refs:
        return []
    avail = x1 - x0 - 2 * ZONE_MARGIN
    raw = [_column_width_pack(r, geoms, _io_footprint_rot(r, edge)) for r in refs]
    raw, gap_use = _widen_busy_columns(refs, raw, avail)
    row_w = sum(raw) + gap_use * max(len(refs) - 1, 0)
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
        # Giãn suốt cạnh dưới. Cột relay / van / RS485 nhận phần rộng thừa.
        col_specs = _pack_io_columns(BOT_IO_LEFT, zone.x0, MCU_ZONE_X0 - 0.4, geoms, zone.edge)
        col_specs += _pack_io_columns_from_right(
            BOT_IO_RIGHT, zone.x0, zone.x1, geoms, zone.edge, stick_right=True
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
        # Cột J8: nới khe để TVS/điện trở không chồng sát mép ESP32.
        gap = 1.35 if j_ref == "J8" else 0.35 + 0.04 * n
        route_h = 0.6 + 0.08 * n
        route_w = 0.7 + 0.06 * n
        need_h = sum_h + gap * max(n - 1, 0) + 0.4 + route_h
        col_w = (col.x1 - col.x0) - 0.15
        need_w = min(col_w, max(max_w + route_w, max_w + 1.2))
        # Đèn + trở một hàng khi cột đủ rộng, kể cả cột chỉ có vài linh kiện.
        if col_w > max_w * 2.1:
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
    angle: float = 0,
) -> tuple[str, str]:
    u = uid()
    just = f"\n\t\t\t(justify {justify})" if justify else ""
    face_line = "\t\t\t\t(face truetype)\n" if truetype else ""
    return u, (
        f'\t(gr_text "{silk_escape(txt)}"\n'
        f"\t\t(at {round(x, 3)} {round(y, 3)} {round(angle % 360, 3):g})\n"
        f'\t\t(layer "F.Fab")\n'
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


def passive_mark_silk(placements: list[Placed], marks: dict[str, str]) -> list[str]:
    """Silk 'R 10k' / 'C 100nF' trên thân điện trở và tụ, để không đọc nhầm thành LED."""
    out: list[str] = []
    for p in placements:
        label = marks.get(p.ref)
        if not label:
            continue
        x0, y0, x1, y1 = p.bbox
        long_side = max(x1 - x0, y1 - y0)
        size = 0.7 if long_side >= 4.0 else 0.42
        while _silk_text_width(label, size) > long_side - 0.2 and size > 0.32:
            size = round(size - 0.02, 2)
        ang = p.rot % 360
        if 90 < ang <= 270:
            ang = (ang + 180) % 360
        _, ts = gr_text(label, (x0 + x1) / 2, (y0 + y1) / 2, size, angle=ang)
        out.append(ts)
    return out


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
            if re.search(r'\((?:property "(?:Reference|Value)"|fp_text (?:reference|value))', text):
                if "(hide yes)" not in text:
                    text = text.replace("(effects", "(hide yes)\n\t\t\t(effects", 1)
        out.append(text)
    return "\n".join(out)


def _column_ceiling(col: IoColumn, blockers: list[Placed], y_jack: float) -> float:
    """Highest board-y (smallest y) still clear of parts already placed in this column."""
    y0 = _Y_IN0
    for b in blockers:
        if b.bbox[2] <= col.x0 + 0.2 or b.bbox[0] >= col.x1 - 0.2:
            continue
        if b.bbox[3] < y_jack:
            y0 = max(y0, b.bbox[3] + 0.4)
    return y0


def _pocket_right(anchor: Placed, placed: list[Placed], x_limit: float) -> tuple[float, float, float]:
    """Free strip immediately right of anchor, starting below anything already there."""
    x0 = anchor.bbox[2] + 0.35
    y0 = anchor.bbox[1]
    y1 = anchor.bbox[3]
    for p in placed:
        if p.bbox[2] <= x0 - 0.05 or p.bbox[0] >= x_limit:
            continue
        if p.bbox[3] <= y0 or p.bbox[1] >= y1:
            continue
        y0 = max(y0, p.bbox[3] + 0.3)
    return x0, y0, y1


def _stack_in_pocket(
    refs: list[str],
    x: float,
    y: float,
    y_limit: float,
    geoms: dict,
) -> list[Placed] | None:
    out: list[Placed] = []
    for ref in refs:
        _w, h = _fp_size(ref, geoms)
        if y + h > y_limit + 0.05:
            return None
        out.append(_place_one_footprint(ref, geoms, x, y, 0.0))
        y += h + 0.28
    return out


def _debug_silk(txt: str, x: float, y: float) -> str:
    tsz = 0.55
    _uid, silk = gr_text(txt, x, y, tsz, truetype=True)
    return silk


def layout_power_debug_leds(placements: list[Placed], geoms: dict) -> tuple[list[Placed], list[str]]:
    """Debug LEDs in existing gaps: 24V beside C4, 5V beside C2, 3V3 between C22 and U3."""
    by = {p.ref: p for p in placements}
    out: list[Placed] = []
    silk: list[str] = []

    def put(anchor_ref: str, refs: list[str], x_limit: float) -> list[Placed] | None:
        anchor = by[anchor_ref]
        x, y, y_limit = _pocket_right(anchor, placements + out, x_limit)
        stacked = _stack_in_pocket(refs, x, y, y_limit, geoms)
        if stacked is None or stacked[-1].bbox[2] > x_limit:
            print(f"WARN debug LED {refs[0]} does not fit beside {anchor_ref}")
            return None
        out.extend(stacked)
        return stacked

    p24 = put("C4", ["D27", "R39"], PROTECT_X1 - 0.35)
    if p24 is not None:
        low = p24[-1]
        tw = _silk_text_width("24V", 0.55)
        silk.append(_debug_silk("24V", (low.bbox[0] + low.bbox[2]) / 2 - tw / 2, low.bbox[3] + 1.05))
    p5 = put("C2", ["D25", "R34"], PWR_X1 - 0.3)
    if p5 is not None:
        led = p5[0]
        silk.append(_debug_silk("5V", led.bbox[2] + 0.35, (led.bbox[1] + p5[-1].bbox[3]) / 2))
    # U3 is as tall as C22, so the 3V3 pair sits in the gap under C7, left of U3.
    c22 = by["C22"]
    u3 = by["U3"]
    c7 = by["C7"]
    x_3v3 = c22.bbox[2] + 0.35
    y_3v3 = c7.bbox[3] + 0.3
    stacked = _stack_in_pocket(["D6", "R16"], x_3v3, y_3v3, u3.bbox[3], geoms)
    if stacked is None or stacked[-1].bbox[2] > u3.bbox[0] - 0.25:
        print("WARN debug LED D6 does not fit between C22 and U3")
    else:
        out.extend(stacked)
        low = stacked[-1]
        tw = _silk_text_width("3V3", 0.55)
        silk.append(
            _debug_silk("3V3", (low.bbox[0] + low.bbox[2]) / 2 - tw / 2, low.bbox[3] + 0.6)
        )
    return out, silk


def layout_relay_at_jacks(
    edge_placed: dict[str, Placed],
    columns: list[IoColumn],
    geoms: dict,
    blockers: list[Placed],
) -> list[Placed]:
    """Coil, driver, 5 V filter and LED, shelf-packed in the widened jack column."""
    by_col = {c.ref: c for c in columns}
    placed: list[Placed] = []
    for jack_ref, refs in (("J5", J5_CLUSTER_REFS), ("J6", J6_CLUSTER_REFS)):
        jack = edge_placed[jack_ref]
        col = by_col[jack_ref]
        y1 = jack.bbox[1] - 0.3
        y0 = _column_ceiling(col, blockers, y1)
        if y1 - y0 < 8.0:
            print(f"WARN {jack_ref} relay column only {y1 - y0:.1f} mm tall")
        zone = Zone(
            f"CONN_{jack_ref}",
            col.x0 + 0.15,
            y0,
            col.x1 - 0.15,
            y1,
            "bottom",
            refs,
            item_gap=0.4,
            zone_margin=0.2,
            pack_by_ref_order=True,
        )
        placed.extend(layout_zone(zone, geoms))
    return placed


def _fp_size(ref: str, geoms: dict) -> tuple[float, float]:
    pts, _pads = geoms[ref]
    bb = rotated_bbox(pts, 0.0)
    return bb[2] - bb[0], bb[3] - bb[1]


def layout_valve_at_jack(
    edge_placed: dict[str, Placed],
    columns: list[IoColumn],
    geoms: dict,
) -> tuple[list[Placed], list[str]]:
    """Q5 centered on J7, flyback beside it, silk MOS so the FET is visible."""
    jack = edge_placed["J7"]
    col = next(c for c in columns if c.ref == "J7")
    jx0, jy_in, jx1, _jy1 = jack.bbox
    qw, qh = _fp_size("Q5", geoms)
    dw, dh = _fp_size("D5", geoms)
    gap = 0.5
    span = qw + gap + dw
    xq = jx0 + max(0.3, (jx1 - jx0 - span) / 2.0)
    y_face = jy_in - 0.4
    placed = [
        _place_one_footprint("Q5", geoms, xq, y_face - qh, 0.0),
        _place_one_footprint("D5", geoms, xq + qw + gap, y_face - dh, 0.0),
    ]
    label = "MOS"
    tsz = 0.75
    tw = _silk_text_width(label, tsz)
    label_y = y_face - qh - 1.25
    _uid, silk = gr_text(label, xq + qw / 2.0 - tw / 2.0, label_y, tsz, truetype=True)
    y = label_y - 0.7
    x = col.x0 + 0.3
    x_lim = col.x1 - 0.25
    row_h = 0.0
    for ref in ("R13", "R14", "D19", "R28"):
        w, h = _fp_size(ref, geoms)
        if x + w > x_lim and x > col.x0 + 0.4:
            x = col.x0 + 0.3
            y -= row_h + 0.4
            row_h = 0.0
        placed.append(_place_one_footprint(ref, geoms, x, y - h, 0.0))
        x += w + 0.45
        row_h = max(row_h, h)
    return placed, [silk]


def _esp32_pad_local(pin: int) -> tuple[float, float]:
    """DevKitC 2×19: pin 1 at local (−12.7, 0), pin 19 toward USB (−Y)."""
    if pin <= 19:
        return -12.7, -(pin - 1) * 2.54
    return 12.7, -(pin - 20) * 2.54


# Đèn trạng thái và trở hạn dòng. Trở không đứng cùng hàng với đèn.
_LAMP_PAIRS: tuple[tuple[str, str], ...] = (
    ("D14", "R23"),
    ("D15", "R24"),
    ("D16", "R25"),
    ("D17", "R26"),
    ("D18", "R27"),
    ("D19", "R28"),
    ("D20", "R29"),
    ("D21", "R30"),
    ("D22", "R31"),
    ("D23", "R32"),
    ("D24", "R33"),
)


def _boxes_hit(bb: tuple[float, float, float, float], parts: list[Placed], gap: float = 0.25) -> bool:
    x0, y0, x1, y1 = bb
    for p in parts:
        a = p.bbox
        if x1 + gap <= a[0] or a[2] + gap <= x0 or y1 + gap <= a[1] or a[3] + gap <= y0:
            continue
        return True
    return False


def separate_lamp_resistors(placements: list[Placed], geoms: dict) -> None:
    """Move each series resistor off the LED's row, into the inward gap."""
    by = {p.ref: p for p in placements}
    for led_ref, res_ref in _LAMP_PAIRS:
        led = by.get(led_ref)
        res = by.get(res_ref)
        if led is None or res is None:
            continue
        y_over = min(led.bbox[3], res.bbox[3]) - max(led.bbox[1], res.bbox[1])
        gap_x = max(led.bbox[0], res.bbox[0]) - min(led.bbox[2], res.bbox[2])
        if not (y_over > 0.4 and gap_x < 2.0):
            continue
        w, h = _fp_size(res_ref, geoms)
        cx = (led.bbox[0] + led.bbox[2]) / 2.0
        inward_down = (led.bbox[1] + led.bbox[3]) / 2.0 < BOARD_H / 2.0
        others = [p for p in placements if p.ref != res_ref]
        chosen: tuple[float, float] | None = None
        for gap in (2.4, 1.6, 3.4, 0.7, 4.6, 6.0):
            for dx in (0.0, 2.2, -2.2, 4.4, -4.4):
                x = cx - w / 2.0 + dx
                y = led.bbox[3] + gap if inward_down else led.bbox[1] - gap - h
                bb = (x, y, x + w, y + h)
                if bb[0] < 1.0 or bb[2] > BOARD_W - 1.0 or bb[1] < 1.0 or bb[3] > BOARD_H - 1.0:
                    continue
                if _boxes_hit(bb, others):
                    continue
                chosen = (x, y)
                break
            if chosen:
                break
        if chosen is None:
            print(f"WARN {res_ref} stays beside {led_ref}")
            continue
        moved = _place_one_footprint(res_ref, geoms, chosen[0], chosen[1], 0.0)
        placements[placements.index(res)] = moved
        by[res_ref] = moved


def layout_j1_series_resistor(placements: list[Placed], geoms: dict) -> list[Placed]:
    """R22 in the gap above F1. Only D13 stays on the jack row."""
    d13 = next(p for p in placements if p.ref == "D13")
    f1 = next(p for p in placements if p.ref == "F1")
    w, h = _fp_size("R22", geoms)
    x = (d13.bbox[0] + d13.bbox[2]) / 2.0 - w / 2.0
    y = f1.bbox[1] - 0.35 - h
    if y < d13.bbox[3] + 0.8:
        print("WARN R22 does not fit between D13 and F1")
        return []
    return [_place_one_footprint("R22", geoms, x, y, 0.0)]


def layout_esp32_pocket(placements: list[Placed], geoms: dict) -> list[Placed]:
    """Pulldowns and GPIO series resistors between the two DevKit header rows."""
    u1 = next(p for p in placements if p.ref == "U1")
    # Top header (pin 1 side): fiber PWM and the two pulldowns. Bottom header: RX and UART.
    # Place the antenna-side pin first so a clash shifts the next part toward USB.
    near = [
        ("R40", 7),
        ("R41", 8),
        ("R20", 9),
        ("R21", 10),
        ("R44", 21),
        ("R45", 31),
        ("R42", 32),
        ("R43", 35),
    ]
    w, h = _fp_size(near[0][0], geoms)
    ant_x0 = u1.x + rot_pt(0.0, -0.6, u1.rot)[0]
    out: list[Placed] = []
    for ref, pin in near:
        lx, ly = _esp32_pad_local(pin)
        rx, ry = rot_pt(lx, ly, u1.rot)
        px, py = u1.x + rx, u1.y + ry
        inward = -1.0 if py > u1.y else 1.0
        y_edge = py + inward * (0.85 + 1.15)
        y0 = y_edge - h if inward < 0 else y_edge
        x0 = px - w / 2.0
        placed = None
        for _ in range(24):
            trial = _place_one_footprint(ref, geoms, x0, y0, 0.0)
            clear = trial.bbox[2] <= ant_x0 - 0.3 and not _boxes_hit(trial.bbox, out, 0.25)
            if clear:
                placed = trial
                break
            x0 -= 0.5
        if placed is None:
            print(f"WARN {ref} does not fit in the ESP32 pin gap")
            continue
        out.append(placed)
    return out


def layout_logic_spread(
    columns: list[IoColumn], placements: list[Placed], geoms: dict
) -> list[Placed]:
    """RS485 transceiver in the widened J8 column, under the module."""
    by_col = {c.ref: c for c in columns}
    u1 = next(p for p in placements if p.ref == "U1")
    out: list[Placed] = []

    def open_top(col: IoColumn) -> float:
        """Smallest y of a part already in the column, below the module."""
        y_hit = 71.2
        for p in placements:
            if p.bbox[2] <= col.x0 + 0.2 or p.bbox[0] >= col.x1 - 0.2:
                continue
            if p.bbox[1] > u1.bbox[3]:
                y_hit = min(y_hit, p.bbox[1])
        return y_hit

    j8 = by_col["J8"]
    uw, uh = _fp_size("U7", geoms)
    uy = u1.bbox[3] + 0.5
    if uy + uh < open_top(j8) - 0.3:
        ux = j8.x0 + max(0.4, (j8.x1 - j8.x0 - uw) / 2.0)
        out.append(_place_one_footprint("U7", geoms, ux, uy, 0.0))
    return out


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
        | MCU_SPREAD_REFS
        | RELAY_AT_JACK_REFS
        | VALVE_AT_JACK_REFS
        | POWER_DEBUG_REFS
        | J1_SERIES_REFS
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

    debug_placed, debug_silk = layout_power_debug_leds(placements, geoms)
    placements += debug_placed
    graphics.extend(debug_silk)
    placements += layout_relay_at_jacks(edge_placed, edge_columns, geoms, placements)
    valve_placed, valve_silk = layout_valve_at_jack(edge_placed, edge_columns, geoms)
    placements += valve_placed
    graphics.extend(valve_silk)
    conn_placed, _conn_zones = layout_connector_zones(
        edge_columns, edge_placed, geoms, CONNECTOR_ANCHORS, blockers=placements
    )
    placements += conn_placed
    placements += layout_j1_series_resistor(placements, geoms)
    placements += layout_esp32_pocket(placements, geoms)
    placements += layout_logic_spread(edge_columns, placements, geoms)
    separate_lamp_resistors(placements, geoms)

    graphics.extend(assembly_zone_graphics(placements))

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
