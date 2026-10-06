from pathlib import Path
import re
from connectivity import build_logic_design, find_comp, pin_abs, snap

d = build_logic_design()
c = find_comp(d, "U1", "5")
print("U1 at", c.x, c.y)
print("pin5 tip", pin_abs(c, "5"))
x, y = pin_abs(c, "5")
dx, dy = x - c.x, y - c.y
dist = (dx * dx + dy * dy) ** 0.5
ux, uy = dx / dist, dy / dist
sx, sy = snap(x + ux * 2.54), snap(y + uy * 2.54)
print("stub end", sx, sy)

t = Path(r"d:/Project/embedded/fiberboard/pcb/fiberboard-logic.kicad_sch").read_text(encoding="utf-8")
# find wires from tip
tip = f"(xy {x} {y})"
# try snapped
for xv, yv in [(x, y), (snap(x), snap(y))]:
    print("search tip", xv, yv, "count", t.count(f"(xy {xv} {yv})"))

# FIBER1_ADC labels
for m in re.finditer(r'\(global_label "FIBER1_ADC"[\s\S]*?\(at ([-\d.]+) ([-\d.]+)', t):
    print("FIBER1_ADC label", m.group(1), m.group(2))

# J1
c = find_comp(d, "J1", "1")
print("J1", c.x, c.y, "pin1", pin_abs(c, "1"))
x, y = pin_abs(c, "1")
print("J1 tip count", t.count(f"(xy {snap(x)} {snap(y)})"), snap(x), snap(y))

# erc remaining for connected parts
erc = Path(r"d:/Project/embedded/fiberboard/pcb/erc.rpt").read_text(encoding="utf-8")
for name in ["J1 Pin 1", "U1 Pin 5", "U1 Pin 1", "U1 Pin 13", "U1 Pin 19", "K1 Pin", "U5 Pin"]:
    print(name, "->", erc.count(name))
