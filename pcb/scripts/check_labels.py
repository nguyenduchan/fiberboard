from pathlib import Path
import re

t = Path(r"d:/Project/embedded/fiberboard/pcb/fiberboard-logic.kicad_sch").read_text(encoding="utf-8")

# all +12V labels
print("=== +12V labels ===")
for m in re.finditer(r'\(global_label "\+12V"[\s\S]*?\(at ([-\d.]+) ([-\d.]+)', t):
    print(m.group(1), m.group(2))

print("=== J1 related ===")
# Find symbol J1
idx = 0
while True:
    i = t.find('(property "Reference" "J1"', idx)
    if i < 0:
        break
    # search backwards for (symbol
    start = t.rfind("(symbol", 0, i)
    chunk = t[start : start + 800]
    at = re.search(r'\(at ([-\d.]+) ([-\d.]+)', chunk)
    lib = re.search(r'\(lib_id "([^"]+)"', chunk)
    print("J1", lib.group(1) if lib else "?", "at", at.group(1) if at else "?", at.group(2) if at else "?")
    idx = i + 1

# Count how many labels sit exactly on computed pin tips for first few nets
from connectivity import build_logic_design, find_comp, pin_abs

d = build_logic_design()
label_pos = []
for m in re.finditer(r'\(global_label "([^"]+)"[\s\S]*?\(at ([-\d.]+) ([-\d.]+)', t):
    label_pos.append((m.group(1), float(m.group(2)), float(m.group(3))))

hits = 0
miss = 0
for net, pins in d.nets.items():
    for ref, pin in pins:
        c = find_comp(d, ref, pin)
        if not c:
            continue
        x, y = pin_abs(c, pin)
        found = any(n == net and abs(lx - x) < 0.02 and abs(ly - y) < 0.02 for n, lx, ly in label_pos)
        if found:
            hits += 1
        else:
            miss += 1
            if miss <= 15:
                print(f"MISS {net} {ref}.{pin} expected ({x},{y})")
print("hits", hits, "miss", miss)
