"""Placement sanity check after generate_kicad_project.py (not full KiCad DRC)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from connectivity import build_logic_design  # noqa: E402
from assembly_groups import SHARED_LAYOUT_REFS, STACK_REFS  # noqa: E402
from pcb_layout import (  # noqa: E402
    BOARD_H,
    BOARD_W,
    LAYOUT_FIXED_REFS,
    ZONES,
    build_layout,
    footprint_geometry,
)

# Import KiCad footprint loader from generator
import importlib.util

_spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / "generate_kicad_project.py")
_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gen)
_load_mod = _gen._load_mod_body


def _bbox_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)


def _min_pad_distance(pads_a: dict, pads_b: dict) -> float:
    best = float("inf")
    for ax, ay in pads_a.values():
        for bx, by in pads_b.values():
            best = min(best, math.hypot(ax - bx, ay - by))
    return best


def main() -> int:
    design = build_logic_design()
    comps = {
        c.ref: c.footprint
        for c in design.comps
        if not c.ref.startswith("#") and c.footprint
    }
    geoms = {ref: footprint_geometry(_load_mod(fp)) for ref, fp in comps.items()}
    placements, _, _ = build_layout(comps, _load_mod)

    errors: list[str] = []
    warns: list[str] = []

    zoned = (
        {r for z in ZONES for r in z.refs}
        | STACK_REFS
        | LAYOUT_FIXED_REFS
        | SHARED_LAYOUT_REFS
    )
    missing = sorted(set(comps) - zoned)
    if missing:
        errors.append(f"refs not in any zone: {missing}")

    overlaps: list[tuple[str, str]] = []
    for i, p in enumerate(placements):
        x0, y0, x1, y1 = p.bbox
        if x0 < 0 or y0 < 0 or x1 > BOARD_W or y1 > BOARD_H:
            errors.append(f"{p.ref} outside Edge.Cuts {p.bbox}")
        for q in placements[i + 1 :]:
            if _bbox_overlap(p.bbox, q.bbox):
                overlaps.append((p.ref, q.ref))
    if overlaps:
        errors.append(f"footprint bbox overlap: {overlaps[:8]}{'...' if len(overlaps) > 8 else ''}")

    # Pad clearance heuristic (Default 0.2 mm)
    for i, p in enumerate(placements):
        for q in placements[i + 1 :]:
            d = _min_pad_distance(p.pads, q.pads)
            if d < 0.2:
                errors.append(f"pad clearance < 0.2 mm: {p.ref} vs {q.ref} ({d:.3f} mm)")

    pcb_path = ROOT / "fiberboard-logic.kicad_pcb"
    if pcb_path.exists():
        text = pcb_path.read_text(encoding="utf-8")
        if "(segment" not in text and "(via" not in text:
            warns.append(
                "PCB has no tracks/vias yet - KiCad DRC will show many unconnected "
                "(expected until you route)."
            )

    for w in warns:
        print("WARN:", w)
    for e in errors:
        print("ERROR:", e)

    if errors:
        print(f"\n{len(errors)} placement error(s).")
        return 1
    print("Placement OK.", f"({len(placements)} footprint)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
