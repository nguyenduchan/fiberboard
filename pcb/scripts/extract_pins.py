from pathlib import Path
import re

SYM = Path(r"C:\Users\duchan.nguyen\AppData\Local\Programs\KiCad\10.0\share\kicad\symbols")


def extract_raw(text: str, name: str) -> str:
    needle = f'(symbol "{name}"'
    start = text.find(needle)
    if start < 0:
        raise KeyError(name)
    i, depth = start, 0
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    raise RuntimeError(name)


def pins_of(lib: str, name: str):
    text = (SYM / lib).read_text(encoding="utf-8")
    block = extract_raw(text, name)
    # unit drawing pins are in *_1_1 or similar sub-symbols
    out = []
    for m in re.finditer(
        r'\(pin\s+(\w+)\s+\w+\s*\(\s*at\s+([-\d.]+)\s+([-\d.]+)\s+(\d+)\s*\).*?'
        r'\(name\s+"([^"]*)".*?'
        r'\(number\s+"([^"]+)"',
        block,
        flags=re.S,
    ):
        out.append((m.group(6), m.group(5), m.group(1), float(m.group(2)), float(m.group(3)), int(m.group(4))))
    # dedupe by number keeping first
    seen = set()
    uniq = []
    for p in out:
        if p[0] in seen:
            continue
        seen.add(p[0])
        uniq.append(p)
    return uniq


# Local Fiberboard lib
local = Path(r"d:\Project\embedded\fiberboard\pcb\libraries\Fiberboard.kicad_sym")
if local.exists():
    text = local.read_text(encoding="utf-8")
    for name in ["ESP32_DevKitC_Socket", "G5LE-1", "Opto_DIP6", "Screw_Terminal_01x02", "Screw_Terminal_01x03", "Fiber_Clamp_2CH", "SOT23"]:
        print(f"=== LOCAL {name} ===")
        try:
            block_start = text.find(f'(symbol "{name}"')
            # reuse extract via temp
            from tempfile import NamedTemporaryFile
            # monkey: write mini lib
            # simpler inline
            needle = f'(symbol "{name}"'
            start = text.find(needle)
            i, depth = start, 0
            while i < len(text):
                if text[i] == "(":
                    depth += 1
                elif text[i] == ")":
                    depth -= 1
                    if depth == 0:
                        block = text[start : i + 1]
                        break
                i += 1
            out = []
            for m in re.finditer(
                r'\(pin\s+(\w+)\s+\w+\s*\(\s*at\s+([-\d.]+)\s+([-\d.]+)\s+(\d+)\s*\).*?'
                r'\(name\s+"([^"]*)".*?'
                r'\(number\s+"([^"]+)"',
                block,
                flags=re.S,
            ):
                out.append((m.group(6), m.group(5), m.group(1), float(m.group(2)), float(m.group(3)), int(m.group(4))))
            seen=set(); 
            for p in out:
                if p[0] in seen: continue
                seen.add(p[0]); print(f"  {p[0]:>3} {p[1]:<16} {p[2]:<14} ({p[3]}, {p[4]}) r{p[5]}")
        except Exception as e:
            print(" ERR", e)

for lib, name in [
    ("Device.kicad_sym", "R"),
    ("Device.kicad_sym", "LED"),
    ("Device.kicad_sym", "C"),
    ("Device.kicad_sym", "D"),
    ("Device.kicad_sym", "R_Potentiometer"),
    ("Transistor_FET.kicad_sym", "AO3400A"),
    ("Sensor_Optical.kicad_sym", "SFH309"),
    ("Comparator.kicad_sym", "LM393"),
    ("Amplifier_Operational.kicad_sym", "LM2904"),
    ("Transistor_BJT.kicad_sym", "2N3904"),
    ("Interface_UART.kicad_sym", "MAX485E"),
    ("Regulator_Linear.kicad_sym", "AMS1117-3.3"),
    ("power.kicad_sym", "GND"),
    ("power.kicad_sym", "+5V"),
]:
    print(f"=== {name} ===")
    try:
        for num, nm, typ, x, y, rot in pins_of(lib, name):
            print(f"  {num:>3} {nm:<16} {typ:<14} ({x}, {y}) r{rot}")
    except Exception as e:
        print(" ERR", e)
