from pathlib import Path
import re

t = Path(r"d:/Project/embedded/fiberboard/pcb/fiberboard-logic.kicad_sch").read_text(encoding="utf-8")
# Find wire containing 30.48 33.02
idx = t.find("(xy 30.48 33.02)")
print("idx", idx)
print(t[idx - 200 : idx + 250])

# U1 pin5 wire
idx = t.find("(xy 54.61 119.38)")
print("\nU1 tip idx", idx)
print(t[idx - 200 : idx + 250])

# Compare with a demo wire from ecc83
demo = Path(r"C:/Users/duchan.nguyen/AppData/Local/Programs/KiCad/10.0/share/kicad/demos/ecc83/ecc83-pp.kicad_sch").read_text(encoding="utf-8")
i = demo.find("(wire")
print("\nDEMO wire:\n", demo[i : i + 300])
