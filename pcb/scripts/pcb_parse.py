"""Minimal .kicad_pcb reader: footprints, pads (absolute geometry + net)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

_BS = chr(92)
_TOK = re.compile(
    "[(]|[)]|\"(?:" + _BS + _BS + ".|[^\"" + _BS + _BS + "])*\"|[^" + _BS + "s()\"]+"
)


def parse_sexpr(text: str):
    stack: list[list] = [[]]
    for m in _TOK.finditer(text):
        t = m.group(0)
        if t == "(":
            stack.append([])
        elif t == ")":
            lst = stack.pop()
            stack[-1].append(lst)
        elif t[0] == '"':
            stack[-1].append(("s", t[1:-1]))
        else:
            stack[-1].append(t)
    return stack[0][0]


def _s(v):
    return v[1] if isinstance(v, tuple) else v


def _find(node, name):
    for c in node:
        if isinstance(c, list) and c and c[0] == name:
            return c
    return None


def _findall(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


@dataclass
class Pad:
    ref: str
    num: str
    x: float
    y: float
    w: float  # axis-aligned extent after rotation
    h: float
    net: str
    smd: bool
    shape: str
    layers: tuple[str, ...]
    drill: float = 0.0


@dataclass
class Footprint:
    ref: str
    name: str
    x: float
    y: float
    rot: float
    pads: list[Pad] = field(default_factory=list)
    crtyd: tuple[float, float, float, float] | None = None  # absolute F/B.CrtYd bbox
    keepouts: list[tuple[float, float, float, float]] = field(default_factory=list)  # no-track areas (abs)


def load_board(path: str):
    text = open(path, encoding="utf-8").read()
    root = parse_sexpr(text)
    fps: list[Footprint] = []
    for fp in _findall(root, "footprint"):
        at = _find(fp, "at")
        fx, fy = float(at[1]), float(at[2])
        frot = float(at[3]) if len(at) > 3 else 0.0
        ref = ""
        for p in _findall(fp, "property"):
            if _s(p[1]) == "Reference":
                ref = _s(p[2])
        f = Footprint(ref, _s(fp[1]), fx, fy, frot)
        a = math.radians(frot)
        ca, sa = math.cos(a), math.sin(a)
        cpts = []
        for kind in ("fp_line", "fp_rect", "fp_poly", "fp_arc"):
            for g in _findall(fp, kind):
                lay = _find(g, "layer")
                if not lay or _s(lay[1]) not in ("F.CrtYd", "B.CrtYd"):
                    continue
                for tag in ("start", "end", "mid"):
                    e = _find(g, tag)
                    if e:
                        cpts.append((float(e[1]), float(e[2])))
                pp = _find(g, "pts")
                if pp:
                    cpts += [(float(x[1]), float(x[2])) for x in _findall(pp, "xy")]
        if cpts:
            ab = [(fx + x * ca + y * sa, fy - x * sa + y * ca) for x, y in cpts]
            f.crtyd = (min(q[0] for q in ab), min(q[1] for q in ab), max(q[0] for q in ab), max(q[1] for q in ab))
        for z in _findall(fp, "zone"):  # board footprints store zone outlines in board coordinates
            ko = _find(z, "keepout")
            if not ko or ["tracks", "not_allowed"] not in ko[1:]:
                continue
            poly = _find(_find(z, "polygon"), "pts")
            xy = [(float(q[1]), float(q[2])) for q in _findall(poly, "xy")]
            if xy:
                f.keepouts.append((min(q[0] for q in xy), min(q[1] for q in xy), max(q[0] for q in xy), max(q[1] for q in xy)))
        for pd in _findall(fp, "pad"):
            pat = _find(pd, "at")
            px, py = float(pat[1]), float(pat[2])
            pang = float(pat[3]) if len(pat) > 3 else 0.0
            ax = fx + px * ca + py * sa
            ay = fy - px * sa + py * ca
            sz = _find(pd, "size")
            w, h = float(sz[1]), float(sz[2])
            r = pang % 180
            if abs(r - 90) < 1e-6:
                w, h = h, w
            elif abs(r) > 1e-6:  # arbitrary angle: bounding box
                t = math.radians(pang)
                w, h = abs(w * math.cos(t)) + abs(h * math.sin(t)), abs(w * math.sin(t)) + abs(h * math.cos(t))
            net = _find(pd, "net")
            nname = _s(net[-1]) if net else ""
            lay = _find(pd, "layers")
            layers = tuple(_s(x) for x in lay[1:]) if lay else ()
            dr = _find(pd, "drill")
            drill = 0.0
            if dr:
                nums = [x for x in dr[1:] if not isinstance(x, (list, tuple)) and x != "oval"]
                drill = float(nums[0]) if nums else 0.0
            f.pads.append(
                Pad(ref, _s(pd[1]), ax, ay, w, h, nname, _s(pd[2]) == "smd", _s(pd[3]) if len(pd) > 3 else "", layers, drill)
            )
        fps.append(f)
    edge = None
    for r in _findall(root, "gr_rect"):
        lay = _find(r, "layer")
        if lay and _s(lay[1]) == "Edge.Cuts":
            s, e = _find(r, "start"), _find(r, "end")
            edge = (float(s[1]), float(s[2]), float(e[1]), float(e[2]))
    return text, fps, edge
