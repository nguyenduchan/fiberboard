"""Grid autorouter (classic maze / A* with rip-up-and-retry) for fiberboard-logic.kicad_pcb.

Usage:  python autoroute.py [--pcb FILE] [--png preview.png] [--passes N] [--dry]

Algorithm
  * 0.1 mm Manhattan grid, 2 copper layers (F.Cu prefers horizontal, B.Cu vertical).
  * Every pad first gets a straight *stub* leaving the pad (hand-assembly rule: the
    track runs straight out of the pin for >= STUB_LEN mm before it may turn).
  * Nets are connected pad-by-pad (Prim order) with A* (cost = length + wrong-way +
    bend + via), clearance/width-aware obstacle masks, T-joins on the net's own copper.
  * Failed nets are moved to the front and everything is re-routed (up to --passes).
  * GND / GND_PWR are left to the copper pours; SMD ground pads get stub + stitch via.
  * Result is written back as (segment ...) / (via ...) items; earlier ones are replaced.
"""

from __future__ import annotations

import argparse
import heapq
import math
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pcb_parse import Pad, load_board  # noqa: E402

try:  # compiled search core; pure-Python astar() below is the fallback
    from maze_nb import Maze  # noqa: E402
except ImportError:  # pragma: no cover
    Maze = None

G = 0.1  # grid pitch (mm)
CLR = 0.20  # copper clearance (kicad_pro min_clearance)
CLR_POWER = 0.30
SAFE = 0.03  # extra clearance margin for off-grid stub geometry
EDGE_CLR = 0.45  # copper to board edge
STUB_LENS = (0.6, 0.45, 0.3)  # straight run beyond pad edge, preferred first
STUB_LEN_GND = (0.7, 0.9, 1.2, 1.6, 0.5)
VIA_SIGNAL = (0.6, 0.3)
VIA_POWER = (0.8, 0.4)
GND_NETS = ("GND", "GND_PWR")
KEEPOUT_NET = -999_999
GND_STITCH = False  # True: old behaviour (pads -> stub + via into the pour, no tracks)

# cost model (integers, 10 == one grid step)
C_STEP = 10
C_WRONG = 5
C_BEND = 25
C_VIA = 140
MAX_EXPAND = 500_000  # pure-Python search
MAX_EXPAND_NB = 3_000_000  # numba search
H_WEIGHT = 2.2  # weighted A*: trades optimality for speed

POWER_HI = {
    "+24V", "VIN_RAW", "VIN_FUSE", "SOL_LO",
    "RLY1_COM", "RLY1_NO", "RLY1_NC", "RLY2_COM", "RLY2_NO", "RLY2_NC",
}
POWER_MID = {"+5V", "+3V3", "BUCK_SW"}
# USB-C 16P (bước 0,5 mm): netclass "USB" trong kicad_pro
USB_RULE = {"width": 0.15, "clearance": 0.13, "via": (0.45, 0.2)}


def width_ladder(net: str) -> tuple[float, ...]:
    if net.startswith("USB_"):  # USB-C 0.5 mm pitch pads
        return (USB_RULE["width"],)
    if net in POWER_HI:
        return (0.8, 0.6, 0.4, 0.25)
    if net in POWER_MID or net in GND_NETS:
        return (0.5, 0.4, 0.25)
    return (0.25,)


def via_for(w: float) -> tuple[float, float]:
    return VIA_POWER if w >= 0.5 else VIA_SIGNAL


def clr_for(net: str) -> float:
    if net.startswith("USB_"):
        return USB_RULE["clearance"]
    return CLR_POWER if net in POWER_HI else CLR


# ----------------------------------------------------------------------------- board model
def _crt_overlap(a, c, tol: float = 0.02) -> bool:
    if not a or not c:
        return False
    return min(a[2], c[2]) - max(a[0], c[0]) > tol and min(a[3], c[3]) - max(a[1], c[1]) > tol


@dataclass
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float
    net: int
    kind: str  # pad / smdpad / track / via


@dataclass
class Stub:
    pad: Pad
    layers: tuple[int, ...]  # layers on which the pad can start a route
    ex: float  # exact stub end
    ey: float
    dx: int
    dy: int
    nx: int  # grid node continuing the stub
    ny: int
    direction: int
    length: float
    big: bool = False


class Board:
    def __init__(self, path: str):
        self.text, self.fps, edge = load_board(path)
        self.x0, self.y0, self.x1, self.y1 = edge
        self.W = int(round((self.x1 - self.x0) / G)) + 1
        self.H = int(round((self.y1 - self.y0) / G)) + 1
        self.HW = self.H * self.W
        self.net_id: dict[str, int] = {}
        self.net_name: dict[int, str] = {}
        self.rects: list[list[Rect]] = [[], []]
        self._cache: list[tuple | None] = [None, None]
        self.pads_by_net: dict[str, list[Pad]] = {}
        self.pad_centroid: dict[int, tuple[float, float]] = {}
        self.pour: dict[str, list[list[tuple[float, float]]]] = {}
        self.moved: dict[str, tuple[float, float]] = {}
        self.orig_pos = {f.ref: (f.x, f.y) for f in self.fps}
        # courtyard overlaps already present in the placement (e.g. parts in the ESP32 pocket) stay allowed
        self.orig_overlap = {(a.ref, c.ref) for a in self.fps for c in self.fps
                             if a is not c and _crt_overlap(a.crtyd, c.crtyd)}
        self._load_pads()
        self._load_pours()
        self.static_counts = [len(self.rects[0]), len(self.rects[1])]

    # -- component nudging
    MOVABLE = ("R", "C", "D", "FB", "L", "LED", "Q")
    NUDGE_MAX = 3.0

    def movable(self, fp) -> bool:
        pre = re.match(r"[A-Za-z]+", fp.ref)
        return bool(pre) and pre.group(0) in self.MOVABLE and len(fp.pads) <= 3 and all(p.smd for p in fp.pads)

    def rebuild_static(self) -> None:
        tracks = [self.rects[L][self.static_counts[L]:] for L in (0, 1)]
        self.rects = [[], []]
        self._cache = [None, None]
        self.pads_by_net = {}
        self._load_pads()
        self.static_counts = [len(self.rects[0]), len(self.rects[1])]
        for L in (0, 1):
            self.rects[L].extend(tracks[L])

    def move_fp(self, fp, dx: float, dy: float) -> None:
        fp.x += dx
        fp.y += dy
        if fp.crtyd:
            x0, y0, x1, y1 = fp.crtyd
            fp.crtyd = (x0 + dx, y0 + dy, x1 + dx, y1 + dy)
        for p in fp.pads:
            p.x += dx
            p.y += dy
        self.moved[fp.ref] = (fp.x - self.orig_pos[fp.ref][0], fp.y - self.orig_pos[fp.ref][1])
        self.rebuild_static()

    def fp_gap_ok(self, fp, gap: float = 0.35) -> bool:
        """Moved footprint keeps `gap` between its pads and every other footprint's pads, and the board edge."""
        for o in self.fps:
            if o is not fp and (fp.ref, o.ref) not in self.orig_overlap and _crt_overlap(fp.crtyd, o.crtyd):
                return False
        for p in fp.pads:
            if (p.x - p.w / 2 < self.x0 + 1.0 or p.x + p.w / 2 > self.x1 - 1.0
                    or p.y - p.h / 2 < self.y0 + 1.0 or p.y + p.h / 2 > self.y1 - 1.0):
                return False
            for o in self.fps:
                if o is fp:
                    continue
                for q in o.pads:
                    if abs(q.x - p.x) > 6 or abs(q.y - p.y) > 6:
                        continue
                    ddx = max(q.x - q.w / 2 - (p.x + p.w / 2), p.x - p.w / 2 - (q.x + q.w / 2), 0.0)
                    ddy = max(q.y - q.h / 2 - (p.y + p.h / 2), p.y - p.h / 2 - (q.y + q.h / 2), 0.0)
                    if math.hypot(ddx, ddy) < gap:
                        return False
        return True

    def apply_moves(self, text: str) -> str:
        for ref, (dx, dy) in self.moved.items():
            if abs(dx) < 1e-9 and abs(dy) < 1e-9:
                continue
            k = text.find(f'(property "Reference" "{ref}"')
            f0 = text.rfind("	(footprint ", 0, k)
            m = re.compile(r"\(at ([-\d.]+) ([-\d.]+)( [-\d.]+)?\)").search(text, f0)
            nx, ny = float(m.group(1)) + dx, float(m.group(2)) + dy
            text = text[:m.start()] + f"(at {nx:.4f} {ny:.4f}{m.group(3) or ''})" + text[m.end():]
        return text

    # -- nets
    def nid(self, name: str) -> int:
        if name not in self.net_id:
            i = len(self.net_id) + 1
            self.net_id[name] = i
            self.net_name[i] = name
        return self.net_id[name]

    def _load_pads(self) -> None:
        anon = -1
        for fp in self.fps:
            cx = sum(p.x for p in fp.pads) / max(1, len(fp.pads))
            cy = sum(p.y for p in fp.pads) / max(1, len(fp.pads))
            fp.pads = [p for p in fp.pads if any(l in ("F.Cu", "B.Cu", "*.Cu") for l in p.layers)]  # drop paste-only apertures
            for ko in fp.keepouts:  # e.g. ESP32 antenna: no copper of any net
                for L in (0, 1):
                    self.add_rect(L, *ko, KEEPOUT_NET, "keepout")
            for p in fp.pads:
                self.pad_centroid[id(p)] = (cx, cy)
                if p.net:
                    n = self.nid(p.net)
                    self.pads_by_net.setdefault(p.net, []).append(p)
                else:
                    n = anon
                    anon -= 1
                lays = self.pad_layers(p)
                for L in lays:
                    self.add_rect(L, p.x - p.w / 2, p.y - p.h / 2, p.x + p.w / 2, p.y + p.h / 2, n,
                                  "smdpad" if p.smd else "pad")

    @staticmethod
    def pad_layers(p: Pad) -> tuple[int, ...]:
        if any(l in ("*.Cu",) for l in p.layers) or (not p.smd):
            return (0, 1)
        if "B.Cu" in p.layers and "F.Cu" not in p.layers:
            return (1,)
        return (0,)

    def _load_pours(self) -> None:
        for m in re.finditer(r'\(zone\s+\(net \d+\)\s+\(net_name "([^"]+)"\)\s+\(layer "([^"]+)"\)(.*?)\(polygon\s+\(pts(.*?)\)\s*\)',
                             self.text, re.S):
            name, layer, _, pts = m.groups()
            poly = [(float(a), float(b)) for a, b in re.findall(r"\(xy ([-\d.]+) ([-\d.]+)\)", pts)]
            self.pour.setdefault(name, []).append(poly)

    def in_pour(self, net: str, x: float, y: float, margin: float) -> bool:
        for poly in self.pour.get(net, []):
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            if min(xs) + margin <= x <= max(xs) - margin and min(ys) + margin <= y <= max(ys) - margin:
                return True  # pours here are axis-aligned rectangles
        return False

    # -- rect store
    def add_rect(self, layer, x0, y0, x1, y1, net, kind) -> None:
        self.rects[layer].append(Rect(x0, y0, x1, y1, net, kind))
        self._cache[layer] = None

    def arrays(self, layer: int):
        if self._cache[layer] is None:
            r = self.rects[layer]
            a = np.array([[q.x0, q.y0, q.x1, q.y1, q.net] for q in r], dtype=float).reshape(-1, 5)
            self._cache[layer] = a
        return self._cache[layer]

    def exact_clear(self, layer, rx0, ry0, rx1, ry1, net, clr) -> bool:
        a = self.arrays(layer)
        if not len(a):
            return True
        m = a[:, 4] != net
        dx = np.maximum(np.maximum(a[:, 0] - rx1, rx0 - a[:, 2]), 0.0)
        dy = np.maximum(np.maximum(a[:, 1] - ry1, ry0 - a[:, 3]), 0.0)
        d = np.hypot(dx, dy)
        if np.any(d[m] < clr - 1e-9):
            return False
        # board edge
        return (rx0 >= self.x0 + EDGE_CLR - 1e-9 and ry0 >= self.y0 + EDGE_CLR - 1e-9
                and rx1 <= self.x1 - EDGE_CLR + 1e-9 and ry1 <= self.y1 - EDGE_CLR + 1e-9)

    # -- grid masks
    def build_masks(self, net: int, netname: str, w: float, vd: float):
        """Return (track_blocked[2], via_blocked) as uint8 H*W arrays."""
        c = clr_for(netname) + SAFE
        H, W = self.H, self.W
        mt = [np.zeros((H, W), np.uint8), np.zeros((H, W), np.uint8)]
        mv = [np.zeros((H, W), np.uint8), np.zeros((H, W), np.uint8)]
        for L in (0, 1):
            for r in self.rects[L]:
                own = r.net == net
                if own and r.kind != "smdpad":
                    continue
                if own:  # never drop vias onto own SMD pads (hand soldering)
                    dv = vd / 2 + 0.12
                    self._paint(mv[L], r, dv)
                    continue
                cc = max(c, clr_for(self.net_name.get(r.net, "")) + SAFE)
                self._paint(mt[L], r, w / 2 + cc)
                self._paint(mv[L], r, vd / 2 + cc)
            for m, half in ((mt[L], w / 2), (mv[L], vd / 2)):
                e = EDGE_CLR + half
                n = int(math.ceil(e / G)) + 1
                m[:n, :] = 1
                m[-n:, :] = 1
                m[:, :n] = 1
                m[:, -n:] = 1
        via_bad = (mv[0] | mv[1]).astype(np.uint8)
        return [m.ravel().tobytes() for m in mt], via_bad.ravel().tobytes()

    def _paint(self, m: np.ndarray, r: Rect, d: float) -> None:
        i0 = int(math.floor((r.x0 - self.x0 - d) / G + 1e-9)) + 1
        i1 = int(math.ceil((r.x1 - self.x0 + d) / G - 1e-9)) - 1
        j0 = int(math.floor((r.y0 - self.y0 - d) / G + 1e-9)) + 1
        j1 = int(math.ceil((r.y1 - self.y0 + d) / G - 1e-9)) - 1
        if i1 < 0 or j1 < 0 or i0 >= self.W or j0 >= self.H:
            return
        m[max(j0, 0): j1 + 1, max(i0, 0): i1 + 1] = 1

    # -- coordinates
    def cell_xy(self, i: int) -> tuple[float, float]:
        return self.x0 + (i % self.W) * G, self.y0 + (i // self.W) * G

    def xy_cell(self, x: float, y: float) -> int:
        return int(round((y - self.y0) / G)) * self.W + int(round((x - self.x0) / G))


# ----------------------------------------------------------------------------- stubs
DIRS = [(1, 0), (0, 1), (-1, 0), (0, -1)]  # E S W N  (y grows downward)


def _dir_index(dx: int, dy: int) -> int:
    return DIRS.index((dx, dy))


def stub_candidates(b: Board, p: Pad, mt: list[bytes] | None) -> list[tuple[int, int]]:
    cx, cy = b.pad_centroid[id(p)]
    vx, vy = p.x - cx, p.y - cy
    sx = (1 if vx >= 0 else -1)
    sy = (1 if vy >= 0 else -1)
    long_h, long_v = p.w > p.h * 2.0, p.h > p.w * 2.0
    if long_h:
        order = [(sx, 0), (0, sy), (0, -sy), (-sx, 0)]
    elif long_v:
        order = [(0, sy), (sx, 0), (-sx, 0), (0, -sy)]
    elif abs(vx) >= abs(vy):
        order = [(sx, 0), (0, sy), (0, -sy), (-sx, 0)]
    else:
        order = [(0, sy), (sx, 0), (-sx, 0), (0, -sy)]
    if not p.smd and not (long_h or long_v):
        # through-hole: prefer the direction with the longest free run (outward on ties)
        def run(d):
            n = 0
            x, y = p.x, p.y
            half = (p.w if d[0] else p.h) / 2
            for k in range(1, 40):
                xx, yy = x + d[0] * (half + k * G), y + d[1] * (half + k * G)
                if not b.exact_clear(0, xx - 0.125, yy - 0.125, xx + 0.125, yy + 0.125, b.nid(p.net) if p.net else -999, CLR + SAFE):
                    break
                n = k
            return min(n * G, 1.0)
        order.sort(key=lambda d: -run(d))
    return order


def pick_stub(b: Board, p: Pad, lens=STUB_LENS, w: float = 0.25, mt=None) -> Stub | None:
    net = b.nid(p.net)
    c = clr_for(p.net) + SAFE
    lays = b.pad_layers(p)
    for d in stub_candidates(b, p, None):
        half = (p.w if d[0] else p.h) / 2
        for ln in lens:
            ex = p.x + d[0] * (half + ln)
            ey = p.y + d[1] * (half + ln)
            # snap along-axis coordinate to the grid so the route continues on-grid
            # (round away from the pad so the straight run is never shorter than asked)
            if d[0]:
                k = (ex - b.x0) / G
                ex = b.x0 + (math.floor(k + 1e-9) if d[0] < 0 else math.ceil(k - 1e-9)) * G
            else:
                k = (ey - b.y0) / G
                ey = b.y0 + (math.floor(k + 1e-9) if d[1] < 0 else math.ceil(k - 1e-9)) * G
            if (ex - p.x) * d[0] + (ey - p.y) * d[1] < half + min(lens) - 1e-6:
                continue
            nx = int(round((ex - b.x0) / G))
            ny = int(round((ey - b.y0) / G))
            gx, gy = b.x0 + nx * G, b.y0 + ny * G
            ok_layers = []
            for L in lays:
                # stub rect (pad centre -> end) + jog to grid node
                x0, x1 = sorted((p.x, ex))
                y0, y1 = sorted((p.y, ey))
                hw = w / 2
                if mt is not None and mt[L][ny * b.W + nx]:
                    continue
                if b.exact_clear(L, x0 - hw, y0 - hw, x1 + hw, y1 + hw, net, c) and \
                   b.exact_clear(L, min(ex, gx) - hw, min(ey, gy) - hw, max(ex, gx) + hw, max(ey, gy) + hw, net, c):
                    ok_layers.append(L)
            if ok_layers:
                return Stub(p, tuple(ok_layers), ex, ey, d[0], d[1], nx, ny, _dir_index(*d), ln)
    return None


# ----------------------------------------------------------------------------- search
def astar(b: Board, sources, targets: set[int], samples, mt, via_bad):
    """sources: list of (layer, cell, dir). targets: set of layer*HW+cell. Returns list of (layer, cell) or None."""
    W, HW = b.W, b.HW
    OFF = (1, W, -1, -W)
    heap: list = []
    g: dict[int, int] = {}
    parent: dict[int, int] = {}
    sx = [(s % W, s // W) for s in samples]

    def h(i: int) -> int:
        x, y = i % W, i // W
        return int(H_WEIGHT * C_STEP * min(abs(x - a) + abs(y - c) for a, c in sx))

    for L, cell, d in sources:
        s = (L * HW + cell) * 4 + d
        g[s] = 0
        heapq.heappush(heap, (h(cell), 0, s))
    expanded = 0
    while heap:
        f, gc, s = heapq.heappop(heap)
        if gc > g.get(s, 1 << 60):
            continue
        key = s >> 2
        d = s & 3
        L, i = divmod(key, HW)
        if key in targets:
            path = []
            cur = s
            while True:
                path.append(cur >> 2)
                if cur not in parent:
                    break
                cur = parent[cur]
            path.reverse()
            return [(k // HW, k % HW) for k in path]
        expanded += 1
        if expanded > MAX_EXPAND:
            return None
        mL = mt[L]
        pref_h = (L == 0)
        for nd in range(4):
            if nd == (d + 2) & 3:
                continue
            ni = i + OFF[nd]
            if mL[ni]:
                continue
            horiz = nd in (0, 2)
            cost = C_STEP + (0 if horiz == pref_h else C_WRONG) + (C_BEND if nd != d else 0)
            ng = gc + cost
            ns = (L * HW + ni) * 4 + nd
            if ng < g.get(ns, 1 << 60):
                g[ns] = ng
                parent[ns] = s
                heapq.heappush(heap, (ng + h(ni), ng, ns))
        if not via_bad[i]:
            L2 = 1 - L
            if not mt[L2][i]:
                ns = (L2 * HW + i) * 4 + d
                ng = gc + C_VIA
                if ng < g.get(ns, 1 << 60):
                    g[ns] = ng
                    parent[ns] = s
                    heapq.heappush(heap, (ng + h(i), ng, ns))
    return None


# ----------------------------------------------------------------------------- router
@dataclass
class Result:
    segs: list[tuple[float, float, float, float, int, float, str]] = field(default_factory=list)
    vias: list[tuple[float, float, float, float, str]] = field(default_factory=list)


class Router:
    def __init__(self, b: Board):
        self.b = b
        self.segs: list[tuple[float, float, float, float, int, float, str]] = []
        self.vias: list[tuple[float, float, float, float, str]] = []
        self.failed: list[str] = []
        self.fail_detail: list[str] = []
        self.fail_pads: list[Pad] = []
        self.no_stub: list[str] = []

    def reset(self) -> None:
        b = self.b
        for L in (0, 1):
            del b.rects[L][b.static_counts[L]:]
            b._cache[L] = None
        self.segs.clear()
        self.vias.clear()

    _maze = None

    def restore(self, segs, vias) -> None:
        self.reset()
        self.reserve_stubs()
        for q in segs:
            self.commit_seg(*q)
        for v in vias:
            self.commit_via(*v)

    def search(self, srcs, tree, samples, mt, via_bad):
        if Maze is None:
            return astar(self.b, srcs, tree, samples, mt, via_bad)
        if Router._maze is None:
            Router._maze = Maze(self.b.W, self.b.HW)
        return Router._maze.search(srcs, tree, samples, mt, via_bad,
                                   (C_STEP, C_WRONG, C_BEND, C_VIA), H_WEIGHT, MAX_EXPAND_NB)

    def reserve_stubs(self) -> int:
        """Escape-first: block the straight exit of every IC/relay SMD pin so no other net walls it in."""
        b = self.b
        n = 0
        for fp in b.fps:
            if len(fp.pads) < 4:
                continue
            for p in fp.pads:
                if not p.smd or not p.net or (GND_STITCH and p.net in GND_NETS) or min(p.w, p.h) > 3.0:
                    continue
                if len(b.pads_by_net.get(p.net, [])) < 2:
                    continue
                st = pick_stub(b, p, w=min(width_ladder(p.net)))
                if st is None:
                    continue
                gx, gy = b.x0 + st.nx * G, b.y0 + st.ny * G
                hw = 0.125
                L = st.layers[0]
                nid = b.nid(p.net)
                for xa, ya, xb, yb in ((p.x, p.y, st.ex, st.ey), (st.ex, st.ey, gx, gy)):
                    b.add_rect(L, min(xa, xb) - hw, min(ya, yb) - hw, max(xa, xb) + hw, max(ya, yb) + hw, nid, "track")
                n += 1
        return n

    # -- commit geometry
    def commit_seg(self, x0, y0, x1, y1, layer, w, netname):
        if abs(x0 - x1) < 1e-9 and abs(y0 - y1) < 1e-9:
            return
        n = self.b.nid(netname)
        hw = w / 2
        self.b.add_rect(layer, min(x0, x1) - hw, min(y0, y1) - hw, max(x0, x1) + hw, max(y0, y1) + hw, n, "track")
        self.segs.append((x0, y0, x1, y1, layer, w, netname))

    def commit_via(self, x, y, vd, drill, netname):
        n = self.b.nid(netname)
        for L in (0, 1):
            self.b.add_rect(L, x - vd / 2, y - vd / 2, x + vd / 2, y + vd / 2, n, "track")
        self.vias.append((x, y, vd, drill, netname))

    def commit_poly(self, pts: list[tuple[float, float]], layer: int, w: float, netname: str):
        pts = simplify(pts)
        for a, c in zip(pts, pts[1:]):
            self.commit_seg(a[0], a[1], c[0], c[1], layer, w, netname)

    # -- one net
    def route_net(self, netname: str) -> bool:
        b = self.b
        pads = b.pads_by_net[netname]
        if len(pads) < 2:
            return True
        net = b.nid(netname)
        ladder = width_ladder(netname)
        stubs: dict[int, Stub] = {}
        for p in pads:
            if min(p.w, p.h) > 3.0:  # large pad (e.g. regulator tab): route may start anywhere inside it
                stubs[id(p)] = Stub(p, b.pad_layers(p), p.x, p.y, 0, 0,
                                    int(round((p.x - b.x0) / G)), int(round((p.y - b.y0) / G)), 0, 0.0, big=True)
                continue
            st = None
            for w in ladder:
                st = pick_stub(b, p, w=w)
                if st:
                    break
            if st is None:
                st = pick_stub(b, p, lens=(0.2, 0.1), w=min(ladder))
            if st is None:  # last resort: leave straight from the pad centre (no stub)
                nx = int(round((p.x - b.x0) / G))
                ny = int(round((p.y - b.y0) / G))
                d = stub_candidates(b, p, None)[0]
                st = Stub(p, b.pad_layers(p), p.x, p.y, d[0], d[1], nx, ny, _dir_index(*d), 0.0)
                self.no_stub.append(f"{p.ref}.{p.num}")
            if st is None:
                self.fail_detail.append(f"{netname}: no stub for {p.ref}.{p.num}")
                self.fail_pads.append(p)
                return False
            stubs[id(p)] = st

        # Prim: seed = pad nearest to the centroid of the net
        mx = sum(p.x for p in pads) / len(pads)
        my = sum(p.y for p in pads) / len(pads)
        order = sorted(pads, key=lambda p: (p.x - mx) ** 2 + (p.y - my) ** 2)
        seed = order[0]
        connected = [seed]
        remaining = order[1:]
        uncommitted: dict[int, Stub] = {}  # layer*HW+cell -> stub that must be drawn when joined
        tree: set[int] = set()
        self._add_stub_cells(stubs[id(seed)], uncommitted, tree)
        ok_all = True
        while remaining:
            remaining.sort(key=lambda p: min(abs(p.x - q.x) + abs(p.y - q.y) for q in connected))
            tgt = remaining.pop(0)
            st = stubs[id(tgt)]
            done = False
            for w in dict.fromkeys((ladder[0], ladder[1] if len(ladder) > 2 else ladder[-1], ladder[-1])):
                vd, vdr = USB_RULE["via"] if netname.startswith("USB_") else via_for(w)
                mt, via_bad = b.build_masks(net, netname, w, vd)
                if not st.big:
                    st = pick_stub(b, tgt, w=w, mt=mt) or pick_stub(b, tgt, lens=(0.2,), w=w, mt=mt) or st
                srcs = []
                for L in st.layers:
                    if st.big:
                        srcs.extend((L, c, 0) for c in self._pad_cells(st) if not mt[L][c])
                        continue
                    cell = st.ny * b.W + st.nx
                    if not mt[L][cell]:
                        srcs.append((L, cell, st.direction))
                if not srcs:
                    continue
                samples = self._samples(tree, b)
                t2 = time.time()
                path = self.search(srcs, tree, samples, mt, via_bad)
                if path is None:
                    print(f"    {netname} -> {tgt.ref}.{tgt.num} w={w}: no path ({time.time() - t2:.1f}s)", flush=True)
                    continue
                used = self._commit_path(path, st, w, vd, vdr, netname, uncommitted, tree)
                done = True
                break
            if not done:
                ok_all = False
                self.fail_detail.append(f"{netname}: cannot reach {tgt.ref}.{tgt.num}")
                self.fail_pads.append(tgt)
                continue
            connected.append(tgt)
            self._add_stub_cells(st, uncommitted, tree, committed=True, only=used)
        return ok_all

    def _pad_cells(self, st: Stub) -> list[int]:
        b, p = self.b, st.pad
        i0 = int(math.ceil((p.x - p.w / 2 + 0.2 - b.x0) / G))
        i1 = int(math.floor((p.x + p.w / 2 - 0.2 - b.x0) / G))
        j0 = int(math.ceil((p.y - p.h / 2 + 0.2 - b.y0) / G))
        j1 = int(math.floor((p.y + p.h / 2 - 0.2 - b.y0) / G))
        return [j * b.W + i for j in range(j0, j1 + 1) for i in range(i0, i1 + 1)]

    def _add_stub_cells(self, st: Stub, uncommitted, tree, committed=False, only=None):
        if st.big:
            for L in st.layers:
                if only is None or L == only:
                    tree.update(L * self.b.HW + c for c in self._pad_cells(st))
            return
        cell = st.ny * self.b.W + st.nx
        for L in st.layers:
            if only is not None and L != only:
                continue
            k = L * self.b.HW + cell
            tree.add(k)
            if not committed:
                uncommitted[k] = st

    def _samples(self, tree: set[int], b: Board) -> list[int]:
        cells = [k % b.HW for k in tree]
        if len(cells) <= 4:
            return cells
        xs = [(c % b.W, c) for c in cells]
        ys = [(c // b.W, c) for c in cells]
        return list({min(xs)[1], max(xs)[1], min(ys)[1], max(ys)[1]})

    def _commit_path(self, path, st: Stub, w, vd, vdr, netname, uncommitted, tree):
        b = self.b
        # polyline segments per layer
        first_layer = path[0][0]
        pts = [] if st.big else [(st.pad.x, st.pad.y), (st.ex, st.ey)]
        cur_layer = first_layer
        for k, (L, cell) in enumerate(path):
            x, y = b.cell_xy(cell)
            if L != cur_layer:
                # via at previous point
                self.commit_poly(pts, cur_layer, w, netname)
                vx, vy = pts[-1]
                self.commit_via(vx, vy, vd, vdr, netname)
                pts = [(vx, vy)]
                cur_layer = L
            else:
                pts.append((x, y))
        self.commit_poly(pts, cur_layer, w, netname)
        # path cells become part of the tree (track cells), stub of the end cell gets drawn
        for a in range(len(path) - 1):
            L, c = path[a]
            L2, c2 = path[a + 1]
            tree.add(L * b.HW + c)
            if L == L2:
                self._fill_cells(L, c, c2, tree)
        L, c = path[-1]
        tree.add(L * b.HW + c)
        # vias add cells on both layers
        for a in range(len(path) - 1):
            if path[a][0] != path[a + 1][0]:
                tree.add(b.HW * 0 + path[a][1])
                tree.add(b.HW + path[a][1])
        endk = L * b.HW + c
        if endk in uncommitted:
            es = uncommitted.pop(endk)
            gx, gy = b.cell_xy(c)
            self.commit_poly([(es.pad.x, es.pad.y), (es.ex, es.ey), (gx, gy)], L, w, netname)
            # the other layer's entry for this stub stays uncommitted -> remove it
            for kk in [k for k, v in uncommitted.items() if v is es]:
                del uncommitted[kk]
        return first_layer

    def _fill_cells(self, L, c, c2, tree):
        pass  # consecutive path cells are adjacent already

    # -- grounds (pour stitching)
    def route_ground(self, gname: str) -> tuple[int, int]:
        b = self.b
        net = b.nid(gname)
        done = skipped = 0
        for p in b.pads_by_net.get(gname, []):
            if not p.smd:
                continue
            placed = False
            vd, vdr = VIA_SIGNAL
            for ln in STUB_LEN_GND:
                st = pick_stub(b, p, lens=(ln,), w=0.25)
                if st is None:
                    continue
                vx, vy = st.ex, st.ey
                if not b.in_pour(gname, vx, vy, 0.8 + vd / 2):
                    continue
                c = CLR + SAFE
                if all(b.exact_clear(L, vx - vd / 2, vy - vd / 2, vx + vd / 2, vy + vd / 2, net, c) for L in (0, 1)):
                    self.commit_poly([(p.x, p.y), (vx, vy)], 0, 0.25, gname)
                    self.commit_via(vx, vy, vd, vdr, gname)
                    placed = True
                    break
            if placed:
                done += 1
            else:
                skipped += 1
        return done, skipped


def simplify(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Drop duplicate points and collinear/backtracking middle points."""
    out: list[tuple[float, float]] = []
    for p in pts:
        if out and abs(out[-1][0] - p[0]) < 1e-9 and abs(out[-1][1] - p[1]) < 1e-9:
            continue
        out.append(p)
    changed = True
    while changed and len(out) > 2:
        changed = False
        for i in range(1, len(out) - 1):
            ax, ay = out[i - 1]
            bx, by = out[i]
            cx, cy = out[i + 1]
            cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
            if abs(cross) < 1e-9:
                del out[i]
                changed = True
                break
    return out


# ----------------------------------------------------------------------------- order, passes
def net_order(b: Board, failed_first: list[str]) -> list[str]:
    def hpwl(n):
        ps = b.pads_by_net[n]
        return (max(p.x for p in ps) - min(p.x for p in ps)) + (max(p.y for p in ps) - min(p.y for p in ps))

    names = [n for n, ps in b.pads_by_net.items()
             if (not GND_STITCH or n not in GND_NETS) and len(ps) >= 2]

    def key(n):
        tier = 3 if n in GND_NETS else (0 if n in POWER_HI else (1 if n in POWER_MID else 2))
        return (0 if n in failed_first else 1, failed_first.index(n) if n in failed_first else 0, tier, hpwl(n))

    return sorted(names, key=key)


def nudge(b: Board, r: Router, log=print) -> int:
    """Shift small SMD parts (<= NUDGE_MAX from origin) so that blocked pads regain an escape stub."""
    offs = sorted(((dx / 4, dy / 4) for dx in range(-12, 13) for dy in range(-12, 13) if dx or dy),
                  key=lambda o: o[0] ** 2 + o[1] ** 2)
    owner = {id(p): f for f in b.fps for p in f.pads}
    moved = 0
    seen = set()
    for pad in r.fail_pads:
        if id(pad) in seen:
            continue
        seen.add(id(pad))
        net = b.nid(pad.net)
        w = min(width_ladder(pad.net))
        vd, _ = via_for(w)

        def good() -> bool:
            st = pick_stub(b, pad, w=w)
            if st is None:
                return False
            c = clr_for(pad.net) + SAFE
            hw = w / 2
            # open space beyond the stub end: >= 1.5 mm free straight run ahead or to a side
            for dx, dy in ((st.dx, st.dy), (st.dy, st.dx), (-st.dy, -st.dx)):
                if not (dx or dy):
                    continue
                x0, x1 = sorted((st.ex, st.ex + dx * 1.5))
                y0, y1 = sorted((st.ey, st.ey + dy * 1.5))
                if all(b.exact_clear(L, x0 - hw, y0 - hw, x1 + hw, y1 + hw, net, c) for L in st.layers[:1]):
                    return True
            return False

        if good():
            continue
        cands = [owner[id(pad)]] + [
            f for f in b.fps
            if f is not owner[id(pad)] and any(math.hypot(q.x - pad.x, q.y - pad.y) < 4.0 for q in f.pads)
        ]
        done = False
        for fp in cands:
            if not b.movable(fp):
                continue
            ox, oy = b.moved.get(fp.ref, (0.0, 0.0))
            for dx, dy in offs:
                if math.hypot(ox + dx, oy + dy) > b.NUDGE_MAX:
                    continue
                b.move_fp(fp, dx, dy)
                if b.fp_gap_ok(fp) and good():
                    log(f"  nudge {fp.ref} by ({dx:+.2f},{dy:+.2f}) to free {pad.ref}.{pad.num}")
                    moved += 1
                    done = True
                    break
                b.move_fp(fp, -dx, -dy)
            if done:
                break
    return moved


def run(b: Board, passes: int, log=print) -> Router:
    failed: list[str] = []
    prio: list[str] = []
    best: Router | None = None
    for ps in range(1, passes + 1):
        r = Router(b)
        r.reset()
        r.reserve_stubs()
        t0 = time.time()
        order = net_order(b, prio)
        failed = []
        for n in order:
            t1 = time.time()
            ok = r.route_net(n)
            if not ok:
                failed.append(n)
            log(f"  {n:14s} {'ok ' if ok else 'FAIL'} {time.time() - t1:5.1f}s")
        gdone = gskip = 0
        for gname in GND_NETS if GND_STITCH else ():
            d, s = r.route_ground(gname)
            gdone += d
            gskip += s
        r.failed = failed
        prio = failed + [n for n in prio if n not in failed]
        log(f"pass {ps}: routed {len(order) - len(failed)}/{len(order)} nets, "
            f"{len(r.segs)} segs, {len(r.vias)} vias, gnd stitch {gdone} (skipped {gskip}), {time.time() - t0:.1f}s")
        if best is None or len(failed) < len(best.failed):
            best = r
            best_state = (list(r.segs), list(r.vias))
        if not failed:
            break
        if ps < passes and nudge(b, r, log):
            best = None  # geometry changed: earlier results are stale
    # restore best result into the board model
    assert best is not None
    if best is not r:
        best.restore(best_state[0], best_state[1])
    if best.failed:
        ripup_fix(b, best, log)
    return best


def ripup_fix(b: Board, r: Router, log=print, rounds: int = 3) -> None:
    """Targeted rip-up and re-route: free the area around a stuck pad, route the stuck net first,
    then put the ripped nets back. A trial is kept only if every touched net connects again."""
    for _ in range(rounds):
        if not r.failed:
            return
        progress = False
        for fnet in list(r.failed):
            pads = [p for p in r.fail_pads if p.net == fnet] or b.pads_by_net[fnet]
            xs = [p.x for p in pads] + [q.x for q in b.pads_by_net[fnet]]
            ys = [p.y for p in pads] + [q.y for q in b.pads_by_net[fnet]]
            # area: around the stuck pads, growing if needed
            for grow in (2.0, 4.0, 7.0):
                px0 = min(p.x for p in pads) - grow
                px1 = max(p.x for p in pads) + grow
                py0 = min(p.y for p in pads) - grow
                py1 = max(p.y for p in pads) + grow
                hits: dict[str, int] = {}
                for x0, y0, x1, y1, L, w, net in r.segs:
                    if net != fnet and max(x0, x1) >= px0 and min(x0, x1) <= px1 and max(y0, y1) >= py0 and min(y0, y1) <= py1:
                        hits[net] = hits.get(net, 0) + 1
                victims = sorted(hits, key=lambda n: -hits[n])
                trials = [[v] for v in victims[:6]] + ([victims[:3]] if len(victims) > 1 else []) + ([victims] if len(victims) > 3 else [])
                for vs in trials:
                    segs0, vias0 = list(r.segs), list(r.vias)
                    gone = set(vs) | {fnet}
                    r.restore([q for q in segs0 if q[6] not in gone], [v for v in vias0 if v[4] not in gone])
                    r.fail_pads.clear()
                    ok = r.route_net(fnet) and all(r.route_net(v) for v in vs)
                    if ok:
                        log(f"  rip-up: {fnet} routed after re-routing {', '.join(vs)}")
                        r.failed.remove(fnet)
                        progress = True
                        break
                    r.restore(segs0, vias0)
                if fnet not in r.failed:
                    break
        if not progress:
            return


# ----------------------------------------------------------------------------- verification
def verify(b: Board, r: Router, log=print) -> int:
    """Independent clearance + connectivity audit on the final copper."""
    bad = 0
    for L in (0, 1):
        a = b.arrays(L)
        n = len(a)
        for i in range(n):
            m = (a[:, 4] != a[i, 4]) & (np.arange(n) > i)
            dx = np.maximum(np.maximum(a[:, 0] - a[i, 2], a[i, 0] - a[:, 2]), 0.0)
            dy = np.maximum(np.maximum(a[:, 1] - a[i, 3], a[i, 1] - a[:, 3]), 0.0)
            d = np.hypot(dx, dy)
            hit = np.where(m & (d < CLR_POWER - 1e-6))[0]
            for j in hit:
                ri, rj = b.rects[L][i], b.rects[L][j]
                static = ("pad", "smdpad", "keepout")
                if ri.kind in static and rj.kind in static:
                    continue  # footprint-internal spacing, not ours
                need = max(clr_for(b.net_name.get(ri.net, "")), clr_for(b.net_name.get(rj.net, "")))
                if ri.kind == "keepout" or rj.kind == "keepout":
                    need = 0.0  # keepout: chỉ cấm chồng lấn
                if d[j] >= need - 1e-6:
                    continue
                bad += 1
                if bad <= 15:
                    log(f"  clearance {'FB'[L]}: {b.net_name.get(ri.net, '?')}({ri.kind}) vs "
                        f"{b.net_name.get(rj.net, '?')}({rj.kind}) = {d[j]:.3f} @ {ri.x0:.1f},{ri.y0:.1f}")
    log(f"audit: {bad} clearance violations")
    # connectivity per routed net
    open_nets = 0
    for netname, pads in b.pads_by_net.items():
        if (GND_STITCH and netname in GND_NETS) or len(pads) < 2:
            continue
        n = b.nid(netname)
        items = []  # (layer, rect)
        for L in (0, 1):
            for q in b.rects[L]:
                if q.net == n:
                    items.append((L, q))
        parent = list(range(len(items)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                (la, qa), (lb, qb) = items[i], items[j]
                if la != lb:
                    continue
                if qa.x0 <= qb.x1 + 1e-6 and qb.x0 <= qa.x1 + 1e-6 and qa.y0 <= qb.y1 + 1e-6 and qb.y0 <= qa.y1 + 1e-6:
                    parent[find(i)] = find(j)
        # vias / TH pads exist on both layers: same geometry rect on L0 and L1 -> union
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                (la, qa), (lb, qb) = items[i], items[j]
                if la != lb and (qa.x0, qa.y0, qa.x1, qa.y1) == (qb.x0, qb.y0, qb.x1, qb.y1):
                    parent[find(i)] = find(j)
        roots = set()
        for p in pads:
            for i, (L, q) in enumerate(items):
                if q.kind in ("pad", "smdpad") and abs((q.x0 + q.x1) / 2 - p.x) < 1e-6 and abs((q.y0 + q.y1) / 2 - p.y) < 1e-6:
                    roots.add(find(i))
                    break
        if len(roots) > 1:
            open_nets += 1
            log(f"  OPEN {netname}: {len(roots)} islands")
    log(f"audit: {open_nets} nets not fully connected")
    return bad + open_nets


# ----------------------------------------------------------------------------- output
_OLD = re.compile(r"^\t\((?:segment|via)\n(?:\t\t.*\n)*?\t\)\n", re.M)


def emit(b: Board, r: Router) -> str:
    text = b.apply_moves(_OLD.sub("", b.text))
    parts = []
    for x0, y0, x1, y1, L, w, net in r.segs:
        parts.append(
            f'\t(segment\n\t\t(start {x0:.4f} {y0:.4f})\n\t\t(end {x1:.4f} {y1:.4f})\n'
            f'\t\t(width {w})\n\t\t(layer "{"FB"[L]}.Cu")\n\t\t(net "{net}")\n'
            f'\t\t(uuid "{uuid.uuid4()}")\n\t)\n'
        )
    for x, y, vd, dr, net in r.vias:
        parts.append(
            f'\t(via\n\t\t(at {x:.4f} {y:.4f})\n\t\t(size {vd})\n\t\t(drill {dr})\n'
            f'\t\t(layers "F.Cu" "B.Cu")\n\t\t(net "{net}")\n\t\t(uuid "{uuid.uuid4()}")\n\t)\n'
        )
    block = "".join(parts)
    k = text.find("\t(zone\n")
    if k < 0:
        k = text.rfind("\t(embedded_fonts")
    return text[:k] + block + text[k:]


def preview(b: Board, r: Router, png: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Circle

    fig, ax = plt.subplots(1, 2, figsize=(34, 12))
    col = {0: "#c8302a", 1: "#2a56c8"}
    for k, L in enumerate((0, 1)):
        a = ax[k]
        a.set_title(("F.Cu (top)", "B.Cu (bottom)")[k])
        a.add_patch(Rectangle((b.x0, b.y0), b.x1 - b.x0, b.y1 - b.y0, fill=False, ec="k"))
        for q in b.rects[L][: b.static_counts[L]]:
            a.add_patch(Rectangle((q.x0, q.y0), q.x1 - q.x0, q.y1 - q.y0, fc="#d9a441", ec="none", alpha=0.8))
        for x0, y0, x1, y1, ly, w, net in r.segs:
            if ly == L:
                a.plot([x0, x1], [y0, y1], color=col[L], lw=max(0.8, w * 4.2), solid_capstyle="round")
        for x, y, vd, dr, net in r.vias:
            a.add_patch(Circle((x, y), vd / 2, fc="#555", ec="w", lw=0.3))
        a.set_xlim(b.x0 - 1, b.x1 + 1)
        a.set_ylim(b.y1 + 1, b.y0 - 1)
        a.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(png, dpi=110)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pcb", default=str(Path(__file__).resolve().parents[1] / "fiberboard-logic.kicad_pcb"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--png", default=None)
    ap.add_argument("--passes", type=int, default=4)
    ap.add_argument("--dry", action="store_true", help="route and report but do not write")
    args = ap.parse_args()

    b = Board(args.pcb)
    print(f"board {b.x1 - b.x0:.0f}x{b.y1 - b.y0:.0f} mm, grid {b.W}x{b.H}, "
          f"{sum(len(p) for p in b.pads_by_net.values())} net pads, {len(b.pads_by_net)} nets")
    r = run(b, args.passes)
    for d in r.fail_detail[-20:]:
        print("  FAIL", d)
    print("unrouted nets:", r.failed or "none")
    print("pads without straight stub:", sorted(set(r.no_stub)) or "none")
    verify(b, r)
    if args.png:
        preview(b, r, args.png)
    if not args.dry:
        out = args.out or args.pcb
        Path(out).write_text(emit(b, r), encoding="utf-8")
        print("wrote", out)


if __name__ == "__main__":
    main()
