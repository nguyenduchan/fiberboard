from pathlib import Path
import re

t = Path(r"d:/Project/embedded/fiberboard/pcb/fiberboard-logic.kicad_sch").read_text(encoding="utf-8")
for m in re.finditer(
    r'\(lib_id "Fiberboard:ESP32_DevKitC_Socket"\)\s*\(at ([-\d.]+) ([-\d.]+)', t
):
    print("U1 at", m.group(1), m.group(2))

i = t.find('(symbol "Fiberboard:ESP32_DevKitC_Socket"')
block = t[i : i + 20000]
pins = []
for m in re.finditer(
    r'\(at ([-\d.]+) ([-\d.]+) (\d+)\)\s*\n\s*\(length[\s\S]*?\(number "(\d+)"',
    block,
):
    pins.append((m.group(4), float(m.group(1)), float(m.group(2))))
print("count", len(pins))
print("first", pins[:8])
for n in ["1", "5", "7", "13", "14", "15", "32"]:
    print("pin", n, [p for p in pins if p[0] == n])

for name in ["FIBER1_ADC", "FIBER1_PWM", "+3V3", "GND"]:
    for m in re.finditer(
        rf'\(global_label "{name}"[\s\S]*?\(at ([-\d.]+) ([-\d.]+)', t
    ):
        print(f"label {name} at", m.group(1), m.group(2))
        break

# J1 pin geom vs place
for m in re.finditer(r'\(lib_id "Fiberboard:Screw_Terminal_01x02"\)\s*\(at ([-\d.]+) ([-\d.]+)', t):
    print("Screw at", m.group(1), m.group(2))
