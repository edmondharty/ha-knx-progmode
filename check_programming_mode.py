"""Continuously scan the KNX bus for devices in programming mode.

Each scan cycle sends an IndividualAddressRead broadcast; only devices in
programming mode respond. We track state across cycles and log ON/OFF
transitions. For each newly-detected device we read its mask version
(device family), manufacturer ID, order info and serial number.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime

from xknx import XKNX
from xknx.management import procedures
from xknx.profile import ResourceGenericPropertyId
from xknx.telegram import IndividualAddress, apci

# Mask version → human-readable device family.
# Source: KNX System Specification Vol. 6/0 (mask versions).
MASK_VERSIONS: dict[int, str] = {
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

# KNX manufacturer IDs (partial — most common). Unknown IDs are reported
# numerically so they can be looked up against the official KNX list.
MANUFACTURERS: dict[int, str] = {
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


def describe_mask(mask: int | None) -> str:
    if mask is None:
        return "unknown"
    return f"{MASK_VERSIONS.get(mask, 'unknown family')} (mask 0x{mask:04X})"


def describe_manufacturer(mid: int | None) -> str:
    if mid is None:
        return "unknown"
    return f"{MANUFACTURERS.get(mid, 'unknown vendor')} (ID {mid})"


def format_order_info(raw: bytes) -> str:
    text = raw.rstrip(b"\x00").decode("ascii", errors="replace").strip()
    return text or raw.hex()


def format_serial(raw: bytes) -> str:
    return f"{raw[:2].hex()}:{raw[2:].hex()}"


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


async def identify_device(
    xknx: XKNX, ia: IndividualAddress
) -> dict[str, object]:
    """Read device descriptor and a few standard properties from one device."""
    info: dict[str, object] = {}
    try:
        async with xknx.management.connection(address=ia) as conn:
            try:
                resp = await conn.request(
                    payload=apci.DeviceDescriptorRead(descriptor=0),
                    expected=apci.DeviceDescriptorResponse,
                )
                if isinstance(resp.payload, apci.DeviceDescriptorResponse):
                    info["mask"] = resp.payload.value
            except Exception as exc:
                info["mask_error"] = repr(exc)

            for key, pid in (
                ("manufacturer_id", ResourceGenericPropertyId.PID_MANUFACTURER_ID),
                ("order_info", ResourceGenericPropertyId.PID_ORDER_INFO),
                ("serial", ResourceGenericPropertyId.PID_SERIAL_NUMBER),
            ):
                try:
                    resp = await conn.request(
                        payload=apci.PropertyValueRead(
                            object_index=0, property_id=pid
                        ),
                        expected=apci.PropertyValueResponse,
                    )
                    if (
                        isinstance(resp.payload, apci.PropertyValueResponse)
                        and resp.payload.data
                    ):
                        info[key] = resp.payload.data
                except Exception as exc:
                    info[f"{key}_error"] = repr(exc)
    except Exception as exc:
        info["connection_error"] = repr(exc)
    return info


def print_device_details(ia: IndividualAddress, info: dict[str, object]) -> None:
    mask = info.get("mask")
    assert mask is None or isinstance(mask, int)
    print(f"    type    : {describe_mask(mask)}")

    mid_raw = info.get("manufacturer_id")
    mid = (
        int.from_bytes(mid_raw, "big")
        if isinstance(mid_raw, (bytes, bytearray)) and mid_raw
        else None
    )
    print(f"    vendor  : {describe_manufacturer(mid)}")

    order_raw = info.get("order_info")
    if isinstance(order_raw, (bytes, bytearray)) and order_raw:
        print(f"    order # : {format_order_info(bytes(order_raw))}")

    serial_raw = info.get("serial")
    if isinstance(serial_raw, (bytes, bytearray)) and serial_raw:
        print(f"    serial  : {format_serial(bytes(serial_raw))}")

    for key in ("mask_error", "connection_error"):
        if key in info:
            print(f"    {key}: {info[key]}")


async def watch(timeout: float, interval: float, identify: bool) -> int:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass
    print(
        f"Watching for KNX devices in programming mode "
        f"(scan {timeout:.1f}s, repeat every {interval:.1f}s). Ctrl-C to stop.",
        flush=True,
    )
    known: dict[IndividualAddress, dict[str, object]] = {}

    async with XKNX() as xknx:
        while True:
            try:
                addresses = await procedures.nm_individual_address_read(
                    xknx, timeout=timeout, raise_if_multiple=False
                )
            except Exception as exc:
                print(f"[{ts()}] scan error: {exc!r}")
                await asyncio.sleep(interval)
                continue

            current = set(addresses)
            previous = set(known)

            for ia in sorted(current - previous, key=str):
                print(f"[{ts()}] ON   {ia}")
                info: dict[str, object] = {}
                if identify:
                    info = await identify_device(xknx, ia)
                    print_device_details(ia, info)
                known[ia] = info

            for ia in sorted(previous - current, key=str):
                print(f"[{ts()}] OFF  {ia}")
                known.pop(ia, None)

            await asyncio.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="Seconds to listen for responses each scan (KNX spec: 3s).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Seconds to wait between scan cycles.",
    )
    parser.add_argument(
        "--no-identify",
        action="store_true",
        help="Skip reading device descriptor / manufacturer / serial.",
    )
    args = parser.parse_args()
    try:
        asyncio.run(
            watch(
                timeout=args.timeout,
                interval=args.interval,
                identify=not args.no_identify,
            )
        )
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
