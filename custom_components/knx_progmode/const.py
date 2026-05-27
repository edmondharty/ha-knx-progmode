"""Constants for the KNX programming-mode watcher integration."""
from __future__ import annotations

from logging import getLogger
from typing import Final

DOMAIN: Final = "knx_progmode"
LOGGER = getLogger(__package__)

CONF_TIMEOUT: Final = "timeout"
CONF_INTERVAL: Final = "interval"
CONF_IDENTIFY: Final = "identify"

DEFAULT_TIMEOUT: Final = 3.0
DEFAULT_INTERVAL: Final = 1.0
DEFAULT_IDENTIFY: Final = True
DEFAULT_SCAN_ENABLED: Final = False

EVENT_ENTERED: Final = f"{DOMAIN}_entered"
EVENT_LEFT: Final = f"{DOMAIN}_left"

SIGNAL_UPDATE: Final = f"{DOMAIN}_update"

# Mask version -> human-readable device family.
# Source: KNX System Specification Vol. 6/0 (mask versions).
MASK_VERSIONS: Final[dict[int, str]] = {
    0x0010: "TP1 BCU1 (System 1)",
    0x0011: "TP1 BCU1 (System 1)",
    0x0012: "TP1 BCU1 (System 1)",
    0x0013: "TP1 BCU1 (System 1)",
    0x0020: "TP1 BCU2 (System 2)",
    0x0021: "TP1 BCU2 (System 2)",
    0x0025: "TP1 BCU2 (System 2)",
    0x0300: "TP1 LTE",
    0x0700: "TP1 BIM M112 (System 7)",
    0x0701: "TP1 BIM M112 (System 7)",
    0x0705: "TP1 BIM M112 (System 7)",
    0x07B0: "TP1 System B",
    0x0810: "TP1 Line / Backbone Coupler",
    0x0910: "Media Coupler TP1-PL110",
    0x091A: "Media Coupler TP1-RF",
    0x1012: "PL110 BCU1",
    0x1013: "PL110 BCU1",
    0x17B0: "RF System B",
    0x2705: "KNXnet/IP System 7",
    0x27B0: "KNXnet/IP System B",
    0x3012: "KNX IP BCU1",
    0x5705: "TP1 System 7 (extended)",
    0x57B0: "TP1 System B (extended)",
}

MANUFACTURERS: Final[dict[int, str]] = {
    1: "Siemens",
    2: "ABB",
    7: "Busch-Jaeger Elektro",
    100: "GIRA Giersiepen",
    131: "Albrecht Jung",
    134: "MDT technologies",
    138: "WAGO Kontakttechnik",
    157: "Theben AG",
    175: "Insta GmbH",
    197: "Schneider Electric / Merten",
    214: "Lingg & Janke",
    220: "Zennio",
}
