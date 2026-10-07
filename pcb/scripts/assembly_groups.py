"""Vùng lắp ráp tùy chọn theo giắc cắm — DNP cả nhóm vẫn chạy bo lõi.

CORE_*: bắt buộc (nguồn + MCU + kéo GPIO an toàn khi không lắp opto).
OPT_*: chỉ lắp nếu dùng giắc tương ứng; không lắp thì firmware tắt chức năng đó.
"""

from __future__ import annotations

# Giắc neo trên hàng mép -> chỉ linh kiện phục vụ **một** giắc (xem SHARED_LAYOUT_REFS).
RLY_PWR_REFS = ["FB4", "F2", "D12", "C24", "C25"]

# Nhóm lắp ráp gắn với nhiều giắc (hoặc không gắn một giắc) -> đặt vùng chức năng, không cột giắc.
GROUP_CONNECTORS: dict[str, tuple[str, ...]] = {
    "OPT_RLY_PWR": ("J5", "J6"),
}
SHARED_LAYOUT_GROUPS = frozenset({"OPT_RLY_PWR", "OPT_LED"})
SHARED_LAYOUT_REFS: set[str] = set(RLY_PWR_REFS)  # không xếp cột giắc

# Linh kiện xếp chồng trong dải interior, căn cột giắc mép bo (không đặt trong vùng MCU).
OUTPUT_ANCHORS: dict[str, list[str]] = {}

INPUT_ANCHORS: dict[str, list[str]] = {
    # Thứ tự: dưới (sát giắc) → lên.
    "J3": ["U5", "R7", "R9", "R20"],
    "J4": ["U6", "R8", "R10", "R21"],
    "J8": ["U7", "R15", "R18", "R19", "D9", "D10", "R16", "D6"],
    "F1T": ["C12"],
    "F2T": ["C13"],
}

CONNECTOR_ANCHORS: dict[str, list[str]] = {**OUTPUT_ANCHORS, **INPUT_ANCHORS}

# Ref -> tên nhóm KiCad / silk (một ref một nhóm).
_REF_TO_GROUP: dict[str, str] = {}


def _register(refs: list[str], group: str) -> None:
    for r in refs:
        _REF_TO_GROUP[r] = group


_register(
    [
        "J1", "F1", "L2", "RV1", "D7", "C19", "C15", "Q12", "R17",
        "C4", "C14", "NT1", "D11", "C23", "FB3",
        "U2", "L1", "D8", "C2", "C22", "U3", "C16", "C17", "C7", "C3",
        "FB2", "FB1", "R38", "R36", "R37", "C5", "C18", "C21",  # FB4 → OPT_RLY_PWR
    ],
    "CORE_PWR",
)

_register(["U1", "R20", "R21"], "CORE_MCU")
_register(["R16", "D6"], "OPT_LED")

_register(RLY_PWR_REFS, "OPT_RLY_PWR")
_register(["K1", "R11", "Q3", "D3"], "OPT_J5_RLY1")
_register(["K2", "R12", "Q4", "D4"], "OPT_J6_RLY2")
_register(["F3", "Q5", "D5", "R13", "R14"], "OPT_J7_SOL")
_register(["R7", "U5", "R9"], "OPT_J3_FOOT")
_register(["R8", "U6", "R10"], "OPT_J4_NPN")
_register(["U7", "R15", "R18", "R19", "D9", "D10"], "OPT_J8_RS485")

_register(["F1T", "F1R", "C12"], "OPT_FIBER1")
_register(["F2T", "F2R", "C13"], "OPT_FIBER2")

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
    "CORE_PWR": "Bắt buộc: nguồn J1, cấp keyboard J2",
    "CORE_MCU": "Bắt buộc: ESP32",
    "OPT_LED": "Tùy chọn: đèn STATUS (cột J8)",
    "OPT_RLY_PWR": "Tùy chọn: +5V_RLY — buck; lắp nếu J5 hoặc J6",
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
