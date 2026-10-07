"""Vùng lắp ráp tùy chọn theo giắc cắm — DNP cả nhóm vẫn chạy bo lõi.

CORE_*: bắt buộc (nguồn + MCU + kéo GPIO an toàn khi không lắp opto).
OPT_*: chỉ lắp nếu dùng giắc tương ứng; không lắp thì firmware tắt chức năng đó.
"""

from __future__ import annotations

# Không có linh kiện nguồn dùng chung giữa hai cọc relay.
SHARED_LAYOUT_REFS: set[str] = set()

# Linh kiện xếp chồng trong dải interior, căn cột giắc mép bo (không đặt trong vùng MCU).
OUTPUT_ANCHORS: dict[str, list[str]] = {}

INPUT_ANCHORS: dict[str, list[str]] = {
    # Thứ tự: sát giắc trước (đèn), rồi mạch của giắc.
    "J1": ["D13"],
    "J2": ["D14", "R23"],
    "J3": ["D15", "R24", "R7", "U5", "R9"],
    "J4": ["D16", "R25", "R8", "U6", "R10"],
    # Cuộn, driver, lọc và đèn J5/J6 đặt sát cọc trong pcb_layout (không còn khối công suất).
    "J5": [],
    "J6": [],
    # MOSFET van, flyback và đèn đặt sát J7 trong pcb_layout (nhãn silk MOS).
    "J7": [],
    "J8": ["D20", "R29", "R18", "R19", "R15", "D9", "D10"],
    "F1T": ["D21", "R30", "C12"],
    "F1R": ["D22", "R31"],
    "F2T": ["D23", "R32", "C13"],
    "F2R": ["D24", "R33"],
}

CONNECTOR_ANCHORS: dict[str, list[str]] = {**OUTPUT_ANCHORS, **INPUT_ANCHORS}

# Ref -> tên nhóm KiCad / silk (một ref một nhóm).
_REF_TO_GROUP: dict[str, str] = {}


def _register(refs: list[str], group: str) -> None:
    for r in refs:
        _REF_TO_GROUP[r] = group


_register(["J1", "J2", "D13", "R22", "D14", "R23"], "CORE_PWR")
# Bảo vệ 24 V: tụ/trở nằm cùng nút chúng lọc (không tách xuống góc bo).
_register(
    [
        "F1", "L2", "C19", "C15", "D7", "RV1",
        "Q12", "R17", "C4", "C14", "D27", "R39", "NT1", "D11", "C23", "FB3",
    ],
    "PWR_24V_PROTECT",
)
# Buck + LDO: tụ vào/ra, Schottky, FB và chia áp sát U2/U3.
_register(
    [
        "C16", "C17", "U2", "D8", "L1", "R38", "R36", "R37",
        "C2", "C5", "FB2", "C22", "D25", "R34", "C7", "U3", "C3", "C18", "FB1", "C21", "D6", "R16",
    ],
    "PWR_BUCK",
)

_register(["U1", "R20", "R21", "R40", "R41", "R42", "R43", "R44", "R45"], "CORE_MCU")

_register(
    ["J5", "K1", "R11", "Q3", "D3", "D17", "R26", "FB4", "D12", "C24", "C25"],
    "OPT_J5_RLY1",
)
_register(
    ["J6", "K2", "R12", "Q4", "D4", "D18", "R27", "FB5", "D26", "C26", "C27"],
    "OPT_J6_RLY2",
)
_register(["Q5", "D5", "R13", "R14", "D19", "R28"], "OPT_J7_SOL")
_register(["R7", "U5", "R9", "D15", "R24"], "OPT_J3_FOOT")
_register(["R8", "U6", "R10", "D16", "R25"], "OPT_J4_NPN")
_register(["U7", "R15", "R18", "R19", "D9", "D10", "D20", "R29"], "OPT_J8_RS485")

_register(["F1T", "F1R", "C12", "D21", "R30", "D22", "R31"], "OPT_FIBER1")
_register(["F2T", "F2R", "C13", "D23", "R32", "D24", "R33"], "OPT_FIBER2")

# Giắc cái (chỉ hàng domino / quang — luôn gắn nếu dùng nhóm OPT tương ứng).
for j in ("J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8", "F1T", "F1R", "F2T", "F2R"):
    if j in ("J1", "J2"):
        _REF_TO_GROUP[j] = "CORE_PWR"
    elif j in ("J3",):
        _REF_TO_GROUP[j] = "OPT_J3_FOOT"
    elif j in ("J4",):
        _REF_TO_GROUP[j] = "OPT_J4_NPN"
    elif j in ("J5",):
        _REF_TO_GROUP[j] = "OPT_J5_RLY1"
    elif j in ("J6",):
        _REF_TO_GROUP[j] = "OPT_J6_RLY2"
    elif j in ("J7",):
        _REF_TO_GROUP[j] = "OPT_J7_SOL"
    elif j in ("J8",):
        _REF_TO_GROUP[j] = "OPT_J8_RS485"
    elif j in ("F1T", "F1R"):
        _REF_TO_GROUP[j] = "OPT_FIBER1"
    elif j in ("F2T", "F2R"):
        _REF_TO_GROUP[j] = "OPT_FIBER2"

ASSEMBLY_TITLES: dict[str, str] = {
    "CORE_PWR": "Bắt buộc: J1 nguồn vào, J2 cấp bàn phím",
    "PWR_24V_PROTECT": "Bắt buộc: bảo vệ 24 V",
    "PWR_BUCK": "Bắt buộc: buck 5 V / LDO 3,3 V",
    "CORE_MCU": "Bắt buộc: MCU",
    "OPT_J5_RLY1": "Tùy chọn: J5 relay 1",
    "OPT_J6_RLY2": "Tùy chọn: J6 relay 2",
    "OPT_J7_SOL": "Tùy chọn: J7 van",
    "OPT_J3_FOOT": "Tùy chọn: J3 chân",
    "OPT_J4_NPN": "Tùy chọn: J4 NPN",
    "OPT_J8_RS485": "Tùy chọn: J8 RS485",
    "OPT_FIBER1": "Tùy chọn: quang kênh 1",
    "OPT_FIBER2": "Tùy chọn: quang kênh 2",
}

# Nhóm OPT: không lắp -> không hàn các ref (trừ giắc cái cùng nhóm nếu không dùng thì DNP giắc).
OPTIONAL_GROUPS = frozenset(
    g for g in ASSEMBLY_TITLES if g.startswith("OPT_")
)

# Không bỏ nhóm trên bo 145 mm khi giắc nằm ở cạnh dài.
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
