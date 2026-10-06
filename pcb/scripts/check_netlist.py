from pathlib import Path
import re
import subprocess

subprocess.run(
    [
        r"C:\Users\duchan.nguyen\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe",
        "sch",
        "export",
        "netlist",
        r"d:\Project\embedded\fiberboard\pcb\fiberboard-logic.kicad_sch",
        "-o",
        r"d:\Project\embedded\fiberboard\pcb\exports\logic.net",
        "--format",
        "kicadsexpr",
    ],
    check=False,
)

t = Path(r"d:/Project/embedded/fiberboard/pcb/exports/logic.net").read_text(encoding="utf-8")
print("file size", len(t))

# KiCad 10 nested format:
# (net
#   (code "1")
#   (name "+5V")
#   (node (ref "C2") (pin "2") ...)
pat = re.compile(
    r'\(net\s*\n\s*\(code "[^"]+"\)\s*\n\s*\(name "([^"]+)"\)([\s\S]*?)(?=\n\t\t\(net|\n\t\))'
)

found = {m.group(1): m.group(2) for m in pat.finditer(t)}
print("nets parsed", len(found))

for name in [
    "VIN_RAW",
    "VIN_FUSE",
    "FIBER1_ADC",
    "FIBER1_PWM",
    "F1_LED_A",
    "F1_GATE",
    "+24V",
    "BUCK_FB",
    "GND",
    "OUT_RLY1",
    "+5V",
    "+3V3",
]:
    body = found.get(name)
    if body is None:
        print(name, "NOT FOUND")
        continue
    refs = re.findall(r'\(ref "([^"]+)"\)\s*\n\s*\(pin "([^"]+)"\)', body)
    print(name, "count=", len(refs), refs[:30])
