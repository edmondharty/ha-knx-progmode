"""Background scanner that detects KNX devices in programming mode.

Reuses the running XKNX instance owned by Home Assistant's KNX integration
so no additional tunnel/connection is opened to the gateway.
"""
from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util
from xknx import XKNX
from xknx.management import procedures
from xknx.profile import ResourceGenericPropertyId
from xknx.telegram import IndividualAddress, apci

from .const import (
    EVENT_ENTERED,
    EVENT_LEFT,
    LOGGER,
    MANUFACTURERS,
    MASK_VERSIONS,
    SIGNAL_UPDATE,
)


def _describe_mask(mask: int | None) -> str | None:
    if mask is None:
        return None
    return MASK_VERSIONS.get(mask, "unknown family")


def _describe_manufacturer(mid: int | None) -> str | None:
    if mid is None:
        return None
    return MANUFACTURERS.get(mid, "unknown vendor")


def _format_order_info(raw: bytes | None) -> str | None:
    if not raw:
        return None
    text = raw.rstrip(b"\x00").decode("ascii", errors="replace").strip()
    return text or raw.hex()


def _format_serial(raw: bytes | None) -> str | None:
    if not raw or len(raw) < 6:
        return None
    return f"{raw[:2].hex()}:{raw[2:].hex()}"


def _resolve_knx_project(hass: HomeAssistant):
    """Return the KNXProject instance from HA's KNX integration, if loaded."""
    knx_data = hass.data.get("knx")
    if knx_data is None:
        return None
    project = getattr(knx_data, "project", None)
    if project is not None:
        return project
    if isinstance(knx_data, dict):
        for value in knx_data.values():
            project = getattr(value, "project", None)
            if project is not None:
                return project
    return None


def _project_device_info(
    hass: HomeAssistant, address: str
) -> dict[str, Any] | None:
    """Look up an individual address in the imported ETS project."""
    project = _resolve_knx_project(hass)
    if project is None:
        return None
    devices = getattr(project, "devices", None)
    if not devices:
        return None
    return devices.get(address) or devices.get(str(address))


def _flatten_application_program(value: Any) -> str | None:
    """xknxproject sometimes returns a string, sometimes a dict — normalise."""
    if value is None:
        return None
    if isinstance(value, dict):
        return (
            value.get("name")
            or value.get("program_name")
            or value.get("application_name")
        )
    return str(value) or None


def _compute_display_name(payload: dict[str, Any]) -> str:
    """TTS-friendly name. Prefers ETS-given name, then vendor+product, else IA."""
    if payload.get("project_name"):
        return payload["project_name"]
    mfg = (
        payload.get("project_manufacturer_name")
        or payload.get("manufacturer_name")
    )
    prod = payload.get("project_product_name")
    parts = [p for p in (mfg, prod) if p]
    if parts:
        return " ".join(parts)
    return payload["address"]


class KnxProgmodeScanner:
    """Owns the scan loop and the set of devices currently in programming mode."""

    def __init__(
        self,
        hass: HomeAssistant,
        xknx: XKNX,
        *,
        timeout: float,
        interval: float,
        identify: bool,
    ) -> None:
        self.hass = hass
        self.xknx = xknx
        self.timeout = timeout
        self.interval = interval
        self.identify = identify
        self.devices: dict[str, dict[str, Any]] = {}

        self._task: asyncio.Task[None] | None = None
        self._enabled = False
        self._wakeup = asyncio.Event()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @callback
    def async_set_enabled(self, enabled: bool) -> None:
        """Turn scanning on or off without tearing down the task."""
        if enabled == self._enabled:
            return
        self._enabled = enabled
        if not enabled:
            self._clear_devices()
        self._wakeup.set()
        self._notify()

    async def async_start(self) -> None:
        if self._task is not None:
            return
        self._task = self.hass.async_create_background_task(
            self._run(), name="knx_progmode_scanner"
        )

    async def async_stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self._clear_devices(fire_events=False)

    def _clear_devices(self, *, fire_events: bool = True) -> None:
        if not self.devices:
            return
        now = dt_util.utcnow().isoformat()
        for addr, info in list(self.devices.items()):
            if fire_events:
                payload = {**info, "left_at": now}
                self.hass.bus.async_fire(EVENT_LEFT, payload)
            del self.devices[addr]

    def _notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    async def _run(self) -> None:
        LOGGER.debug("knx_progmode scanner task started")
        try:
            while True:
                if not self._enabled:
                    self._wakeup.clear()
                    await self._wakeup.wait()
                    continue
                try:
                    await self._scan_once()
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001
                    LOGGER.exception("KNX programming-mode scan failed")
                try:
                    await asyncio.wait_for(
                        self._wakeup.wait(), timeout=self.interval
                    )
                    self._wakeup.clear()
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            LOGGER.debug("knx_progmode scanner task cancelled")
            raise

    async def _scan_once(self) -> None:
        addresses = await procedures.nm_individual_address_read(
            self.xknx, timeout=self.timeout, raise_if_multiple=False
        )
        if not self._enabled:
            return
        current = {str(a) for a in addresses}
        previous = set(self.devices)
        now = dt_util.utcnow().isoformat()

        for addr in sorted(current - previous):
            info = await self._build_entered_payload(addr, now)
            self.devices[addr] = info
            self.hass.bus.async_fire(EVENT_ENTERED, info)
            LOGGER.info("KNX device %s entered programming mode", addr)

        for addr in sorted(previous - current):
            cached = self.devices.pop(addr)
            payload = {**cached, "left_at": now}
            self.hass.bus.async_fire(EVENT_LEFT, payload)
            LOGGER.info("KNX device %s left programming mode", addr)

        if (current - previous) or (previous - current):
            self._notify()

    async def _build_entered_payload(
        self, addr: str, entered_at: str
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "address": addr,
            "entered_at": entered_at,
            # bus identify (populated from a connection-oriented read)
            "mask": None,
            "mask_family": None,
            "manufacturer_id": None,
            "manufacturer_name": None,
            "order_info": None,
            "serial": None,
            # ETS project lookup (populated from the imported .knxproj)
            "project_name": None,
            "project_description": None,
            "project_manufacturer_name": None,
            "project_product_name": None,
            "project_hardware_name": None,
            "project_application_program": None,
            "project_area": None,
            "project_line": None,
            "display_name": addr,
        }

        project_device = _project_device_info(self.hass, addr)
        if project_device:
            payload["project_name"] = project_device.get("name") or None
            payload["project_description"] = (
                project_device.get("description") or None
            )
            payload["project_manufacturer_name"] = (
                project_device.get("manufacturer_name") or None
            )
            payload["project_product_name"] = (
                project_device.get("product_name") or None
            )
            payload["project_hardware_name"] = (
                project_device.get("hardware_name") or None
            )
            payload["project_application_program"] = _flatten_application_program(
                project_device.get("application_program")
            )
            payload["project_area"] = project_device.get("area") or None
            payload["project_line"] = project_device.get("line") or None

        if self.identify:
            try:
                info = await self._identify_device(IndividualAddress(addr))
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Identify failed for %s: %r", addr, exc)
                info = {}

            mask = info.get("mask")
            if isinstance(mask, int):
                payload["mask"] = f"0x{mask:04X}"
                payload["mask_family"] = _describe_mask(mask)

            mid_raw = info.get("manufacturer_id")
            if isinstance(mid_raw, (bytes, bytearray)) and mid_raw:
                mid = int.from_bytes(mid_raw, "big")
                payload["manufacturer_id"] = mid
                payload["manufacturer_name"] = _describe_manufacturer(mid)

            order_raw = info.get("order_info")
            if isinstance(order_raw, (bytes, bytearray)):
                payload["order_info"] = _format_order_info(bytes(order_raw))

            serial_raw = info.get("serial")
            if isinstance(serial_raw, (bytes, bytearray)):
                payload["serial"] = _format_serial(bytes(serial_raw))

        payload["display_name"] = _compute_display_name(payload)
        return payload

    async def _identify_device(
        self, ia: IndividualAddress
    ) -> dict[str, Any]:
        info: dict[str, Any] = {}
        async with self.xknx.management.connection(address=ia) as conn:
            try:
                resp = await conn.request(
                    payload=apci.DeviceDescriptorRead(descriptor=0),
                    expected=apci.DeviceDescriptorResponse,
                )
                if isinstance(resp.payload, apci.DeviceDescriptorResponse):
                    info["mask"] = resp.payload.value
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("DeviceDescriptorRead failed for %s: %r", ia, exc)

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
                except Exception as exc:  # noqa: BLE001
                    LOGGER.debug(
                        "PropertyValueRead %s failed for %s: %r", key, ia, exc
                    )
        return info
