from pathlib import Path
import re

t = Path(r"d:/Project/embedded/fiberboard/pcb/erc.rpt").read_text(encoding="utf-8")
for key in ["J1 Pin", "R20 Pin", "U1 Pin 5", "U1 Pin 7", "D1 Pin", "label_dangling", "Q1 Pin", "U4 Pin"]:
    print("====", key, "====")
    lines = t.splitlines()
    for i, line in enumerate(lines):
        if key in line or (key == "label_dangling" and "label_dangling" in line):
            for j in range(i, min(i + 4, len(lines))):
                print(lines[j])
            print()
            if key != "label_dangling":
                break
    if key == "label_dangling":
        # only first 3
        count = 0
        for i, line in enumerate(lines):
            if "label_dangling" in line:
                for j in range(i, min(i + 4, len(lines))):
                    print(lines[j])
                print()
                count += 1
                if count >= 3:
                    break

sch = Path(r"d:/Project/embedded/fiberboard/pcb/fiberboard-logic.kicad_sch").read_text(encoding="utf-8")
print("wires", sch.count("\n\t(wire\n"))
print("segments pcb", Path(r"d:/Project/embedded/fiberboard/pcb/fiberboard-logic.kicad_pcb").read_text(encoding="utf-8").count("\n\t(segment\n"))
# show a wire near J1 (30,30)
for m in re.finditer(r'\(wire\n\t\t\(pts\n\t\t\t\(xy ([-\d.]+) ([-\d.]+)\) \(xy ([-\d.]+) ([-\d.]+)\)', sch):
    x1,y1,x2,y2 = map(float, m.groups())
    if abs(x1-30)<15 and abs(y1-30)<15:
        print("wire near J1", x1,y1,x2,y2)
        break
