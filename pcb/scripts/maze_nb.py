"""Numba-compiled A* core for autoroute.py (same search as autoroute.astar, ~50x faster)."""

from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True)
def _astar(mt0, mt1, via_bad, W, HW, srcs, tgt, sx, sy, hweight,
           c_step, c_wrong, c_bend, c_via, max_expand,
           g, stamp, gen, parent, hf, hs):
    ns = len(sx)
    cap = len(hf)
    n = 0
    for k in range(len(srcs)):
        s = srcs[k]
        cell = (s >> 2) % HW
        x = cell % W
        y = cell // W
        best = 1 << 30
        for q in range(ns):
            d = abs(x - sx[q]) + abs(y - sy[q])
            if d < best:
                best = d
        f = np.int64(hweight * c_step * best)
        g[s] = 0
        stamp[s] = gen
        parent[s] = -1
        # push
        i = n
        n += 1
        while i > 0:
            p = (i - 1) >> 1
            if hf[p] <= f:
                break
            hf[i] = hf[p]
            hs[i] = hs[p]
            i = p
        hf[i] = f
        hs[i] = s
    offs = (1, W, -1, -W)
    expanded = 0
    while n > 0:
        # pop
        s = hs[0]
        n -= 1
        lf = hf[n]
        ls = hs[n]
        i = 0
        while True:
            c = 2 * i + 1
            if c >= n:
                break
            if c + 1 < n and hf[c + 1] < hf[c]:
                c += 1
            if hf[c] >= lf:
                break
            hf[i] = hf[c]
            hs[i] = hs[c]
            i = c
        if n > 0:
            hf[i] = lf
            hs[i] = ls
        key = s >> 2
        d = s & 3
        L = key // HW
        cell = key - L * HW
        gc = g[s]
        if tgt[key]:
            return s
        expanded += 1
        if expanded > max_expand:
            return -1
        pref_h = L == 0
        for nd in range(4):
            if nd == ((d + 2) & 3):
                continue
            ni = cell + offs[nd]
            if L == 0:
                if mt0[ni]:
                    continue
            else:
                if mt1[ni]:
                    continue
            horiz = nd == 0 or nd == 2
            cost = c_step
            if horiz != pref_h:
                cost += c_wrong
            if nd != d:
                cost += c_bend
            ng = gc + cost
            s2 = (L * HW + ni) * 4 + nd
            if stamp[s2] != gen or ng < g[s2]:
                g[s2] = ng
                stamp[s2] = gen
                parent[s2] = s
                x = ni % W
                y = ni // W
                best = 1 << 30
                for q in range(ns):
                    dd = abs(x - sx[q]) + abs(y - sy[q])
                    if dd < best:
                        best = dd
                f = ng + np.int64(hweight * c_step * best)
                if n >= cap:
                    return -2
                i = n
                n += 1
                while i > 0:
                    p = (i - 1) >> 1
                    if hf[p] <= f:
                        break
                    hf[i] = hf[p]
                    hs[i] = hs[p]
                    i = p
                hf[i] = f
                hs[i] = s2
        if not via_bad[cell]:
            L2 = 1 - L
            blocked = mt1[cell] if L2 == 1 else mt0[cell]
            if not blocked:
                s2 = (L2 * HW + cell) * 4 + d
                ng = gc + c_via
                if stamp[s2] != gen or ng < g[s2]:
                    g[s2] = ng
                    stamp[s2] = gen
                    parent[s2] = s
                    x = cell % W
                    y = cell // W
                    best = 1 << 30
                    for q in range(ns):
                        dd = abs(x - sx[q]) + abs(y - sy[q])
                        if dd < best:
                            best = dd
                    f = ng + np.int64(hweight * c_step * best)
                    if n >= cap:
                        return -2
                    i = n
                    n += 1
                    while i > 0:
                        p = (i - 1) >> 1
                        if hf[p] <= f:
                            break
                        hf[i] = hf[p]
                        hs[i] = hs[p]
                        i = p
                    hf[i] = f
                    hs[i] = s2
    return -1


class Maze:
    """Holds the big scratch arrays between searches."""

    def __init__(self, W: int, HW: int, heap_cap: int = 12_000_000):
        self.W, self.HW = W, HW
        n = 2 * HW * 4
        self.g = np.zeros(n, np.int32)
        self.stamp = np.zeros(n, np.int32)
        self.parent = np.full(n, -1, np.int32)
        self.hf = np.zeros(heap_cap, np.int64)
        self.hs = np.zeros(heap_cap, np.int32)
        self.tgt = np.zeros(2 * HW, np.uint8)
        self.gen = 0

    def search(self, sources, targets, samples, mt, via_bad, costs, hweight, max_expand):
        W, HW = self.W, self.HW
        self.gen += 1
        srcs = np.array([(L * HW + cell) * 4 + d for L, cell, d in sources], np.int32)
        tidx = np.fromiter(targets, np.int64, len(targets))
        self.tgt[tidx] = 1
        sm = np.array(samples, np.int64)
        try:
            end = _astar(
                np.frombuffer(mt[0], np.uint8), np.frombuffer(mt[1], np.uint8), np.frombuffer(via_bad, np.uint8),
                W, HW, srcs, self.tgt, (sm % W).astype(np.int64), (sm // W).astype(np.int64), float(hweight),
                costs[0], costs[1], costs[2], costs[3], max_expand,
                self.g, self.stamp, self.gen, self.parent, self.hf, self.hs,
            )
        finally:
            self.tgt[tidx] = 0
        if end < 0:
            return None
        path = []
        s = int(end)
        while s >= 0:
            path.append(s >> 2)
            s = int(self.parent[s])
        path.reverse()
        return [(k // HW, k % HW) for k in path]
