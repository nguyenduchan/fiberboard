"""Vùng lắp ráp tùy chọn theo giắc cắm — DNP cả nhóm vẫn chạy bo lõi.

CORE_*: bắt buộc (nguồn + MCU).
OPT_*: chỉ lắp nếu dùng giắc tương ứng; không lắp thì firmware tắt chức năng đó.
"""

from __future__ import annotations

# Không có linh kiện nguồn dùng chung giữa hai cọc relay.
SHARED_LAYOUT_REFS: set[str] = set()

# Linh kiện xếp chồng trong dải interior, căn cột giắc mép bo (không đặt trong vùng MCU).
OUTPUT_ANCHORS: dict[str, list[str]] = {}

INPUT_ANCHORS: dict[str, list[str]] = {
    # Thứ tự: sát giắc trước (đèn), rồi mạch của giắc.
    "J3": ["D15", "R24", "R7", "U5", "R9"],
    "J4": ["D16", "R25", "R8", "U6", "R10"],
    "J9": ["D31", "R59", "R57", "U9", "R58"],
    "J10": ["D32", "R62", "R60", "U10", "R61"],
    # USB-C: chống sét và trở CC ngay sau cổng.
    "J11": ["R50", "R51"],
    # Cuộn, driver và đèn J5/J6, MOSFET J7 đặt sát cọc trong pcb_layout.
    "J5": [],
    "J6": [],
    "J7": [],
    "J8": ["D20", "R29", "R18", "R19", "R15", "D9", "U7", "C11", "R49"],
}

CONNECTOR_ANCHORS: dict[str, list[str]] = {**OUTPUT_ANCHORS, **INPUT_ANCHORS}

# Ref -> tên nhóm KiCad / silk (một ref một nhóm).
_REF_TO_GROUP: dict[str, str] = {}


def _register(refs: list[str], group: str) -> None:
    for r in refs:
        _REF_TO_GROUP[r] = group


_register(["J1", "J2"], "CORE_PWR")
_register(["F1", "D7", "C15", "Q12", "R17", "R63", "C4", "C14", "D27", "R39"], "PWR_24V_PROTECT")
_register(
    ["U2", "C16", "C17", "D8", "L1", "C2", "C5", "U3", "C7", "C3", "C18", "NT1", "D6", "R16"],
    "PWR_BUCK",
)
_register(
    ["U1", "C8", "C9", "R52", "C10", "R53", "R54", "R55", "SW1", "D30", "R56", "J11", "R50", "R51"],
    "CORE_MCU",
)
_register(["J3", "R7", "U5", "R9", "D15", "R24"], "OPT_J3_FOOT")
_register(["J4", "R8", "U6", "R10", "D16", "R25"], "OPT_J4_NPN")
_register(["J9", "R57", "U9", "R58", "D31", "R59"], "OPT_J9_AMP1")
_register(["J10", "R60", "U10", "R61", "D32", "R62"], "OPT_J10_AMP2")
_register(["J5", "K1", "R11", "R47", "Q3", "D3", "D17", "R26"], "OPT_J5_RLY1")
_register(["J6", "K2", "R12", "R48", "Q4", "D4", "D18", "R27"], "OPT_J6_RLY2")
_register(["J7", "Q5", "D5", "R13", "R14", "D19", "R28"], "OPT_J7_SOL")
_register(["J8", "U7", "C11", "R49", "R15", "R18", "R19", "D9", "D20", "R29"], "OPT_J8_RS485")

ASSEMBLY_TITLES: dict[str, str] = {
    "CORE_PWR": "Bắt buộc: J1 nguồn vào, J2 cấp bàn phím",
    "PWR_24V_PROTECT": "Bắt buộc: bảo vệ 24 V",
    "PWR_BUCK": "Bắt buộc: buck 5 V + LDO 3,3 V",
    "CORE_MCU": "Bắt buộc: MCU + USB",
    "OPT_J5_RLY1": "Tùy chọn: J5 relay 1",
    "OPT_J6_RLY2": "Tùy chọn: J6 relay 2",
    "OPT_J7_SOL": "Tùy chọn: J7 van",
    "OPT_J3_FOOT": "Tùy chọn: J3 chân",
    "OPT_J4_NPN": "Tùy chọn: J4 NPN",
    "OPT_J9_AMP1": "Tùy chọn: J9 amp 1",
    "OPT_J10_AMP2": "Tùy chọn: J10 amp 2",
    "OPT_J8_RS485": "Tùy chọn: J8 RS485",
}

# Nhóm OPT: không lắp -> không hàn các ref (kể cả giắc cái của nhóm).
OPTIONAL_GROUPS = frozenset(g for g in ASSEMBLY_TITLES if g.startswith("OPT_"))

OMITTED_GROUPS = frozenset()

STACK_REFS: set[str] = set()
for _lst in CONNECTOR_ANCHORS.values():
    STACK_REFS.update(_lst)


def omitted_refs() -> frozenset[str]:
    return frozenset(r for r, g in _REF_TO_GROUP.items() if g in OMITTED_GROUPS)


def assembly_group(ref: str) -> str:
    return _REF_TO_GROUP.get(ref, "MISC")


def refs_in_group(name: str) -> list[str]:
    return sorted(r for r, g in _REF_TO_GROUP.items() if g == name)
