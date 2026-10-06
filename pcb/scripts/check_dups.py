from pathlib import Path
import re
from collections import Counter

t = Path(r"d:/Project/embedded/fiberboard/pcb/fiberboard-logic.kicad_sch").read_text(encoding="utf-8")
inst = re.findall(r'\(reference "([^"]+)"\)', t)
c = Counter(inst)
dups = [(r, n) for r, n in c.items() if n > 1 and not r.startswith("#")]
print("dup refs", sorted(dups))
print("U4", c.get("U4"), "U8", c.get("U8"))

net = Path(r"d:/Project/embedded/fiberboard/pcb/exports/logic.net").read_text(encoding="utf-8")
print("nets section sample:")
# find (nets
i = net.find("(nets")
print(net[i : i + 1500] if i >= 0 else "no nets section")
print("FIBER count", net.count("FIBER"))
print("F1_LED", net.count("F1_LED"))
