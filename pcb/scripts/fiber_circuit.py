"""Fiber optic front-end: integrated Broadcom Versatile Link (POF 1 mm) on PCB."""

from __future__ import annotations

FIBER_PCB_PARTS: list[tuple] = []

FIBER_NOTES = """
Fiber (2 channels) — on-board Versatile Link (no external amplifier)
====================================================================
Parts (per channel):
  TX: AFBR-1624Z  (650 nm LED + driver, TTL in, 3.3/5 V)
  RX: AFBR-2624Z  (PIN + digitizer, TTL out, 3.3/5 V)
Fiber: 1 mm plastic optical fiber (POF), plug into module on front connector row (right side).

Wiring:
  ESP32 IO32/IO33 LEDC PWM -> F1T/F2T DATA_IN (optical power / modulation)
  F1R/F2R DATA_OUT -> ESP32 IO4 / IO15 (digital receive)
  +5 V + 100 nF local decoupling per channel (C12/C13)
  Footprint: Broadcom horizontal Versatile Link DIP (2.54 mm pitch, 7.62 mm rows) — see AV02-4369EN

GPIO:
  IO32 FIBER1_PWM   IO33 FIBER2_PWM
  IO4  FIBER1_DIG   IO15 FIBER2_DIG
  (IO34/IO35 ADC unused — no discrete analog front-end)

Alternates (same footprint family): AFBR-1629Z / AFBR-2529Z (inverted logic).
"""


def build_fiber_detail_schematic(place_symbol, global_label, text_box, wire, uid_fn) -> tuple[list, list, list, list]:
    """Minimal fiber block annotation (main design is in connectivity.py)."""
    texts = [
        text_box("FIBER: AFBR-1624Z TX + AFBR-2624Z RX per channel (1 mm POF)", 320, 40),
        text_box("Ports F1T/F1R F2T/F2R on front row (signal side) — no clamp J2/J11", 320, 46),
    ]
    return [], [], texts, []
